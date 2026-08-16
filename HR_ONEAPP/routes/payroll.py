from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decorators import admin_required
from models import db, Payroll, Employee, User
from datetime import datetime, date

payroll_bp = Blueprint('payroll', __name__, url_prefix='/payroll')


@payroll_bp.route('/')
@admin_required
def index():
    page = request.args.get('page', 1, type=int)
    q = db.session.query(Payroll, Employee, User).join(
        Employee, Payroll.employee_id == Employee.id).join(
        User, Employee.user_id == User.id
    ).order_by(Payroll.year.desc(), Payroll.month.desc())
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    records = pagination.items
    return render_template('payroll/index.html', records=records, pagination=pagination)


@payroll_bp.route('/api/calendar')
@admin_required
def calendar_feed():
    events = []
    for p, emp, user in db.session.query(Payroll, Employee, User).join(
            Employee, Payroll.employee_id == Employee.id).join(
            User, Employee.user_id == User.id).all():
        join_floor = emp.date_of_joining.isoformat() if emp.date_of_joining else None
        pay_date = p.pay_date or date(p.year, p.month, 1)
        pay_event = {
            'title': f'💰 {user.name[:12]} ₹{p.net_salary:.0f}',
            'start': pay_date.strftime('%Y-%m-%d'),
            'color': '#16a34a' if p.status == 'paid' else '#d97706',
            'category': 'Salary'
        }
        if not join_floor or pay_event['start'] >= join_floor:
            events.append(pay_event)
        if p.tax_due_date:
            tax_event = {
                'title': f'🧾 Tax due — {user.name[:12]}',
                'start': p.tax_due_date.strftime('%Y-%m-%d'),
                'color': '#dc2626', 'category': 'Tax'
            }
            if not join_floor or tax_event['start'] >= join_floor:
                events.append(tax_event)
    for emp, user in db.session.query(Employee, User).join(User, Employee.user_id == User.id).all():
        if emp.date_of_joining:
            # Anniversary this year
            try:
                anniv = emp.date_of_joining.replace(year=date.today().year)
                events.append({
                    'title': f'🎉 {user.name[:12]} anniversary',
                    'start': anniv.strftime('%Y-%m-%d'),
                    'color': '#0891b2', 'category': 'Anniversary'
                })
            except ValueError:
                pass
    return jsonify(events)


@payroll_bp.route('/assign', methods=['GET', 'POST'])
@admin_required
def assign():
    employees = db.session.query(Employee, User).join(User, Employee.user_id == User.id).all()
    now = datetime.now()
    if request.method == 'POST':
        emp_id    = request.form.get('employee_id')
        month     = int(request.form.get('month'))
        year      = int(request.form.get('year'))
        basic     = float(request.form.get('basic_salary', 0))
        allowance = float(request.form.get('allowances', 0))
        deduction = float(request.form.get('deductions', 0))
        pay_date  = request.form.get('pay_date') or None
        tax_date  = request.form.get('tax_due_date') or None
        net       = basic + allowance - deduction

        existing = Payroll.query.filter_by(employee_id=emp_id, month=month, year=year).first()
        if existing:
            existing.basic_salary, existing.allowances, existing.deductions = basic, allowance, deduction
            existing.pay_date     = date.fromisoformat(pay_date) if pay_date else existing.pay_date
            existing.tax_due_date = date.fromisoformat(tax_date) if tax_date else existing.tax_due_date
            # Recompute net using whatever leave_deduction already sits on this
            # row (0.0 if the dashboard widget never touched it) — this manual
            # form must never silently wipe out a leave-driven deduction that
            # was already applied via the dashboard salary widget.
            existing.net_salary = basic + allowance - deduction - (existing.leave_deduction or 0.0)
        else:
            db.session.add(Payroll(
                employee_id=emp_id, month=month, year=year,
                basic_salary=basic, allowances=allowance, deductions=deduction, net_salary=net,
                pay_date=date.fromisoformat(pay_date) if pay_date else None,
                tax_due_date=date.fromisoformat(tax_date) if tax_date else None,
                created_by=session['user_id']
            ))

        emp = Employee.query.get(emp_id)
        if emp:
            emp.salary = basic

        db.session.commit()
        flash('Salary assigned successfully!', 'success')
        return redirect(url_for('payroll.index'))
    return render_template('payroll/assign.html', employees=employees,
                            months=range(1, 13), current_year=now.year, current_month=now.month)


@payroll_bp.route('/pay/<int:payroll_id>', methods=['POST'])
@admin_required
def mark_paid(payroll_id):
    p = Payroll.query.get_or_404(payroll_id)
    p.status, p.paid_on = 'paid', datetime.utcnow()
    db.session.commit()
    flash('Marked as paid!', 'success')
    return redirect(url_for('payroll.index'))
