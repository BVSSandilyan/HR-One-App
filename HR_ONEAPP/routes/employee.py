from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decorators import login_required, admin_or_hr_required
from models import db, Employee, User, Department
from datetime import date

employee_bp = Blueprint('employee', __name__, url_prefix='/employee')


@employee_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    pagination = db.session.query(Employee, User).join(
        User, Employee.user_id == User.id).order_by(User.name).paginate(
        page=page, per_page=20, error_out=False)
    employees = pagination.items
    return render_template('employee/index.html', employees=employees, pagination=pagination)


@employee_bp.route('/api/calendar')
@login_required
def calendar_feed():
    events = []
    today = date.today()
    for emp, user in db.session.query(Employee, User).join(User, Employee.user_id == User.id).all():
        if emp.date_of_joining:
            events.append({
                'title': f'🎉 {user.name[:14]} joined', 'start': emp.date_of_joining.strftime('%Y-%m-%d'),
                'color': '#0891b2', 'category': 'Joining'
            })
            try:
                anniv = emp.date_of_joining.replace(year=today.year)
                if anniv != emp.date_of_joining:
                    events.append({
                        'title': f'🏆 {user.name[:14]} anniversary', 'start': anniv.strftime('%Y-%m-%d'),
                        'color': '#7c3aed', 'category': 'Anniversary'
                    })
            except ValueError:
                pass
        if emp.date_of_birth:
            try:
                bday = emp.date_of_birth.replace(year=today.year)
                events.append({
                    'title': f'🎂 {user.name[:14]} birthday', 'start': bday.strftime('%Y-%m-%d'),
                    'color': '#db2777', 'category': 'Birthday'
                })
            except ValueError:
                pass
        if emp.probation_end:
            events.append({
                'title': f'⏳ {user.name[:14]} probation ends', 'start': emp.probation_end.strftime('%Y-%m-%d'),
                'color': '#d97706', 'category': 'Probation'
            })
        if emp.contract_end:
            events.append({
                'title': f'📄 {user.name[:14]} contract renewal', 'start': emp.contract_end.strftime('%Y-%m-%d'),
                'color': '#dc2626', 'category': 'Contract'
            })
    return jsonify(events)


@employee_bp.route('/<int:emp_id>')
@login_required
def detail(emp_id):
    emp, user = db.session.query(Employee, User).join(
        User, Employee.user_id == User.id).filter(Employee.id == emp_id).first_or_404()
    return render_template('employee/detail.html', emp=emp, user=user)


@employee_bp.route('/edit/<int:emp_id>', methods=['GET', 'POST'])
@admin_or_hr_required
def edit(emp_id):
    emp  = Employee.query.get_or_404(emp_id)
    user = User.query.get(emp.user_id)
    depts = Department.query.all()
    if request.method == 'POST':
        emp.designation   = request.form.get('designation')
        emp.phone         = request.form.get('phone')
        emp.address       = request.form.get('address')
        emp.department_id = request.form.get('department_id') or None
        dob   = request.form.get('date_of_birth')
        prob  = request.form.get('probation_end')
        contr = request.form.get('contract_end')
        emp.date_of_birth  = date.fromisoformat(dob) if dob else emp.date_of_birth
        emp.probation_end  = date.fromisoformat(prob) if prob else emp.probation_end
        emp.contract_end   = date.fromisoformat(contr) if contr else emp.contract_end
        db.session.commit()
        flash('Employee updated!', 'success')
        return redirect(url_for('employee.detail', emp_id=emp_id))
    return render_template('employee/edit.html', emp=emp, user=user, depts=depts)
