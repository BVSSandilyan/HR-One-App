"""
Background poller for date-fixed ("schedule for later") meetings.

Why this exists: a meeting scheduled for a future date needs to flip from
'scheduled' to 'active' and notify every employee/HR on that date, WITHOUT
requiring any human to be browsing the app at that moment. A Flask
before_request hook would only fire when someone happens to make a
request — if nobody opens the app on the scheduled day, the meeting would
silently never start. A standard-library background thread that wakes up
on its own interval is the minimal way to get a real "fires on the date
regardless of traffic" guarantee without adding a new dependency
(APScheduler/Celery) for a single feature.

Idempotency: the poller runs repeatedly forever, so the activation logic
must be safe to "miss seeing" a meeting that was already activated by a
previous tick. `Meeting.notified_at` is the guard — only act on rows where
it's still NULL, and the very first thing the activation does is stamp it,
before the notification loop runs. This means even if two ticks somehow
overlapped, the second would see notified_at already set and skip.
"""

import threading
import time
from datetime import datetime, date


def _activate_due_meetings(app):
    """One poll cycle: find scheduled meetings whose date has arrived and
    turn them into live, notified meetings — using the exact same
    participant + notification creation shape that meeting.start() uses
    for an immediate meeting, so a scheduled meeting behaves identically
    to a manually-started one from the moment it goes live."""
    from models import db, Meeting, MeetingParticipant, Notification, User

    with app.app_context():
        today = date.today()
        due = Meeting.query.filter(
            Meeting.status == 'scheduled',
            Meeting.scheduled_date <= today,
            Meeting.notified_at.is_(None)
        ).all()

        for meeting in due:
            meeting.status      = 'active'
            meeting.started_at  = datetime.utcnow()
            meeting.notified_at = datetime.utcnow()

            all_users = User.query.filter(
                User.role.in_(['employee', 'hr']), User.is_active == True
            ).all()
            for u in all_users:
                db.session.add(Notification(
                    user_id=u.id,
                    message=f'📹 Scheduled meeting is starting now: "{meeting.title}". Click to join!',
                    type='meeting', ref_id=meeting.id
                ))
                existing_p = MeetingParticipant.query.filter_by(
                    meeting_id=meeting.id, user_id=u.id).first()
                if not existing_p:
                    db.session.add(MeetingParticipant(
                        meeting_id=meeting.id, user_id=u.id, attendance='absent'))

            # The admin who scheduled it is also a participant, marked present
            # immediately — matches how an immediately-started meeting treats
            # its starter in meeting.start().
            starter_p = MeetingParticipant.query.filter_by(
                meeting_id=meeting.id, user_id=meeting.started_by).first()
            if starter_p:
                starter_p.joined_at, starter_p.attendance = datetime.utcnow(), 'present'
            else:
                db.session.add(MeetingParticipant(
                    meeting_id=meeting.id, user_id=meeting.started_by,
                    joined_at=datetime.utcnow(), attendance='present'
                ))

        if due:
            db.session.commit()


def start_meeting_scheduler(app, interval_seconds=30):
    """Launch the poller as a daemon thread once, at app startup.

    daemon=True so the thread never blocks process shutdown. A 30-second
    interval is frequent enough that a meeting "starts on its date" with
    at most a 30-second lag — far tighter than the day-level granularity
    the feature actually needs, while still being cheap (one small query
    per tick, almost always returning zero rows).
    """
    def _loop():
        while True:
            try:
                _activate_due_meetings(app)
            except Exception as e:
                # A transient DB error here must never kill the polling
                # thread permanently — log and keep trying on the next tick.
                print(f'[meeting_scheduler] poll error: {e}')
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread
