from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from decorators import login_required, admin_required, floor_events_by_joining
from models import db, Meeting, MeetingParticipant, Notification, User, Employee, Attendance, LeaveRequest
from datetime import datetime, date

meeting_bp = Blueprint('meeting', __name__, url_prefix='/meeting')

# In-memory mic/cam presence per meeting: {meeting_id: {user_id: {...}}}
_media_states = {}


@meeting_bp.route('/')
@login_required
def list_meetings():
    q = Meeting.query
    # Non-admins must never see a meeting that hasn't gone live yet — same
    # rule the calendar feed already applies. Admin sees everything,
    # including their own still-pending scheduled meetings, since they
    # need to be able to find and manage what they scheduled.
    if session.get('user_role') != 'admin':
        q = q.filter(Meeting.status != 'scheduled')
    meetings = q.order_by(Meeting.started_at.desc()).all()
    return render_template('meeting/list.html', meetings=meetings)


@meeting_bp.route('/api/calendar')
@login_required
def calendar_feed():
    events = []
    for m in Meeting.query.all():
        # A meeting scheduled for a future date shouldn't appear on anyone's
        # calendar except the admin who scheduled it — non-admins only ever
        # see it once it's actually live (the before_request hook in app.py
        # flips status to 'active' and fires the join-notification on the
        # day it's due).
        if m.status == 'scheduled' and session.get('user_role') != 'admin':
            continue
        display_date = m.scheduled_date or m.started_at.date()
        events.append({
            'title': f'{m.title}' + (' (scheduled)' if m.status == 'scheduled' else ''),
            'start': display_date.strftime('%Y-%m-%d'),
            'color': '#64748b' if m.status == 'scheduled' else ('#1d4ed8' if m.status == 'active' else '#94a3b8'),
            'category': 'Meeting',
            'meeting_id': m.id,
            'status': m.status,
            'recurring': m.is_recurring
        })

    if session.get('user_role') != 'admin':
        emp = Employee.query.filter_by(user_id=session['user_id']).first()
        if emp:
            events = floor_events_by_joining(events, emp.date_of_joining)

    return jsonify(events)


@meeting_bp.route('/start', methods=['GET', 'POST'])
@admin_required
def start():
    if request.method == 'POST':
        title          = request.form.get('title')
        description    = request.form.get('description')
        link           = request.form.get('meeting_link', '')
        recurring      = request.form.get('is_recurring') == 'on'
        recurrence     = request.form.get('recurrence', '')
        scheduled_date = request.form.get('scheduled_date', '').strip()

        today = date.today()
        is_future = bool(scheduled_date) and date.fromisoformat(scheduled_date) > today

        if is_future:
            # Date-fixed meeting: created now, but stays invisible/inactive
            # to everyone except the admin who scheduled it until the
            # background scheduler (scheduler.py) flips it live on the
            # given date and fires the join notification then — not now.
            meeting = Meeting(
                title=title, description=description,
                started_by=session['user_id'], meeting_link=link,
                status='scheduled', is_recurring=recurring,
                recurrence=recurrence if recurring else None,
                scheduled_date=date.fromisoformat(scheduled_date)
            )
            db.session.add(meeting)
            db.session.commit()
            flash(f'Meeting "{title}" scheduled for '
                  f'{date.fromisoformat(scheduled_date).strftime("%d %b %Y")}. '
                  f'Everyone will be notified automatically on that date.', 'success')
            return redirect(url_for('meeting.list_meetings'))

        # Immediate start (also covers a "scheduled_date" of today/blank —
        # there's no reason to wait for the poller when it's already due).
        meeting = Meeting(
            title=title, description=description,
            started_by=session['user_id'], meeting_link=link,
            status='active', is_recurring=recurring,
            recurrence=recurrence if recurring else None,
            scheduled_date=date.fromisoformat(scheduled_date) if scheduled_date else None
        )
        db.session.add(meeting)
        db.session.flush()

        all_users = User.query.filter(
            User.role.in_(['employee', 'hr']), User.is_active == True
        ).all()
        for u in all_users:
            db.session.add(Notification(
                user_id=u.id, message=f'📹 Meeting started: "{title}". Click to join!',
                type='meeting', ref_id=meeting.id
            ))
            db.session.add(MeetingParticipant(meeting_id=meeting.id, user_id=u.id, attendance='absent'))

        db.session.add(MeetingParticipant(
            meeting_id=meeting.id, user_id=session['user_id'],
            joined_at=datetime.utcnow(), attendance='present'
        ))
        db.session.commit()

        flash(f'Meeting "{title}" started! All employees and HR notified.', 'success')
        return redirect(url_for('meeting.room', meeting_id=meeting.id))
    return render_template('meeting/start.html', today=date.today().isoformat())


