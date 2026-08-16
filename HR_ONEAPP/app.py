from flask import Flask, redirect, url_for
from flask_socketio import SocketIO
from models import db
from routes import (
    auth_bp,
    dashboard_bp,
    meeting_bp,
    attendance_bp,
    payroll_bp,
    task_bp,
    employee_bp,
    leave_bp,
    admin_approval_bp
)
from scheduler import start_meeting_scheduler
import os


# ============================================================
# Flask-SocketIO
# ============================================================

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading"
)


# ============================================================
# Application Factory
# ============================================================

def create_app():
    app = Flask(__name__)

    # --------------------------------------------------------
    # Configuration
    # --------------------------------------------------------

    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY",
        "hr-oneapp-secret-2024"
    )

    # Keep SQLite for your current project
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "sqlite:///hr_oneapp.db"
    )

    # Render/PostgreSQL sometimes provides postgres://
    # Convert it to postgresql:// if necessary.
    database_url = app.config["SQLALCHEMY_DATABASE_URI"]

    if database_url.startswith("postgres://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --------------------------------------------------------
    # Initialize Database
    # --------------------------------------------------------

    db.init_app(app)

    # --------------------------------------------------------
    # Initialize SocketIO
    # --------------------------------------------------------

    socketio.init_app(app)

    # --------------------------------------------------------
    # Register Blueprints
    # --------------------------------------------------------

    blueprints = [
        auth_bp,
        dashboard_bp,
        meeting_bp,
        attendance_bp,
        payroll_bp,
        task_bp,
        employee_bp,
        leave_bp,
        admin_approval_bp
    ]

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    # --------------------------------------------------------
    # Register SocketIO Event Handlers
    # --------------------------------------------------------

    import signal_handlers  # noqa: F401

    # --------------------------------------------------------
    # Home Route
    # --------------------------------------------------------

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    # --------------------------------------------------------
    # Create Database Tables
    # --------------------------------------------------------

    with app.app_context():
        db.create_all()
        print("All tables ready.")

    # --------------------------------------------------------
    # Meeting Scheduler
    # --------------------------------------------------------
    # Only start scheduler when appropriate.
    # Avoid duplicate scheduler during Flask debug reload.
    # --------------------------------------------------------

    if (
        not app.debug
        or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        start_meeting_scheduler(app)

    return app


# ============================================================
# Local Development
# ============================================================

if __name__ == "__main__":

    app = create_app()

    print("=" * 60)
    print("HR-ONEAPP SERVER STARTING")
    print("=" * 60)
    print("Server: http://127.0.0.1:5000")
    print("SocketIO Async Mode: threading")
    print("Meeting/WebRTC signaling: Enabled")
    print("=" * 60)

    socketio.run(
        app,
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        allow_unsafe_werkzeug=True
    )