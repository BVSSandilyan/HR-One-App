"""
Admin Registration Approval Routes
===================================
Handles the full approval workflow for pending Employee/HR registrations:

  GET  /admin/registrations           — list all pending (and recent) requests
  GET  /admin/registrations/<id>      — view detail for one user (no secrets exposed)
  POST /admin/registrations/<id>/approve  — approve, activate, notify
  POST /admin/registrations/<id>/reject   — reject with optional reason, notify

Every route is protected by @admin_required on the backend — the frontend
confirmation dialogs are UX, not security. All writes are idempotent: a
second approve/reject on an already-reviewed account is a no-op with a
clear flash message rather than a server error.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decorators import admin_required
from models import db, User, Notification
from datetime import datetime

admin_approval_bp = Blueprint('admin_approval', __name__, url_prefix='/admin')


@admin_approval_bp.route('/registrations')
@admin_required
def registrations():
    """All registration requests, newest first, grouped by status so admin
    can see what needs action without scrolling past already-reviewed rows."""
    pending  = User.query.filter_by(approval_status='pending').order_by(
                   User.created_at.desc()).all()
    approved = User.query.filter(User.approval_status == 'approved',
                                 User.role != 'admin').order_by(
                   User.approved_at.desc()).limit(20).all()
    rejected = User.query.filter_by(approval_status='rejected').order_by(
                   User.created_at.desc()).limit(20).all()
    return render_template('admin/registrations.html',
                           pending=pending, approved=approved, rejected=rejected)


@admin_approval_bp.route('/registrations/<int:user_id>')
@admin_required
def registration_detail(user_id):
    """Detail view for one registration request.
    NEVER exposes password_hash, password, tokens, or other secrets — only
    safe fields (name, email, role, created_at, approval_status) are
    passed to the template."""
    user = User.query.get_or_404(user_id)
    # Build a safe dict — do NOT pass the ORM object directly to the
    # template, because the template could inadvertently (or deliberately)
    # access user.password_hash via dot notation. Requirement 12.
    safe_user = {
        'id':              user.id,
        'name':            user.name,
        'email':           user.email,
        'role':            user.role,
        'created_at':      user.created_at,
        'approval_status': user.approval_status,
        'approved_at':     user.approved_at,
        'rejection_reason':user.rejection_reason,
    }
    return render_template('admin/registration_detail.html', user=safe_user)


@admin_approval_bp.route('/registrations/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve(user_id):
    """Approve a pending registration.

    Idempotent: approving an already-approved account is a no-op (flash +
    redirect) rather than an error. This prevents race conditions if two
    admins both click Approve in quick succession (requirement 26).
    """
    user = User.query.get_or_404(user_id)

    # Guard: only pending accounts can be approved.
    if user.approval_status != 'pending':
        flash(f'{user.name}\'s account has already been '
              f'{user.approval_status}. No change made.', 'warning')
        return redirect(url_for('admin_approval.registrations'))

    # Guard: never approve an admin-role account through this flow — those
    # are created directly, not via the public registration form.
    if user.role == 'admin':
        flash('Admin accounts cannot be managed through this workflow.', 'danger')
        return redirect(url_for('admin_approval.registrations'))

    user.approval_status = 'approved'
    user.is_active       = True
    user.approved_by     = session['user_id']
    user.approved_at     = datetime.utcnow()

    # Notify the approved user so they know they can now log in.
    db.session.add(Notification(
        user_id=user.id,
        message=(f'✅ Your registration as {user.role.capitalize()} has been '
                 f'approved by the Admin. You can now log in to HR ONEAPP.'),
        type='info',
        ref_id=None
    ))
    db.session.commit()

    flash(f'{user.name}\'s account has been approved. They can now log in.', 'success')
    return redirect(url_for('admin_approval.registrations'))


@admin_approval_bp.route('/registrations/<int:user_id>/reject', methods=['POST'])
@admin_required
def reject(user_id):
    """Reject a pending registration with an optional reason.

    Idempotent on the same terms as approve(). The rejection reason is
    stored so it can be shown to the user in their login error message
    (requirement 19) without exposing any authentication secrets.
    """
    user = User.query.get_or_404(user_id)

    if user.approval_status != 'pending':
        flash(f'{user.name}\'s account has already been '
              f'{user.approval_status}. No change made.', 'warning')
        return redirect(url_for('admin_approval.registrations'))

    if user.role == 'admin':
        flash('Admin accounts cannot be managed through this workflow.', 'danger')
        return redirect(url_for('admin_approval.registrations'))

    reason = request.form.get('reason', '').strip()

    user.approval_status  = 'rejected'
    user.is_active        = False   # already False, but explicit for clarity
    user.approved_by      = session['user_id']   # reusing approved_by for the reviewing admin
    user.approved_at      = datetime.utcnow()
    user.rejection_reason = reason or None

    reason_part = f' Reason: {reason}' if reason else ''
    db.session.add(Notification(
        user_id=user.id,
        message=(f'❌ Your registration request was not approved.{reason_part} '
                 f'Please contact HR for further assistance.'),
        type='info',
        ref_id=None
    ))
    db.session.commit()

    flash(f'{user.name}\'s registration has been rejected.', 'info')
    return redirect(url_for('admin_approval.registrations'))
