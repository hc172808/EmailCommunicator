#!/usr/bin/env python3
"""
Script to create the first admin user for the email server
"""

from app import app, db
from models import User

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(is_admin=True).first()
        if admin:
            print(f"Admin user already exists: {admin.username} ({admin.email})")
            return
        
        # Create admin user
        admin_user = User(
            username='admin',
            email='admin@emailserver.local',
            full_name='System Administrator',
            phone_number='+1234567890',
            location='Server Location',
            bio='System administrator for the email server',
            active=True,
            is_admin=True,
            is_verified=True,
            smtp_server='smtp.gmail.com',
            smtp_port=587,
            smtp_username='admin@emailserver.local',
            imap_server='imap.gmail.com',
            imap_port=993,
            use_tls=True
        )
        
        # Set password
        admin_user.set_password('admin123')
        
        # Save to database
        db.session.add(admin_user)
        db.session.commit()
        
        print("✓ Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("Email: admin@emailserver.local")
        print("\nPlease change the password after first login.")

if __name__ == '__main__':
    create_admin_user()