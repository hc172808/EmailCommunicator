from app import db
from datetime import datetime
from sqlalchemy import Text, DateTime, Boolean, String, Integer
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

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
    profile_photo = db.Column(String(255))
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
    
    # Two-factor authentication
    totp_secret = db.Column(String(64))
    totp_enabled = db.Column(Boolean, default=False)
    totp_backup_codes = db.Column(Text)
    
    # Relationships
    emails_sent = db.relationship('Email', foreign_keys='Email.sender_id', backref='sender_user', lazy='dynamic')
    emails_received = db.relationship('Email', foreign_keys='Email.recipient_id', backref='recipient_user', lazy='dynamic')
    api_tokens = db.relationship('APIToken', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_email_address(self):
        return self.smtp_username or self.email
    
    @property
    def is_active(self):
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


class PasswordResetToken(db.Model):
    """Tokens for password reset flow"""
    __tablename__ = 'password_reset_tokens'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(String(128), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(64))
    created_at = db.Column(DateTime, default=datetime.utcnow)
    expires_at = db.Column(DateTime, nullable=False)
    used = db.Column(Boolean, default=False)
    
    user = db.relationship('User', backref=db.backref('reset_tokens', lazy='dynamic'))
    
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at
    
    def __repr__(self):
        return f'<PasswordResetToken user_id={self.user_id}>'


class EmailVerificationToken(db.Model):
    """Tokens for email address verification"""
    __tablename__ = 'email_verification_tokens'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(String(128), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(64))
    created_at = db.Column(DateTime, default=datetime.utcnow)
    expires_at = db.Column(DateTime, nullable=False)
    used = db.Column(Boolean, default=False)
    
    user = db.relationship('User', backref=db.backref('verification_tokens', lazy='dynamic'))
    
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at
    
    def __repr__(self):
        return f'<EmailVerificationToken user_id={self.user_id}>'


class SystemConfig(db.Model):
    """Key-value store for system-wide settings (e.g. maintenance mode)"""
    __tablename__ = 'system_config'

    id = db.Column(Integer, primary_key=True)
    key = db.Column(String(100), unique=True, nullable=False)
    value = db.Column(Text)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
            row.updated_at = datetime.utcnow()
        else:
            row = cls(key=key, value=value)
            db.session.add(row)
        db.session.commit()

    def __repr__(self):
        return f'<SystemConfig {self.key}={self.value}>'


class FirewallRule(db.Model):
    """IP-based firewall rules — block or allow specific addresses."""
    __tablename__ = 'firewall_rules'

    id = db.Column(Integer, primary_key=True)
    rule_type = db.Column(String(10), nullable=False)   # 'block' or 'allow'
    ip_or_cidr = db.Column(String(100), nullable=False)
    description = db.Column(String(255))
    is_active = db.Column(Boolean, default=True)
    hits = db.Column(Integer, default=0)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    created_by = db.Column(Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<FirewallRule {self.rule_type} {self.ip_or_cidr}>'


class OAuthApp(db.Model):
    """A registered third-party client application that uses this server for SSO."""
    __tablename__ = 'oauth_apps'

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(100), nullable=False)
    description = db.Column(Text)
    website_url = db.Column(String(500))
    logo_url = db.Column(String(500))
    client_id = db.Column(String(64), unique=True, nullable=False,
                          default=lambda: secrets.token_urlsafe(32))
    client_secret = db.Column(String(128), nullable=False,
                              default=lambda: secrets.token_urlsafe(64))
    redirect_uris = db.Column(Text, nullable=False)  # newline-separated list
    is_active = db.Column(Boolean, default=True)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    created_by = db.Column(Integer, db.ForeignKey('users.id'))

    auth_codes = db.relationship('OAuthAuthorizationCode', backref='app', lazy='dynamic',
                                 cascade='all, delete-orphan')
    access_tokens = db.relationship('OAuthAccessToken', backref='app', lazy='dynamic',
                                    cascade='all, delete-orphan')

    def allowed_redirect(self, uri):
        allowed = [u.strip() for u in (self.redirect_uris or '').splitlines() if u.strip()]
        return uri in allowed

    def __repr__(self):
        return f'<OAuthApp {self.name}>'


class OAuthAuthorizationCode(db.Model):
    """Short-lived code issued after user approves an OAuth authorization request."""
    __tablename__ = 'oauth_authorization_codes'

    id = db.Column(Integer, primary_key=True)
    code = db.Column(String(128), unique=True, nullable=False,
                     default=lambda: secrets.token_urlsafe(64))
    app_id = db.Column(Integer, db.ForeignKey('oauth_apps.id'), nullable=False)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    redirect_uri = db.Column(String(500), nullable=False)
    scope = db.Column(String(200), default='profile')
    created_at = db.Column(DateTime, default=datetime.utcnow)
    expires_at = db.Column(DateTime, nullable=False)
    used = db.Column(Boolean, default=False)

    user = db.relationship('User', backref=db.backref('oauth_codes', lazy='dynamic'))

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f'<OAuthAuthorizationCode app={self.app_id} user={self.user_id}>'


class OAuthAccessToken(db.Model):
    """Access token issued to a client app after code exchange."""
    __tablename__ = 'oauth_access_tokens'

    id = db.Column(Integer, primary_key=True)
    token = db.Column(String(128), unique=True, nullable=False,
                      default=lambda: secrets.token_urlsafe(64))
    app_id = db.Column(Integer, db.ForeignKey('oauth_apps.id'), nullable=False)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    scope = db.Column(String(200), default='profile')
    created_at = db.Column(DateTime, default=datetime.utcnow)
    expires_at = db.Column(DateTime, nullable=False)

    user = db.relationship('User', backref=db.backref('oauth_tokens', lazy='dynamic'))

    def is_valid(self):
        return datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f'<OAuthAccessToken app={self.app_id} user={self.user_id}>'


class APIToken(db.Model):
    """Long-lived API tokens for programmatic access"""
    __tablename__ = 'api_tokens'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(String(100), nullable=False)
    token = db.Column(String(128), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(64))
    created_at = db.Column(DateTime, default=datetime.utcnow)
    last_used_at = db.Column(DateTime)
    is_active = db.Column(Boolean, default=True)
    
    def __repr__(self):
        return f'<APIToken {self.name} user_id={self.user_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'token_preview': self.token[:8] + '...' + self.token[-4:],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'is_active': self.is_active
        }