@meeting_bp.route('/<int:meeting_id>/room')
@login_required
def room(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status != 'active':
        if meeting.status == 'scheduled':
            flash(f'This meeting is fixed for {meeting.scheduled_date.strftime("%d %b %Y")} '
                  f'and hasn\'t started yet.', 'warning')
        else:
            flash('This meeting has ended.', 'warning')
        return redirect(url_for('meeting.list_meetings'))

    p = MeetingParticipant.query.filter_by(meeting_id=meeting_id, user_id=session['user_id']).first()
    if p:
        if not p.joined_at:
            p.joined_at, p.attendance = datetime.utcnow(), 'present'
            db.session.commit()
    else:
        db.session.add(MeetingParticipant(
            meeting_id=meeting_id, user_id=session['user_id'],
            joined_at=datetime.utcnow(), attendance='present'
        ))
        db.session.commit()

    notif = Notification.query.filter_by(
        user_id=session['user_id'], type='meeting', ref_id=meeting_id, is_read=False).first()
    if notif:
        notif.is_read = True
        db.session.commit()

    participants = MeetingParticipant.query.filter_by(meeting_id=meeting_id).all()
    return render_template('meeting/room.html', meeting=meeting, participants=participants)


@meeting_bp.route('/<int:meeting_id>/join', methods=['POST', 'GET'])
@login_required
def join(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status != 'active':
        if meeting.status == 'scheduled':
            flash(f'This meeting is fixed for {meeting.scheduled_date.strftime("%d %b %Y")} '
                  f'and hasn\'t started yet.', 'warning')
        else:
            flash('Meeting is no longer active.', 'danger')
        return redirect(url_for('meeting.list_meetings'))
    return redirect(url_for('meeting.room', meeting_id=meeting_id))


@meeting_bp.route('/<int:meeting_id>/leave', methods=['POST'])
@login_required
def leave_room(meeting_id):
    mid, uid = str(meeting_id), str(session['user_id'])
    if mid in _media_states and uid in _media_states[mid]:
        del _media_states[mid][uid]
    flash('You have left the meeting.', 'info')
    return redirect(url_for('meeting.list_meetings'))


@meeting_bp.route('/state/<int:meeting_id>', methods=['GET', 'POST'])
@login_required
def media_state(meeting_id):
    """Presence/mic/cam state board. Local-preview only — no actual media is relayed server-side."""
    mid = str(meeting_id)
    _media_states.setdefault(mid, {})

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        uid = str(session['user_id'])
        _media_states[mid][uid] = {
            'user_id': session['user_id'],
            'name':    session['user_name'],
            'role':    session['user_role'],
            'mic':     bool(data.get('mic', False)),
            'cam':     bool(data.get('cam', False)),
        }
        return jsonify({'status': 'ok'})

    return jsonify(list(_media_states.get(mid, {}).values()))


@meeting_bp.route('/<int:meeting_id>/cancel-scheduled', methods=['POST'])
@admin_required
def cancel_scheduled(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status != 'scheduled':
        flash('This meeting is no longer pending — it may have already started.', 'warning')
        return redirect(url_for('meeting.list_meetings'))
    meeting.status = 'ended'
    meeting.ended_at = datetime.utcnow()
    db.session.commit()
    flash(f'Scheduled meeting "{meeting.title}" was cancelled.', 'info')
    return redirect(url_for('meeting.list_meetings'))


@meeting_bp.route('/<int:meeting_id>/manage')
@admin_required
def manage(meeting_id):
    meeting      = Meeting.query.get_or_404(meeting_id)
    participants = MeetingParticipant.query.filter_by(meeting_id=meeting_id).all()
    return render_template('meeting/manage.html', meeting=meeting, participants=participants)


@meeting_bp.route('/<int:meeting_id>/mark', methods=['POST'])
@admin_required
def mark_attendance(meeting_id):
    meeting     = Meeting.query.get_or_404(meeting_id)
    present_ids = request.form.getlist('present')
    today       = date.today()

    for p in MeetingParticipant.query.filter_by(meeting_id=meeting_id).all():
        p.attendance = 'present' if str(p.user_id) in present_ids else 'absent'
        p.marked_by  = session['user_id']

        emp = Employee.query.filter_by(user_id=p.user_id).first()
        if emp:
            status   = 'present' if str(p.user_id) in present_ids else 'absent'
            existing = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
            if existing:
                existing.status, existing.marked_by = status, session['user_id']
            else:
                db.session.add(Attendance(employee_id=emp.id, date=today,
                                           status=status, marked_by=session['user_id']))
    db.session.commit()
    flash('Attendance marked successfully!', 'success')
    return redirect(url_for('meeting.manage', meeting_id=meeting_id))


@meeting_bp.route('/<int:meeting_id>/end', methods=['POST'])
@admin_required
def end_meeting(meeting_id):
    meeting          = Meeting.query.get_or_404(meeting_id)
    meeting.status   = 'ended'
    meeting.ended_at = datetime.utcnow()
    _media_states.pop(str(meeting_id), None)
    db.session.commit()
    flash('Meeting ended.', 'info')
    return redirect(url_for('meeting.list_meetings'))


@meeting_bp.route('/notifications')
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(
        user_id=session['user_id'], is_read=False
    ).order_by(Notification.created_at.desc()).all()

    result = []
    for n in notifs:
        item = {'id': n.id, 'message': n.message, 'type': n.type,
                 'ref_id': n.ref_id, 'created_at': str(n.created_at)}
        # For a pending leave notification, tell the bell dropdown whether
        # approving it would exceed the employee's remaining balance — so
        # it can route to the full review page (where a deduction rate can
        # be entered) instead of one-click approving blind with no way to
        # collect that rate in the cramped dropdown UI.
        if n.type == 'leave' and n.ref_id:
            lr = LeaveRequest.query.get(n.ref_id)
            if lr and lr.status == 'pending':
                emp = Employee.query.get(lr.employee_id)
                consumed = 0.5 if lr.leave_type == 'half-day' else (lr.to_date - lr.from_date).days + 1
                item['exceeds_balance'] = bool(emp) and consumed > emp.leave_balance
        result.append(item)
    return jsonify(result)


@meeting_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if n.user_id == session['user_id']:
        n.is_read = True
        db.session.commit()
    return jsonify({'status': 'ok'})
