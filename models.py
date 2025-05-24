from app import db
from datetime import datetime
from sqlalchemy import Text, DateTime, Boolean, String, Integer
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    """User model for authentication and profile management"""
    __tablename__ = 'users'
    
    id = db.Column(Integer, primary_key=True)
    username = db.Column(String(80), unique=True, nullable=False)
    email = db.Column(String(255), unique=True, nullable=False)
    password_hash = db.Column(String(256), nullable=False)
    
    # Profile information
    full_name = db.Column(String(255), nullable=False)
    phone_number = db.Column(String(20))
    location = db.Column(String(255))
    profile_photo = db.Column(String(255))  # File path or URL
    bio = db.Column(Text)
    
    # User status and role
    active = db.Column(Boolean, default=True)
    is_admin = db.Column(Boolean, default=False)
    is_verified = db.Column(Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(DateTime)
    
    # Email server settings
    smtp_server = db.Column(String(255))
    smtp_port = db.Column(Integer)
    smtp_username = db.Column(String(255))
    smtp_password = db.Column(String(255))
    imap_server = db.Column(String(255))
    imap_port = db.Column(Integer)
    use_tls = db.Column(Boolean, default=True)
    
    # Relationships
    emails_sent = db.relationship('Email', foreign_keys='Email.sender_id', backref='sender_user', lazy='dynamic')
    emails_received = db.relationship('Email', foreign_keys='Email.recipient_id', backref='recipient_user', lazy='dynamic')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_email_address(self):
        """Get the primary email address for this user"""
        return self.smtp_username or self.email
    
    @property
    def is_active(self):
        """Override UserMixin property to use our 'active' field"""
        return self.active
    
    def __repr__(self):
        return f'<User {self.username}>'

class Email(db.Model):
    """Model for storing email messages"""
    __tablename__ = 'emails'
    
    id = db.Column(Integer, primary_key=True)
    sender = db.Column(String(255), nullable=False)
    recipient = db.Column(String(255), nullable=False)
    sender_id = db.Column(Integer, db.ForeignKey('users.id'))
    recipient_id = db.Column(Integer, db.ForeignKey('users.id'))
    subject = db.Column(String(500), nullable=False)
    body_text = db.Column(Text)
    body_html = db.Column(Text)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    sent_at = db.Column(DateTime)
    is_sent = db.Column(Boolean, default=False)
    is_received = db.Column(Boolean, default=False)
    is_draft = db.Column(Boolean, default=False)
    message_id = db.Column(String(255), unique=True)
    in_reply_to = db.Column(String(255))
    error_message = db.Column(Text)
    
    def __repr__(self):
        return f'<Email {self.id}: {self.subject}>'
    
    def to_dict(self):
        """Convert email to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'sender': self.sender,
            'recipient': self.recipient,
            'subject': self.subject,
            'body_text': self.body_text,
            'body_html': self.body_html,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'is_sent': self.is_sent,
            'is_received': self.is_received,
            'is_draft': self.is_draft,
            'message_id': self.message_id,
            'in_reply_to': self.in_reply_to,
            'error_message': self.error_message
        }

class EmailConfig(db.Model):
    """Model for storing email server configuration"""
    __tablename__ = 'email_config'
    
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(100), nullable=False)
    smtp_server = db.Column(String(255))
    smtp_port = db.Column(Integer)
    smtp_username = db.Column(String(255))
    smtp_password = db.Column(String(255))
    imap_server = db.Column(String(255))
    imap_port = db.Column(Integer)
    default_sender = db.Column(String(255))
    use_tls = db.Column(Boolean, default=True)
    is_active = db.Column(Boolean, default=False)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<EmailConfig {self.name}>'
