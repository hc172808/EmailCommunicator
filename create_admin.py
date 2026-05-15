#!/usr/bin/env python3
"""
Script to create or update the netlifegy admin user.
Run with: python create_admin.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db
from models import User

def create_or_update_admin():
    with app.app_context():
        user = User.query.filter_by(username='netlifegy').first()
        if user:
            user.email       = 'netlifegy@netlifegy.com'
            user.full_name   = user.full_name or 'Netlifegy Admin'
            user.is_admin    = True
            user.active      = True
            user.is_verified = True
            user.set_password('Zaq12wsx')
            db.session.commit()
            print(f"Updated: {user.username} / {user.email}")
        else:
            user = User(
                username    = 'netlifegy',
                email       = 'netlifegy@netlifegy.com',
                full_name   = 'Netlifegy Admin',
                is_admin    = True,
                active      = True,
                is_verified = True,
            )
            user.set_password('Zaq12wsx')
            db.session.add(user)
            db.session.commit()
            print(f"Created: {user.username} / {user.email}")

        print("Login → username: netlifegy  password: Zaq12wsx")

if __name__ == '__main__':
    create_or_update_admin()
