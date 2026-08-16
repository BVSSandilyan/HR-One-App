# HR ONEAPP

**An Integrated Employee Management & Workforce Operations Platform**

A full-stack HR management system built with Flask, SQLAlchemy, and SQLite that unifies attendance, leave, payroll, meetings, tasks, and real-time video conferencing into one role-aware platform. Every administrative action — approving leave, starting a meeting, assigning salary — automatically propagates across all connected modules without requiring duplicate data entry.

---

## Main Features

| Module | What it does |
|---|---|
| **Admin Approval Workflow** | New Employee/HR registrations require Admin approval before login is granted |
| **Role-Based Dashboards** | Admin, HR, and Employee each see a tailored dashboard and permission set |
| **Video Meetings** | Real-time video/audio via WebRTC; screen sharing; mic/camera controls; scheduled future meetings |
| **Leave Management** | 20-day annual balance (half-day = 0.5); overlap detection; admin approve/reject with salary deduction for excess |
| **Attendance** | Admin marks daily attendance; auto-marked via approved leave; calendar heatmap |
| **Payroll** | Admin assigns salary; dashboard widget auto-calculates leave-based deductions (1.67 days/month allowance) |
| **Tasks** | Admin assigns tasks with priority/due date; real-time bell notifications |
| **Calendar** | Unified read-only calendar on every module page (attendance, meetings, tasks, payroll, leave, employee) |
| **Notifications** | Live bell with unread count; quick approve/reject for leave and registrations from the dropdown |
| **Light/Dark Mode** | Session-persisted toggle; no database change needed |

---

## Technologies Used

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask 3.0, Flask-SQLAlchemy, Flask-SocketIO |
| Database | SQLite (file-based, zero config) |
| Real-time | Socket.IO 5.x (WebSocket + polling fallback), WebRTC mesh topology |
| WebRTC async | gevent + gevent-websocket |
| Frontend | Jinja2 templates, Vanilla JS, CSS custom properties (light + dark theme) |
| Scheduling | Python `threading` background poller (auto-starts scheduled meetings) |

---

## Project Structure

```
HR_ONEAPP/
├── app.py                          # App factory, SocketIO init, blueprint registration
├── models.py                       # SQLAlchemy models (User, Employee, Leave, Payroll, ...)
├── signal_handlers.py              # WebRTC signaling relay via Socket.IO
├── scheduler.py                    # Background thread: auto-activates scheduled meetings
├── decorators.py                   # login_required, admin_required, floor_events_by_joining
├── seed_admin.py                   # One-time script: creates the default Admin account
├── requirements.txt
│
├── routes/
│   ├── __init__.py
│   ├── auth.py                     # Login, register, logout (approval-status aware)
│   ├── dashboard.py                # Dashboard + salary-by-leave widget
│   ├── meeting.py                  # Meeting CRUD, join/leave, room, media-state REST
│   ├── attendance.py               # Mark attendance, holiday management, calendar feed
│   ├── leave.py                    # Apply, approve, reject, overlap check, calendar feed
│   ├── payroll.py                  # Assign salary, mark paid, calendar feed
│   ├── task.py                     # Assign tasks, update status, calendar feed
│   ├── employee.py                 # Employee list, detail, edit
│   └── admin_approval.py           # Registration list, detail, approve, reject
│
├── templates/
│   ├── base.html                   # Sidebar, topbar, dark-mode toggle, notification bell
│   ├── auth/                       # login.html, register.html
│   ├── dashboard/index.html        # Stats, tasks, quick actions, salary widget, calendar
│   ├── meeting/
│   │   ├── list.html
│   │   ├── start.html              # Immediate or future-dated meeting scheduling
│   │   ├── room.html               # WebRTC room: mic, camera, screen share, VAD
│   │   └── manage.html             # Admin: mark meeting attendance
│   ├── leave/
│   │   ├── apply.html              # Half-day support, date constraints, balance display
│   │   ├── index.html              # List + calendar; admin sees approve/reject buttons
│   │   └── confirm_approve.html    # Over-balance: admin enters ₹200–500 deduction rate
│   ├── attendance/, payroll/, task/, employee/, admin/
│   └── _pagination.html
│
└── static/
    ├── css/style.css               # Full light/dark theme via CSS custom properties
    └── js/
        ├── app.js                  # Notifications bell, dark-mode toggle, quick-actions
        └── calendar.js             # Read-only calendar widget (timezone-safe dateKey)
```

