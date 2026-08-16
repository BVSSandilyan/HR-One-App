from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from decorators import login_required, admin_required, floor_events_by_joining
from models import db, LeaveRequest, Employee, User, Attendance, Notification, Payroll
from datetime import datetime, date, timedelta

leave_bp = Blueprint('leave', __name__, url_prefix='/leave')


def _employee_for(uid):
    return Employee.query.filter_by(user_id=uid).first()


def _days_in_range(lr):
    """Half-day leave is always a single date (enforced client-side and
    consumes 0.5 of the balance. Every other type counts 1 full day per
    calendar date in [from_date, to_date] inclusive."""
    if lr.leave_type == 'half-day':
        return 0.5
    return (lr.to_date - lr.from_date).days + 1


def _preview_approval(lr):
    """Read-only: compute what approving this request WOULD do, without
    touching the session. Safe to call from a GET handler."""
    days = _days_in_range(lr)
    emp  = Employee.query.get(lr.employee_id)
    current_balance = emp.leave_balance if emp and emp.leave_balance is not None else 0.0
    excess = max(0.0, days - current_balance)
    return {
        'days': days,
        'needs_rate': excess > 0,
        'excess_days': excess,
        'balance_after': max(0.0, current_balance - days)
    }


def _commit_approval(lr, reviewer_id, deduction_rate=None):
    """Actually apply the effects of approving a leave request: mark
    attendance for every date in range, decrement the employee's leave
    balance, and — if the request consumes more days than the employee has
    left — record the excess and push a deduction into that leave's
    starting month's payroll record (deduction_rate must be supplied
    whenever the preview says needs_rate=True; the caller is responsible
    for checking that before calling this).
    """
    preview = _preview_approval(lr)
    days, excess = preview['days'], preview['excess_days']
    emp = Employee.query.get(lr.employee_id)

    att_status = 'half-day' if lr.leave_type == 'half-day' else 'leave'
    d = lr.from_date
    while d <= lr.to_date:
        existing = Attendance.query.filter_by(employee_id=lr.employee_id, date=d).first()
        if existing:
            existing.status, existing.marked_by = att_status, reviewer_id
        else:
            db.session.add(Attendance(employee_id=lr.employee_id, date=d,
                                       status=att_status, marked_by=reviewer_id))
        d += timedelta(days=1)

    # Decrement balance, floored at 0 — the stored balance represents what's
    # left, not a debt; the debt itself is the `excess` handled below.
    if emp:
        emp.leave_balance = preview['balance_after']

    lr.days_consumed = days
    lr.excess_days   = excess

    if excess > 0:
        # Defensive: every current caller already checks needs_rate before
        # getting here, but a missing/invalid rate must never silently
        # corrupt data (excess * None would crash; a negative or absurd
        # rate would write a bogus deduction). Treat it as a precondition
        # violation rather than trusting caller discipline alone.
        if deduction_rate is None or deduction_rate < 200 or deduction_rate > 500:
            raise ValueError(
                f'_commit_approval called with excess_days={excess} but '
                f'deduction_rate={deduction_rate!r} is missing or outside ₹200-500'
            )
        lr.deduction_rate   = deduction_rate
        lr.deduction_amount = excess * deduction_rate

        month, year = lr.from_date.month, lr.from_date.year
        payroll = Payroll.query.filter_by(employee_id=lr.employee_id, month=month, year=year).first()
        if not payroll:
            payroll = Payroll(
                employee_id=lr.employee_id, month=month, year=year,
                basic_salary=(emp.salary if emp else 0.0),
                allowances=0.0, deductions=0.0, created_by=reviewer_id
            )
            db.session.add(payroll)
        payroll.deductions = (payroll.deductions or 0.0) + lr.deduction_amount
        payroll.net_salary = payroll.basic_salary + payroll.allowances - payroll.deductions

    return {'excess_days': excess, 'balance_after': preview['balance_after']}


# ── LIST (employee sees own; admin sees all) ──
@leave_bp.route('/')
@login_required
def index():
    uid, role = session['user_id'], session['user_role']
    page = request.args.get('page', 1, type=int)

    if role == 'admin':
        q = db.session.query(LeaveRequest, Employee, User).join(
            Employee, LeaveRequest.employee_id == Employee.id).join(
            User, Employee.user_id == User.id
        ).order_by(LeaveRequest.applied_on.desc())
    else:
        emp = _employee_for(uid)
        q = db.session.query(LeaveRequest, Employee, User).join(
            Employee, LeaveRequest.employee_id == Employee.id).join(
            User, Employee.user_id == User.id
        ).filter(Employee.id == (emp.id if emp else -1)
        ).order_by(LeaveRequest.applied_on.desc())

    pagination = q.paginate(page=page, per_page=20, error_out=False)
    records = pagination.items
    pending_count = LeaveRequest.query.filter_by(status='pending').count() if role == 'admin' else None

    return render_template('leave/index.html', records=records, pagination=pagination,
                            role=role, pending_count=pending_count)


