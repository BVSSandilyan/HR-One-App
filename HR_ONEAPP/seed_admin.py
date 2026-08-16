"""
Run this ONCE after extracting the project to create the default Admin account.

    python seed_admin.py

After running, log in at http://127.0.0.1:5000 with:
    Email   : admin@gmail.com
    Password: admin@123
"""

import sys
sys.path.insert(0, '.')

from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    existing = User.query.filter_by(email='admin@gmail.com').first()

    if existing:
        # Update credentials in case they were changed
        existing.set_password('admin@123')
        existing.is_active       = True
        existing.approval_status = 'approved'
        existing.role            = 'admin'
        db.session.commit()
        print("✅ Admin account updated.")
    else:
        admin = User(
            name            = 'Admin',
            email           = 'admin@gmail.com',
            role            = 'admin',
            is_active       = True,
            approval_status = 'approved'
        )
        admin.set_password('admin@123')
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin account created.")

    print()
    print("━" * 40)
    print("  Email    : admin@gmail.com")
    print("  Password : admin@123")
    print("  URL      : http://127.0.0.1:5000")
    print("━" * 40)
