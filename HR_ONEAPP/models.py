from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='employee')   # admin | hr | employee
    is_active     = db.Column(db.Boolean, default=True)
    # ── Registration approval workflow ──
    # Admin accounts are created pre-approved (approval_status='approved',
    # is_active=True). Employee and HR accounts start pending and inactive
    # until an Admin explicitly approves them. This column is the single
    # source of truth for the approval state; is_active mirrors it (False
    # while pending or rejected, True only when approved) but is kept as a
    # separate flag so the login guard can produce a meaningful error message
    # without having to re-derive the reason from is_active alone.
    approval_status  = db.Column(db.String(20), default='approved')  # approved|pending|rejected
    approved_by      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at      = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)


class Department(db.Model):
    __tablename__ = 'departments'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))
    employees   = db.relationship('Employee', backref='department', lazy=True)


class Employee(db.Model):
    __tablename__   = 'employees'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    department_id   = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    employee_code   = db.Column(db.String(20), unique=True, nullable=False)
    phone           = db.Column(db.String(15))
    address         = db.Column(db.Text)
    date_of_birth   = db.Column(db.Date)
    date_of_joining = db.Column(db.Date, default=datetime.utcnow)
    designation     = db.Column(db.String(100))
    salary          = db.Column(db.Float, default=0.0)
    probation_end   = db.Column(db.Date)
    contract_end    = db.Column(db.Date)
    leave_balance   = db.Column(db.Float, default=20.0)   # remaining annual leave days; half-day = 0.5
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='employee_profile', lazy=True)


class Attendance(db.Model):
    __tablename__ = 'attendance'
    id          = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date        = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    status      = db.Column(db.String(20), default='present')   # present|absent|half-day|leave
    marked_by   = db.Column(db.Integer, db.ForeignKey('users.id'))
    marked_at   = db.Column(db.DateTime, default=datetime.utcnow)
    remarks     = db.Column(db.String(255))

    employee = db.relationship('Employee', backref='attendance_records', lazy=True)


class Holiday(db.Model):
    __tablename__ = 'holidays'
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(150), nullable=False)
    date  = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(255))


class Payroll(db.Model):
    __tablename__ = 'payroll'
    id           = db.Column(db.Integer, primary_key=True)
    employee_id  = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    month        = db.Column(db.Integer, nullable=False)
    year         = db.Column(db.Integer, nullable=False)
    basic_salary = db.Column(db.Float, default=0.0)
    allowances   = db.Column(db.Float, default=0.0)
    deductions   = db.Column(db.Float, default=0.0)   # manual deductions, set via Payroll > Assign Salary
    # Leave-driven deduction, kept in its own columns rather than folded into
    # `deductions` above — the dashboard salary widget writes these, the
    # manual Assign Salary page writes `deductions`. Keeping them separate
    # means neither flow can silently overwrite the other's number when
    # both touch the same employee/month/year row; net_salary always sums
    # both regardless of which flow last ran.
    leave_days_used     = db.Column(db.Float, default=0.0)   # approved leave days counted for this month
    leave_deduction_rate= db.Column(db.Float)                 # admin-entered ₹/day rate, if any excess applied
    leave_deduction      = db.Column(db.Float, default=0.0)   # excess_days * rate
    net_salary   = db.Column(db.Float, default=0.0)
    status       = db.Column(db.String(20), default='pending')   # pending|paid
    pay_date     = db.Column(db.Date)            # scheduled salary release date
    tax_due_date = db.Column(db.Date)             # tax submission date
    paid_on      = db.Column(db.DateTime)
    created_by   = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref='payroll_records', lazy=True)


class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'
    id              = db.Column(db.Integer, primary_key=True)
    employee_id     = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    leave_type      = db.Column(db.String(50), nullable=False)
    from_date       = db.Column(db.Date, nullable=False)
    to_date         = db.Column(db.Date, nullable=False)
    reason          = db.Column(db.Text)
    status          = db.Column(db.String(20), default='pending')   # pending|approved|rejected
    applied_on      = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_on     = db.Column(db.DateTime)
    days_consumed   = db.Column(db.Float)   # set on approval: 0.5 for half-day, else 1/date in range
    excess_days     = db.Column(db.Float, default=0.0)   # portion that exceeded the employee's balance, if any
    deduction_rate  = db.Column(db.Float)   # admin-entered ₹/day rate applied to excess_days, if any
    deduction_amount= db.Column(db.Float, default=0.0)   # excess_days * deduction_rate

    employee = db.relationship('Employee', backref='leave_requests', lazy=True)


class Task(db.Model):
    __tablename__ = 'tasks'
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    assigned_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    due_date     = db.Column(db.Date)
    priority     = db.Column(db.String(20), default='medium')   # low|medium|high
    status       = db.Column(db.String(20), default='pending')  # pending|in-progress|completed
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigner = db.relationship('User', foreign_keys=[assigned_by], backref='tasks_assigned')
    assignee = db.relationship('User', foreign_keys=[assigned_to],  backref='tasks_received')

    @property
    def is_overdue(self):
        from datetime import date
        return bool(self.due_date and self.due_date < date.today() and self.status != 'completed')


class Meeting(db.Model):
    __tablename__ = 'meetings'
    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text)
    started_by      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    started_at      = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at        = db.Column(db.DateTime)
    status          = db.Column(db.String(20), default='active')   # scheduled|active|ended
    meeting_link    = db.Column(db.String(300))
    is_recurring    = db.Column(db.Boolean, default=False)
    recurrence      = db.Column(db.String(20))   # daily|weekly|monthly
    scheduled_date  = db.Column(db.Date, nullable=True)   # set only for date-fixed meetings; None = started immediately
    notified_at     = db.Column(db.DateTime, nullable=True)  # when the "it's today" alert actually went out

    starter      = db.relationship('User', foreign_keys=[started_by], backref='meetings_started')
    participants = db.relationship('MeetingParticipant', backref='meeting', lazy=True)


class MeetingParticipant(db.Model):
    __tablename__ = 'meeting_participants'
    id         = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at  = db.Column(db.DateTime)
    attendance = db.Column(db.String(20), default='absent')   # present|absent
    marked_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='meeting_participations')


class Notification(db.Model):
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.String(500), nullable=False)
    type       = db.Column(db.String(50), default='info')   # meeting|task|payroll|info
    ref_id     = db.Column(db.Integer)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications', lazy=True)