# ── CALENDAR FEED ──
@leave_bp.route('/api/calendar')
@login_required
def calendar_feed():
    uid, role = session['user_id'], session['user_role']
    color_map = {'pending': '#d97706', 'approved': '#16a34a', 'rejected': '#dc2626'}

    if role == 'admin':
        rows = db.session.query(LeaveRequest, Employee, User).join(
            Employee, LeaveRequest.employee_id == Employee.id).join(
            User, Employee.user_id == User.id).all()
    else:
        emp = _employee_for(uid)
        rows = db.session.query(LeaveRequest, Employee, User).join(
            Employee, LeaveRequest.employee_id == Employee.id).join(
            User, Employee.user_id == User.id
        ).filter(Employee.id == (emp.id if emp else -1)).all()

    events = []
    for lr, emp, user in rows:
        color = color_map.get(lr.status, '#64748b')
        d = lr.from_date
        while d <= lr.to_date:
            events.append({
                'title': f'🗓 {user.name[:12]} — {lr.leave_type} ({lr.status})',
                'start': d.strftime('%Y-%m-%d'),
                'color': color,
                'category': lr.status.capitalize()
            })
            d += timedelta(days=1)

    if role != 'admin':
        emp = _employee_for(uid)
        if emp:
            events = floor_events_by_joining(events, emp.date_of_joining)

    return jsonify(events)


# ── APPLY (employee / hr) ──
@leave_bp.route('/apply', methods=['GET', 'POST'])
@login_required
def apply():
    uid = session['user_id']
    emp = _employee_for(uid)
    if not emp:
        flash('No employee profile found for your account.', 'danger')
        return redirect(url_for('dashboard.index'))

    join_date = emp.date_of_joining.isoformat() if emp.date_of_joining else None
    balance   = emp.leave_balance if emp.leave_balance is not None else 20.0

    if request.method == 'POST':
        leave_type = request.form.get('leave_type')
        from_date  = request.form.get('from_date')
        to_date    = request.form.get('to_date')
        reason     = request.form.get('reason', '')

        if not (leave_type and from_date and to_date):
            flash('Please fill in all required fields.', 'danger')
            return render_template('leave/apply.html', join_date=join_date, balance=balance)

        f_date = date.fromisoformat(from_date)
        t_date = date.fromisoformat(to_date)
        if t_date < f_date:
            flash('End date cannot be before start date.', 'danger')
            return render_template('leave/apply.html', join_date=join_date, balance=balance)

        # Authoritative server-side floor: an employee cannot request leave
        # for a date before they actually joined. This is checked here, not
        # just via the date-picker's min attribute, because a min attribute
        # is purely cosmetic — anyone can submit the form directly and skip
        # the browser control entirely.
        if emp.date_of_joining and f_date < emp.date_of_joining:
            flash(f'You cannot request leave before your joining date '
                  f'({emp.date_of_joining.strftime("%d %b %Y")}).', 'danger')
            return render_template('leave/apply.html', join_date=join_date, balance=balance)

        # Block a new request whose date range overlaps an ALREADY-APPROVED
        # leave for this same employee. Deliberately checks only 'approved'
        # (not 'pending') — two pending requests for the same dates are an
        # admin-review concern, not something to block at submission time.
        # Standard interval-overlap test: two ranges overlap unless one
        # ends before the other starts.
        overlap = LeaveRequest.query.filter(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.status == 'approved',
            LeaveRequest.from_date <= t_date,
            LeaveRequest.to_date >= f_date
        ).first()
        if overlap:
            flash(f'You already have approved {overlap.leave_type} leave from '
                  f'{overlap.from_date.strftime("%d %b %Y")} to {overlap.to_date.strftime("%d %b %Y")} — '
                  f'that overlaps the dates you just selected. Choose different dates.', 'danger')
            return render_template('leave/apply.html', join_date=join_date, balance=balance)

        lr = LeaveRequest(
            employee_id=emp.id, leave_type=leave_type,
            from_date=f_date, to_date=t_date, reason=reason, status='pending'
        )
        db.session.add(lr)
        db.session.flush()

        # Notify every admin
        admins = User.query.filter_by(role='admin', is_active=True).all()
        for a in admins:
            db.session.add(Notification(
                user_id=a.id,
                message=f'🗓 {session["user_name"]} requested {leave_type} leave '
                        f'({f_date.strftime("%d %b")} – {t_date.strftime("%d %b")})',
                type='leave', ref_id=lr.id
            ))
        db.session.commit()

        flash('Leave request submitted! You will be notified once reviewed.', 'success')
        return redirect(url_for('leave.index'))

    return render_template('leave/apply.html', join_date=join_date, balance=balance)


