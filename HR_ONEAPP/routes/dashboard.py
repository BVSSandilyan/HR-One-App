from flask import Blueprint, render_template, session, jsonify, request, redirect, url_for, flash
from decorators import login_required, admin_required, floor_events_by_joining
from models import db, User, Employee, LeaveRequest, Task, Meeting, Notification, Attendance, Payroll, Holiday
from datetime import date, timedelta
import calendar as calendar_module

dashboard_bp = Blueprint('dashboard', __name__)

def _employee_for(uid):
    return Employee.query.filter_by(user_id=uid).first()


# 20 annual leave days spread evenly across 12 months. Deliberately left as
# the exact fraction (not rounded) — rounding to 1 or 2 would silently shift
# how generous or strict the monthly threshold is from what was actually
# agreed (20/12).
MONTHLY_LEAVE_ALLOWANCE = 20.0 / 12.0


def _approved_leave_days_in_month(employee_id, month, year):
    """Sum of approved leave days that fall WITHIN the given calendar month,
    clipped at the month's boundaries — a leave spanning two months only
    counts the portion that's actually inside this one. Half-day leave
    contributes 0.5 if its single date falls in the month, matching the
    same convention leave.py's _days_in_range uses for the annual balance."""
    month_start = date(year, month, 1)
    month_end   = date(year, month, calendar_module.monthrange(year, month)[1])

    total = 0.0
    approved = LeaveRequest.query.filter_by(employee_id=employee_id, status='approved').all()
    for lr in approved:
        if lr.to_date < month_start or lr.from_date > month_end:
            continue  # no overlap with this month at all
        if lr.leave_type == 'half-day':
            total += 0.5
            continue
        clipped_from = max(lr.from_date, month_start)
        clipped_to   = min(lr.to_date, month_end)
        total += (clipped_to - clipped_from).days + 1
    return total


@dashboard_bp.route('/dashboard/salary/preview', methods=['POST'])
@admin_required
def salary_preview():
    """AJAX: given employee+month+year+basic+allowances, compute the leave
    days used this month and whether they exceed the monthly allowance.
    Read-only — never writes anything, safe to call as the admin types."""
    emp_id = request.form.get('employee_id', type=int)
    month  = request.form.get('month', type=int)
    year   = request.form.get('year', type=int)
    basic  = request.form.get('basic_salary', type=float) or 0.0
    allowances = request.form.get('allowances', type=float) or 0.0

    emp = Employee.query.get(emp_id) if emp_id else None
    if not emp:
        return jsonify({'error': 'Employee not found'}), 404

    days_used = _approved_leave_days_in_month(emp.id, month, year)
    excess    = max(0.0, days_used - MONTHLY_LEAVE_ALLOWANCE)

    return jsonify({
        'days_used': round(days_used, 2),
        'monthly_allowance': round(MONTHLY_LEAVE_ALLOWANCE, 2),
        'excess_days': round(excess, 2),
        'needs_rate': excess > 0,
        'full_salary': round(basic + allowances, 2)
    })


@dashboard_bp.route('/dashboard/salary/assign', methods=['POST'])
@admin_required
def salary_assign():
    """Commit: create/update this employee's payroll row for the month,
    using the SAME leave-days calculation salary_preview just showed the
    admin, so what was previewed is exactly what gets charged — no
    re-deriving a different number at commit time that could drift from
    what the admin actually saw and approved on screen."""
    emp_id     = request.form.get('employee_id', type=int)
    month      = request.form.get('month', type=int)
    year       = request.form.get('year', type=int)
    basic      = request.form.get('basic_salary', type=float) or 0.0
    allowances = request.form.get('allowances', type=float) or 0.0
    rate       = request.form.get('deduction_rate', type=float)

    emp = Employee.query.get(emp_id)
    if not emp:
        flash('Employee not found.', 'danger')
        return redirect(url_for('dashboard.index'))

    days_used = _approved_leave_days_in_month(emp.id, month, year)
    excess    = max(0.0, days_used - MONTHLY_LEAVE_ALLOWANCE)

    leave_deduction = 0.0
    if excess > 0:
        if rate is None or rate < 200 or rate > 500:
            flash(f'This employee used {days_used:g} leave day(s) this month, '
                  f'{excess:.2f} over the {MONTHLY_LEAVE_ALLOWANCE:.2f}/month allowance. '
                  f'Enter a deduction rate between ₹200 and ₹500 per day to proceed.', 'danger')
            return redirect(url_for('dashboard.index'))
        leave_deduction = round(excess * rate, 2)

    payroll = Payroll.query.filter_by(employee_id=emp.id, month=month, year=year).first()
    if not payroll:
        payroll = Payroll(employee_id=emp.id, month=month, year=year, created_by=session['user_id'])
        db.session.add(payroll)

    payroll.basic_salary        = basic
    payroll.allowances          = allowances
    payroll.leave_days_used     = days_used
    payroll.leave_deduction_rate= rate if excess > 0 else None
    payroll.leave_deduction     = leave_deduction
    # Manual `deductions` (from the separate Payroll > Assign page) is left
    # untouched here on purpose — this widget only ever writes the
    # leave-driven figures, never the generic deductions field, so neither
    # flow can clobber the other's number on the same row.
    payroll.net_salary = basic + allowances - (payroll.deductions or 0.0) - leave_deduction

    emp.salary = basic
    db.session.commit()

    if excess > 0:
        flash(f'Salary assigned. {days_used:g} leave days used this month '
              f'({excess:.2f} over allowance) → ₹{leave_deduction:.2f} deducted. '
              f'Net salary: ₹{payroll.net_salary:.2f}', 'success')
    else:
        flash(f'Full salary assigned — {days_used:g} leave day(s) used, '
              f'within the {MONTHLY_LEAVE_ALLOWANCE:.2f}/month allowance. '
              f'Net salary: ₹{payroll.net_salary:.2f}', 'success')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/dashboard')
