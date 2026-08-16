from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decorators import login_required, admin_required, floor_events_by_joining
from models import db, Task, User, Employee, Notification
from datetime import datetime, date

task_bp = Blueprint('task', __name__, url_prefix='/task')


@task_bp.route('/')
@login_required
def index():
    uid, role = session['user_id'], session['user_role']
    page = request.args.get('page', 1, type=int)
    q = Task.query.order_by(Task.created_at.desc()) if role == 'admin' \
        else Task.query.filter_by(assigned_to=uid).order_by(Task.created_at.desc())
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    tasks = pagination.items
    return render_template('task/index.html', tasks=tasks, role=role, pagination=pagination)


@task_bp.route('/api/calendar')
@login_required
def calendar_feed():
    uid, role = session['user_id'], session['user_role']
    tasks = Task.query.all() if role == 'admin' else Task.query.filter_by(assigned_to=uid).all()
    events = []
    for t in tasks:
        if not t.due_date:
            continue
        color = '#dc2626' if t.is_overdue else (
            '#16a34a' if t.status == 'completed' else
            '#2563eb' if t.status == 'in-progress' else '#d97706')
        events.append({
            'title': t.title, 'start': t.due_date.strftime('%Y-%m-%d'),
            'color': color, 'category': 'Overdue' if t.is_overdue else t.status.replace('-', ' ').title(),
            'task_id': t.id
        })

    if role != 'admin':
        emp = Employee.query.filter_by(user_id=uid).first()
        if emp:
            events = floor_events_by_joining(events, emp.date_of_joining)

    return jsonify(events)


@task_bp.route('/assign', methods=['GET', 'POST'])
@admin_required
def assign():
    users = User.query.filter(User.role.in_(['employee', 'hr']), User.is_active == True).all()
    if request.method == 'POST':
        title, desc = request.form.get('title'), request.form.get('description')
        to_id, due  = request.form.get('assigned_to'), request.form.get('due_date')
        priority    = request.form.get('priority', 'medium')

        task = Task(title=title, description=desc, assigned_by=session['user_id'],
                    assigned_to=int(to_id),
                    due_date=datetime.strptime(due, '%Y-%m-%d').date() if due else None,
                    priority=priority)
        db.session.add(task)
        db.session.flush()
        db.session.add(Notification(user_id=int(to_id),
                        message=f'📋 New task assigned: "{title}" | Priority: {priority}',
                        type='task', ref_id=task.id))
        db.session.commit()
        flash('Task assigned and employee notified!', 'success')
        return redirect(url_for('task.index'))
    return render_template('task/assign.html', users=users)


@task_bp.route('/update/<int:task_id>', methods=['POST'])
@login_required
def update_status(task_id):
    task = Task.query.get_or_404(task_id)
    if task.assigned_to != session['user_id'] and session['user_role'] != 'admin':
        flash('Not authorized.', 'danger')
        return redirect(url_for('task.index'))
    task.status, task.updated_at = request.form.get('status', task.status), datetime.utcnow()
    db.session.commit()
    flash('Task updated!', 'success')
    return redirect(url_for('task.index'))


@task_bp.route('/reschedule/<int:task_id>', methods=['POST'])
@login_required
def reschedule(task_id):
    """Reserved endpoint — calendar is currently read-only, kept for future drag-and-drop."""
    task = Task.query.get_or_404(task_id)
    if session['user_role'] != 'admin' and task.assigned_to != session['user_id']:
        return jsonify({'status': 'error', 'message': 'Not authorized'}), 403
    new_date = request.json.get('due_date') if request.is_json else request.form.get('due_date')
    if new_date:
        task.due_date = date.fromisoformat(new_date)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400