# ── APPROVE (admin) ──
# GET shows a confirmation page — required when the request exceeds the
# employee's remaining balance, since admin must enter a ₹200-500/day rate
# before anything is committed; shown as a simple one-click confirm
# otherwise, since a GET request must never have side effects on its own.
@leave_bp.route('/<int:leave_id>/approve', methods=['GET', 'POST'])
@admin_required
def approve(leave_id):
    lr = LeaveRequest.query.get_or_404(leave_id)
    if lr.status != 'pending':
        flash('This request has already been reviewed.', 'warning')
        return redirect(url_for('leave.index'))

    if request.method == 'GET':
        preview = _preview_approval(lr)
        emp = Employee.query.get(lr.employee_id)
        return render_template('leave/confirm_approve.html', lr=lr, emp=emp,
                                preview=preview)

    # POST: actually commit.
    rate_str = request.form.get('deduction_rate', '').strip()
    preview = _preview_approval(lr)

    if preview['needs_rate'] and not rate_str:
        flash(f'This request exceeds the available balance by {preview["excess_days"]:.1f} day(s). '
              f'Please enter a deduction rate to proceed.', 'danger')
        return redirect(url_for('leave.approve', leave_id=leave_id))

    # The confirm_approve.html input has min="200" max="500", but that's a
    # browser-side hint only — anyone posting directly to this route
    # bypasses it entirely. The ₹200–500 range has to be enforced here too,
    # or an admin (or a malformed/malicious request) could set an arbitrary
    # rate with no upper bound.
    deduction_rate = None
    if preview['needs_rate']:
        try:
            deduction_rate = float(rate_str)
        except ValueError:
            flash('Enter a valid numeric deduction rate.', 'danger')
            return redirect(url_for('leave.approve', leave_id=leave_id))
        if deduction_rate < 200 or deduction_rate > 500:
            flash('Deduction rate must be between ₹200 and ₹500 per day.', 'danger')
            return redirect(url_for('leave.approve', leave_id=leave_id))

    result = _commit_approval(lr, session['user_id'], deduction_rate=deduction_rate)

    lr.status      = 'approved'
    lr.reviewed_by = session['user_id']
    lr.reviewed_on = datetime.utcnow()

    emp = Employee.query.get(lr.employee_id)
    if emp:
        extra = ''
        if result['excess_days'] > 0:
            extra = (f' {result["excess_days"]:.1f} day(s) exceeded your balance and '
                     f'₹{lr.deduction_amount:.0f} will be deducted from your salary.')
        db.session.add(Notification(
            user_id=emp.user_id,
            message=f'✅ Your {lr.leave_type} leave request '
                    f'({lr.from_date.strftime("%d %b")} – {lr.to_date.strftime("%d %b")}) was approved.{extra}',
            type='leave', ref_id=lr.id
        ))

    db.session.commit()
    flash('Leave request approved.' + (
        f' ₹{lr.deduction_amount:.0f} deduction applied for {result["excess_days"]:.1f} excess day(s).'
        if result['excess_days'] > 0 else ''), 'success')
    return redirect(url_for('leave.index'))


# ── DECLINE (admin) ──
@leave_bp.route('/<int:leave_id>/decline', methods=['POST'])
@admin_required
def decline(leave_id):
    lr = LeaveRequest.query.get_or_404(leave_id)
    lr.status      = 'rejected'
    lr.reviewed_by = session['user_id']
    lr.reviewed_on = datetime.utcnow()

    emp = Employee.query.get(lr.employee_id)
    if emp:
        db.session.add(Notification(
            user_id=emp.user_id,
            message=f'❌ Your {lr.leave_type} leave request '
                    f'({lr.from_date.strftime("%d %b")} – {lr.to_date.strftime("%d %b")}) was declined.',
            type='leave', ref_id=lr.id
        ))

    db.session.commit()
    flash('Leave request declined.', 'info')
    return redirect(url_for('leave.index'))


# ── QUICK ACTION FROM NOTIFICATION BELL (AJAX) ──
@leave_bp.route('/<int:leave_id>/quick/<action>', methods=['POST'])
@admin_required
def quick_action(leave_id, action):
    if action not in ('approve', 'decline'):
        return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
    lr = LeaveRequest.query.get_or_404(leave_id)
    if lr.status != 'pending':
        return jsonify({'status': 'error', 'message': 'Already reviewed'}), 400

    if action == 'approve':
        preview = _preview_approval(lr)
        if preview['needs_rate']:
            # One-click approval from the bell has no rate-entry UI, and a
            # rate must come from the admin (not guessed/defaulted here).
            # Tell the frontend to send them to the full review page
            # instead of approving with no deduction applied.
            return jsonify({
                'status': 'needs_rate',
                'redirect': url_for('leave.approve', leave_id=leave_id),
                'excess_days': preview['excess_days']
            })
        result = _commit_approval(lr, session['user_id'])
        lr.status = 'approved'
        msg_prefix = '✅ approved'
    else:
        lr.status = 'rejected'
        msg_prefix = '❌ declined'

    lr.reviewed_by = session['user_id']
    lr.reviewed_on = datetime.utcnow()

    emp = Employee.query.get(lr.employee_id)
    if emp:
        db.session.add(Notification(
            user_id=emp.user_id,
            message=f'{msg_prefix.capitalize()}: your {lr.leave_type} leave request '
                    f'({lr.from_date.strftime("%d %b")} – {lr.to_date.strftime("%d %b")})',
            type='leave', ref_id=lr.id
        ))

    db.session.commit()
    return jsonify({'status': 'ok', 'new_status': lr.status})
