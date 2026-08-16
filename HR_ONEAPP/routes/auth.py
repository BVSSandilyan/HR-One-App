from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User, Employee, Notification
from datetime import datetime
import random, string

auth_bp = Blueprint('auth', __name__)

def gen_code():
    return 'EMP' + ''.join(random.choices(string.digits, k=5))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')

        # Look up by email regardless of is_active so we can produce a
        # meaningful message for pending/rejected accounts rather than the
        # generic "Invalid email or password" that gives nothing away.
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            # Check approval status first, before checking is_active,
            # so pending and rejected users see a specific message rather
            # than the generic "Invalid email or password".
            if user.approval_status == 'pending':
                flash('Your account is pending Admin approval. You will be '
                      'notified by email once it has been reviewed.', 'warning')
                return render_template('auth/login.html')

            if user.approval_status == 'rejected':
                reason_part = (f' Reason: {user.rejection_reason}'
                               if user.rejection_reason else '')
                flash(f'Your registration was not approved.{reason_part} '
                      f'Please contact HR for assistance.', 'danger')
                return render_template('auth/login.html')

            if not user.is_active:
                # Catch-all for any other inactive state (manually disabled
                # accounts, etc.) so the message stays meaningful.
                flash('Your account has been deactivated. Please contact '
                      'the administrator.', 'danger')
                return render_template('auth/login.html')

            session['user_id']   = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard.index'))

        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        name     = request.form.get('name')
        email    = request.form.get('email')
        password = request.form.get('password')
        confirm  = request.form.get('confirm')
        role     = request.form.get('role', 'employee')

        # Requirement 6: public registration must never create an Admin.
        # Even if someone edits the form HTML to insert role=admin, this
        # server-side guard silently downgrades the value rather than
        # revealing that admin is a valid role to enumerate.
        if role == 'admin':
            role = 'employee'

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        # Employee and HR accounts start inactive and pending — they cannot
        # log in until an Admin explicitly approves them. is_active=False is
        # the hard gate the login query already checks; approval_status
        # carries the semantic reason so the login route can distinguish
        # "pending" from "rejected" and show the right message.
        user = User(
            name=name, email=email, role=role,
            is_active=False, approval_status='pending'
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        emp = Employee(user_id=user.id, employee_code=gen_code(),
                       date_of_joining=datetime.utcnow().date())
        db.session.add(emp)
        db.session.flush()

        # Notify every Admin immediately — they'll see it in the bell and
        # in the Registration Requests section of their dashboard.
        admins = User.query.filter_by(role='admin', is_active=True,
                                      approval_status='approved').all()
        for admin in admins:
            db.session.add(Notification(
                user_id=admin.id,
                message=(f'🆕 New registration request from {name} '
                         f'({email}) as {role.capitalize()}. '
                         f'Registered: {datetime.utcnow().strftime("%d %b %Y %H:%M")} — Pending approval.'),
                type='registration',
                ref_id=user.id   # ref_id points to the new user's id so the
                                  # admin can jump straight to the detail view
            ))

        db.session.commit()
        flash('Registration submitted! Your account is pending Admin approval. '
              'You will be notified once it has been reviewed.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