@login_required
def index():
    uid  = session['user_id']
    role = session['user_role']

    total_employees = Employee.query.count()
    total_users     = User.query.count()
    active_meetings = Meeting.query.filter_by(status='active').count()
    my_tasks        = Task.query.filter_by(assigned_to=uid).filter(Task.status != 'completed').all()

    salary_widget_employees = None
    pending_registrations   = None
    pending_reg_count       = 0
    if role == 'admin':
        pending_leaves = LeaveRequest.query.filter_by(status='pending').count()
        leave_balance  = None
        salary_widget_employees = db.session.query(Employee, User).join(
            User, Employee.user_id == User.id
        ).filter(User.role.in_(['employee', 'hr'])).order_by(User.name).all()
        # Registration requests — only pending ones shown on dashboard for
        # immediate action; full history is on /admin/registrations page.
        pending_registrations = User.query.filter_by(
            approval_status='pending').order_by(User.created_at.desc()).all()
        pending_reg_count = len(pending_registrations)
    else:
        emp = Employee.query.filter_by(user_id=uid).first()
        pending_leaves = LeaveRequest.query.filter_by(
            employee_id=emp.id if emp else -1, status='pending').count()
        leave_balance = emp.leave_balance if emp and emp.leave_balance is not None else 20.0

    return render_template('dashboard/index.html',
        total_employees=total_employees,
        total_users=total_users,
        pending_leaves=pending_leaves,
        active_meetings=active_meetings,
        my_tasks=my_tasks,
        leave_balance=leave_balance,
        salary_widget_employees=salary_widget_employees,
        pending_registrations=pending_registrations,
        pending_reg_count=pending_reg_count,
        current_month=date.today().month,
        current_year=date.today().year,
        role=role
    )


@dashboard_bp.route('/api/calendar/overview')
@login_required
def calendar_overview():
    """Combined feed: meetings + my tasks + my attendance + my payroll + holidays."""
    uid = session['user_id']
    events = []

    for m in Meeting.query.all():
        # A meeting still pending its fixed date hasn't gone live yet — a
        # non-admin shouldn't see it on their personal calendar at all,
        # same rule meeting.calendar_feed already applies. Admin keeps
        # full visibility since they need to track what they scheduled.
        if m.status == 'scheduled' and session.get('user_role') != 'admin':
            continue
        display_date = m.scheduled_date or m.started_at.date()
        events.append({
            'title': f'📹 {m.title}' + (' (scheduled)' if m.status == 'scheduled' else ''),
            'start': display_date.strftime('%Y-%m-%d'),
            'color': '#64748b' if m.status == 'scheduled' else '#1d4ed8',
            'category': 'Meeting'
        })

    for t in Task.query.filter_by(assigned_to=uid).all():
        if t.due_date:
            color = '#dc2626' if t.is_overdue else ('#16a34a' if t.status == 'completed'
                     else '#2563eb' if t.status == 'in-progress' else '#d97706')
            events.append({
                'title': f'📋 {t.title}', 'start': t.due_date.strftime('%Y-%m-%d'),
                'color': color, 'category': 'Task'
            })

    emp = _employee_for(uid)
    if emp:
        for a in Attendance.query.filter_by(employee_id=emp.id).all():
            color = '#16a34a' if a.status == 'present' else ('#d97706' if a.status == 'half-day' else '#dc2626')
            events.append({
                'title': f'✅ {a.status.capitalize()}', 'start': a.date.strftime('%Y-%m-%d'),
                'color': color, 'category': 'Attendance'
            })
        for p in Payroll.query.filter_by(employee_id=emp.id).all():
            events.append({
                'title': f'💰 Salary ₹{p.net_salary:.0f}',
                'start': (p.pay_date or date(p.year, p.month, 1)).strftime('%Y-%m-%d'),
                'color': '#7c3aed', 'category': 'Payroll'
            })
        if emp.date_of_joining:
            events.append({
                'title': '🎉 Joined Company', 'start': emp.date_of_joining.strftime('%Y-%m-%d'),
                'color': '#0891b2', 'category': 'Milestone'
            })
        leave_color = {'pending': '#d97706', 'approved': '#16a34a', 'rejected': '#dc2626'}
        for lr in LeaveRequest.query.filter_by(employee_id=emp.id).all():
            d = lr.from_date
            while d <= lr.to_date:
                events.append({
                    'title': f'🗓 {lr.leave_type.capitalize()} leave ({lr.status})',
                    'start': d.strftime('%Y-%m-%d'),
                    'color': leave_color.get(lr.status, '#64748b'), 'category': 'Leave'
                })
                d += timedelta(days=1)

    for h in Holiday.query.all():
        events.append({
            'title': f'🏖 {h.name}', 'start': h.date.strftime('%Y-%m-%d'),
            'color': '#64748b', 'category': 'Holiday'
        })

    # Floor everything in THIS feed to the viewer's own joining date.
    # Admin doesn't hit this branch — admin's dashboard is the aggregate
    # view and needs full visibility — but every employee/HR person sees
    # only this combined personal feed, so this is the one place the
    # floor actually has to apply for it to mean anything in practice.
    if session.get('user_role') != 'admin' and emp:
        events = floor_events_by_joining(events, emp.date_of_joining)

    return jsonify(events)
