from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decorators import admin_required, floor_events_by_joining
from models import db, Attendance, Employee, User, Department, Holiday
from datetime import date

attendance_bp = Blueprint('attendance', __name__, url_prefix='/attendance')


@attendance_bp.route('/')
@admin_required
def index():
    emp_filter  = request.args.get('employee_id', type=int)
    dept_filter = request.args.get('department_id', type=int)

    q = db.session.query(Attendance, Employee, User).join(
        Employee, Attendance.employee_id == Employee.id).join(
        User, Employee.user_id == User.id)

    if emp_filter:
        q = q.filter(Employee.id == emp_filter)
    if dept_filter:
        q = q.filter(Employee.department_id == dept_filter)

    page = request.args.get('page', 1, type=int)
    pagination = q.order_by(Attendance.date.desc()).paginate(page=page, per_page=20, error_out=False)
    records = pagination.items

    today = date.today()
    present_today = Attendance.query.filter_by(date=today, status='present').count()
    absent_today  = Attendance.query.filter_by(date=today, status='absent').count()
    leave_today   = Attendance.query.filter_by(date=today, status='leave').count()

    employees   = db.session.query(Employee, User).join(User, Employee.user_id == User.id).all()
    departments = Department.query.all()

    return render_template('attendance/index.html', records=records, pagination=pagination,
                            present_today=present_today, absent_today=absent_today,
                            leave_today=leave_today, employees=employees,
                            departments=departments, emp_filter=emp_filter, dept_filter=dept_filter)


@attendance_bp.route('/api/calendar')
@admin_required
def calendar_feed():
    emp_filter = request.args.get('employee_id', type=int)

    q = db.session.query(Attendance, Employee, User).join(
        Employee, Attendance.employee_id == Employee.id).join(
        User, Employee.user_id == User.id)
    if emp_filter:
        q = q.filter(Employee.id == emp_filter)

    events = []
    for a, emp, user in q.all():
        color = {'present': '#16a34a', 'absent': '#dc2626',
                 'half-day': '#d97706', 'leave': '#7c3aed'}.get(a.status, '#64748b')
        events.append({
            'title': f'{user.name[:12]} — {a.status}',
            'start': a.date.strftime('%Y-%m-%d'),
            'color': color, 'category': a.status.capitalize()
        })
    for h in Holiday.query.all():
        events.append({
            'title': f'🏖 {h.name}', 'start': h.date.strftime('%Y-%m-%d'),
            'color': '#64748b', 'category': 'Holiday'
        })

    # The unfiltered admin view intentionally shows everything — admin
    # needs full visibility. The floor only makes sense once admin has
    # narrowed down to ONE specific employee, since at that point the
    # feed is effectively showing "that employee's calendar" and a
    # pre-joining attendance row for them would just be stray/bad data.
    if emp_filter:
        single_emp = Employee.query.get(emp_filter)
        if single_emp:
            events = floor_events_by_joining(events, single_emp.date_of_joining)

    return jsonify(events)


@attendance_bp.route('/mark', methods=['GET', 'POST'])
@admin_required
def mark():
    employees = db.session.query(Employee, User).join(User, Employee.user_id == User.id).all()
    if request.method == 'POST':
        today = date.today()
        for emp, user in employees:
            status   = request.form.get(f'status_{emp.id}', 'absent')
            existing = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
            if existing:
                existing.status, existing.marked_by = status, session['user_id']
            else:
                db.session.add(Attendance(employee_id=emp.id, date=today,
                                           status=status, marked_by=session['user_id']))
        db.session.commit()
        flash("Attendance marked for today!", 'success')
        return redirect(url_for('attendance.index'))
    return render_template('attendance/mark.html', employees=employees, today=date.today())


@attendance_bp.route('/holiday/add', methods=['POST'])
@admin_required
def add_holiday():
    name = request.form.get('name')
    hdate = request.form.get('date')
    if name and hdate:
        db.session.add(Holiday(name=name, date=date.fromisoformat(hdate),
                                notes=request.form.get('notes', '')))
        db.session.commit()
        flash('Holiday added to calendar.', 'success')
    return redirect(url_for('attendance.index'))