---

## Installation Requirements

- **Python 3.10 or higher**
- **pip** (comes with Python)
- A modern browser: Chrome 90+, Firefox 88+, Edge 90+ (required for WebRTC)
- **HTTPS or localhost** — browsers only grant camera/mic/screen access on secure origins. `127.0.0.1:5000` qualifies as a secure origin and works without a certificate.

---

## Installation & Setup

### 1. Extract the ZIP

```bash
unzip HR_ONEAPP.zip
cd HR_ONEAPP
```

### 2. (Optional) Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate          # Mac / Linux
venv\Scripts\activate             # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, Flask-SQLAlchemy, Flask-SocketIO, gevent, gevent-websocket, and Werkzeug.

### 4. Create the Admin account

Run this **once** before starting the server:

```bash
python seed_admin.py
```

Output:
```
✅ Admin account created.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Email    : admin@gmail.com
  Password : admin@123
  URL      : http://127.0.0.1:5000
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> **Note:** Admin accounts cannot be created through the public Register page by design. Only `seed_admin.py` (or a direct DB insert) can create an Admin.

---

## Running the Application

```bash
python app.py
```

Expected output:
```
All tables ready.
 * Running on http://0.0.0.0:5000
```

Open **http://127.0.0.1:5000** in your browser.

> **Important:** Always run with `python app.py`, not `flask run`. The app uses `socketio.run()` internally, which starts the gevent server needed for WebSocket support. `flask run` bypasses this and breaks real-time features.

---

## Environment Variables / Configuration

No `.env` file is required for local development. All defaults are set in `app.py`:

| Setting | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `hr-oneapp-secret-2024` | Change before deploying to production |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///hr_oneapp.db` | File created automatically on first run |
| `DEBUG` | `True` | Set `False` in production |

---

## How to Use the App

### Workflow for a new Employee/HR

1. Go to `/register`, fill in name, email, role (Employee or HR), and password
2. Account is created with `is_active = False` and `approval_status = pending`
3. A notification appears in the Admin's bell and the Registrations sidebar item
4. Admin logs in → clicks **Registrations** → reviews → clicks **Approve** or **Reject**
5. Employee/HR receives a notification and can now log in

### Admin Credentials (after running seed_admin.py)

| Field | Value |
|---|---|
| Email | `admin@gmail.com` |
| Password | `admin@123` |

---

## Meeting & Video Conferencing

### Starting a Meeting

1. Log in as Admin
2. Go to **Meetings → Start Meeting**
3. Enter a title and optionally a future date to schedule it
4. Click **Start & Notify All** — all Employees and HR receive a bell notification with a Join link

### Joining a Meeting

1. Click the notification or go to **Meetings → Join** on any active meeting
2. The meeting room opens with mic/camera/screen-share controls

### Controls in the Room

| Button | Function |
|---|---|
| 🎤 Unmute / Mute | Toggle your microphone |
| 📷 Camera | Toggle your webcam |
| 🔊 Speaker | Mute/unmute incoming audio |
| 🖥️ Share | Start/stop screen sharing |
| 👥 People | Show/hide participant list with live mic/cam indicators |
| 📞 Leave | Exit the meeting cleanly |

### How Real-Time Video/Audio Works

The app uses a **WebRTC mesh topology** with a Socket.IO signaling relay:

```
Browser A ──offer/answer/ICE──▶ Flask-SocketIO (signal_handlers.py) ──▶ Browser B
                                  (relay only — no media passes through server)
Browser A ◀──────────── direct RTP/SRTP media ────────────────────────▶ Browser B
```

- `signal_handlers.py` relays offer, answer, and ICE candidates between peers
- Actual audio/video/screen data flows **peer-to-peer** — the server is not in the media path
- STUN servers (Google public) are used for NAT traversal on the same network

### WebRTC / Browser Requirements

