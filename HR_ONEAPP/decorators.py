from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('user_role') != 'admin':
            flash('Admin access only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated

def admin_or_hr_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('user_role') not in ('admin', 'hr'):
            flash('HR or Admin access only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def floor_events_by_joining(events, joining_date):
    """Drop any calendar event dated before an employee's joining date.

    Applied to an employee/HR person's OWN data across every calendar feed
    (attendance, meetings, tasks, payroll, leave) — someone shouldn't see
    or act on company history that predates their own employment. This is
    intentionally NOT applied to an admin's aggregate, all-employee view:
    admin needs full visibility to administer the system (audit past
    records, review old requests), so the floor only ever restricts what
    a person sees of their own personal timeline.

    `events` is the list-of-dicts shape every /api/calendar feed already
    returns (each with a 'start': 'YYYY-MM-DD' key). `joining_date` is a
    `date` object or None. Returns the same shape, just filtered.
    """
    if not joining_date:
        return events
    floor = joining_date.isoformat()
    return [e for e in events if e.get('start', '9999-99-99') >= floor]