| Requirement | Details |
|---|---|
| Secure origin | Mic/camera/screen require HTTPS or `localhost`/`127.0.0.1` |
| Camera permission | Optional — mic works without a camera |
| Screen share | Chrome/Edge: full screen, window, or tab; Firefox: requires user gesture |
| Same network | Public STUN servers handle same-LAN connections. Cross-internet requires a TURN server |

### Adding a TURN Server (for cross-network meetings)

Edit the `RTC_CONFIG` block near the top of `templates/meeting/room.html`:

```js
const RTC_CONFIG = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    {
      urls:       'turn:your-turn-server.com:3478',
      username:   'your-username',
      credential: 'your-password'
    }
  ]
};
```

Free TURN providers: [Metered.ca](https://www.metered.ca/tools/openrelay/), [Twilio](https://www.twilio.com/docs/stun-turn).

---

## Testing Instructions

### Manual Functional Test

1. Open two browser windows (or use Chrome + an incognito window)
2. Log in as Admin in one and as an approved Employee in the other
3. Admin starts a meeting from **Meetings → Start Meeting**
4. Employee clicks the notification or joins from the Meetings list

**Verify the following:**

| Test | Expected |
|---|---|
| Admin shares screen | Employee sees the screen in their video grid |
| Employee shares screen | Admin sees the screen; tile expands to full width |
| Stop screen share | Normal camera tiles restore for both participants |
| Admin unmutes mic | Employee hears audio (🎤 icon turns on in participant panel) |
| Employee unmutes mic | Admin hears audio |
| Mute mic | Speaker icon shows muted; other participant's audio icon updates |
| Leave and rejoin | Peer tile is removed on leave; new peer connection on rejoin |
| Admin ends meeting | Everyone is redirected to the meetings list |

### Running the Server in Debug Mode (logs all socket events)

```bash
python app.py
```

Socket.IO and WebRTC events are printed to the terminal, including connection state changes and ICE negotiation logs visible in the browser console (F12 → Console).

---

## Common Errors & Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: flask_socketio` | Flask-SocketIO not installed | `pip install -r requirements.txt` |
| `ModuleNotFoundError: gevent` | Gevent not installed | `pip install gevent gevent-websocket` |
| Mic/camera not working | Browser blocked permissions | Click the 🔒 lock icon in the address bar and allow camera/microphone |
| Screen share not appearing for others | Using `flask run` instead of `python app.py` | Always use `python app.py` |
| "Account pending Admin approval" on login | Account not yet approved | Admin must approve via Registrations page |
| Participants can't hear each other | Cross-network without TURN | Add a TURN server to `RTC_CONFIG` in `room.html` |
| `gevent` SSL errors on Windows | OpenSSL version mismatch | Install `pyopenssl`: `pip install pyopenssl` |
| DB locked error | Multiple processes | Only run one `python app.py` at a time |
| WebRTC `ICE failed` in console | Firewall blocking UDP | Ensure UDP ports 3478 and 49152–65535 are open, or use TURN |

---

## Important Notes for Development & Deployment

### Development
- The SQLite database file `hr_oneapp.db` is created automatically in the `instance/` folder on first run
- `seed_admin.py` is safe to re-run — it updates existing admin credentials rather than creating duplicates
- The background scheduler thread (auto-activates scheduled meetings) starts once and runs in the background; no separate process needed

### Production
- Replace `SECRET_KEY` with a cryptographically random value: `python -c "import secrets; print(secrets.token_hex(32))"`
- Switch from SQLite to PostgreSQL or MySQL for concurrent users by changing `SQLALCHEMY_DATABASE_URI`
- Run behind a reverse proxy (nginx/Caddy) with HTTPS — required for camera/mic/screen-share in production
- Use `gunicorn` with `geventwebsocket` worker: `gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker app:app`
- Deploy a TURN server for participants on different networks
- Set `DEBUG = False` in `app.py` before deploying

### Admin Account
- Only create Admin accounts via `seed_admin.py` or direct DB commands — the public Register page intentionally prevents Admin self-registration
- The first Admin account must be created before anyone else can register and be approved

---

## License

This project was built for educational and demonstration purposes.
