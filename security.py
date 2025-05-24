"""
Security module for email server with fail2ban-like functionality
Implements IP blocking, rate limiting, and security monitoring
"""

import time
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from functools import wraps
from flask import request, abort, session, current_app
from app import db
from sqlalchemy import Text, DateTime, Boolean, String, Integer

class SecurityBan(db.Model):
    """Model for storing IP bans and security events"""
    __tablename__ = 'security_bans'
    
    id = db.Column(Integer, primary_key=True)
    ip_address = db.Column(String(45), nullable=False, index=True)  # Support IPv6
    reason = db.Column(String(255), nullable=False)
    ban_type = db.Column(String(50), nullable=False)  # 'temporary', 'permanent', 'warning'
    attempts = db.Column(Integer, default=1)
    first_attempt = db.Column(DateTime, default=datetime.utcnow)
    last_attempt = db.Column(DateTime, default=datetime.utcnow)
    ban_until = db.Column(DateTime)
    is_active = db.Column(Boolean, default=True)
    user_agent = db.Column(Text)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<SecurityBan {self.ip_address}: {self.reason}>'

class SecurityLog(db.Model):
    """Model for logging security events"""
    __tablename__ = 'security_logs'
    
    id = db.Column(Integer, primary_key=True)
    ip_address = db.Column(String(45), nullable=False, index=True)
    event_type = db.Column(String(50), nullable=False)  # 'login_attempt', 'blocked_access', 'suspicious_activity'
    event_data = db.Column(Text)  # JSON data
    user_agent = db.Column(Text)
    endpoint = db.Column(String(255))
    method = db.Column(String(10))
    status_code = db.Column(Integer)
    timestamp = db.Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f'<SecurityLog {self.ip_address}: {self.event_type}>'

class SecurityManager:
    """Main security manager class"""
    
    def __init__(self):
        self.failed_attempts = defaultdict(list)
        self.rate_limits = defaultdict(list)
        
        # Configuration
        self.MAX_LOGIN_ATTEMPTS = 5
        self.LOGIN_BAN_DURATION = 3600  # 1 hour in seconds
        self.RATE_LIMIT_REQUESTS = 100
        self.RATE_LIMIT_WINDOW = 3600  # 1 hour
        self.SUSPICIOUS_PATTERNS = [
            'admin', 'administrator', 'root', 'test', 'guest',
            'user', 'password', '123456', 'qwerty'
        ]
        
    def get_client_ip(self):
        """Get real client IP address considering proxies"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP')
        return request.remote_addr
    
    def is_ip_banned(self, ip_address=None):
        """Check if IP address is currently banned"""
        if not ip_address:
            ip_address = self.get_client_ip()
        
        # Check database for active bans
        ban = SecurityBan.query.filter_by(
            ip_address=ip_address, 
            is_active=True
        ).first()
        
        if ban:
            # Check if temporary ban has expired
            if ban.ban_type == 'temporary' and ban.ban_until:
                if datetime.utcnow() > ban.ban_until:
                    ban.is_active = False
                    db.session.commit()
                    return False
            return True
        
        return False
    
    def ban_ip(self, ip_address, reason, ban_type='temporary', duration_hours=1):
        """Ban an IP address"""
        existing_ban = SecurityBan.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if existing_ban:
            # Update existing ban
            existing_ban.attempts += 1
            existing_ban.last_attempt = datetime.utcnow()
            if ban_type == 'permanent':
                existing_ban.ban_type = 'permanent'
                existing_ban.ban_until = None
            else:
                existing_ban.ban_until = datetime.utcnow() + timedelta(hours=duration_hours)
        else:
            # Create new ban
            ban_until = None if ban_type == 'permanent' else datetime.utcnow() + timedelta(hours=duration_hours)
            
            new_ban = SecurityBan(
                ip_address=ip_address,
                reason=reason,
                ban_type=ban_type,
                ban_until=ban_until,
                user_agent=request.headers.get('User-Agent', '')
            )
            db.session.add(new_ban)
        
        db.session.commit()
        
        # Log the ban
        self.log_security_event('ip_banned', {
            'reason': reason,
            'ban_type': ban_type,
            'duration_hours': duration_hours
        })
        
        logging.warning(f"IP {ip_address} banned: {reason}")
    
    def unban_ip(self, ip_address):
        """Remove ban for IP address"""
        ban = SecurityBan.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if ban:
            ban.is_active = False
            db.session.commit()
            
            self.log_security_event('ip_unbanned', {
                'previously_banned_reason': ban.reason
            })
            
            logging.info(f"IP {ip_address} unbanned")
            return True
        
        return False
    
    def record_failed_login(self, username_or_email):
        """Record a failed login attempt"""
        ip_address = self.get_client_ip()
        
        # Add to memory tracking
        now = time.time()
        self.failed_attempts[ip_address].append(now)
        
        # Clean old attempts (older than ban duration)
        cutoff = now - self.LOGIN_BAN_DURATION
        self.failed_attempts[ip_address] = [
            attempt for attempt in self.failed_attempts[ip_address] 
            if attempt > cutoff
        ]
        
        # Check if we should ban this IP
        if len(self.failed_attempts[ip_address]) >= self.MAX_LOGIN_ATTEMPTS:
            self.ban_ip(
                ip_address, 
                f"Too many failed login attempts ({self.MAX_LOGIN_ATTEMPTS})",
                'temporary',
                duration_hours=1
            )
        
        # Log the failed attempt
        self.log_security_event('failed_login', {
            'username_or_email': username_or_email,
            'attempt_count': len(self.failed_attempts[ip_address])
        })
    
    def record_successful_login(self, user):
        """Record a successful login"""
        ip_address = self.get_client_ip()
        
        # Clear failed attempts for this IP
        if ip_address in self.failed_attempts:
            del self.failed_attempts[ip_address]
        
        # Log successful login
        self.log_security_event('successful_login', {
            'user_id': user.id,
            'username': user.username
        })
    
    def check_rate_limit(self, requests_per_hour=None):
        """Check if IP is within rate limits"""
        if not requests_per_hour:
            requests_per_hour = self.RATE_LIMIT_REQUESTS
        
        ip_address = self.get_client_ip()
        now = time.time()
        
        # Add current request
        self.rate_limits[ip_address].append(now)
        
        # Clean old requests
        cutoff = now - self.RATE_LIMIT_WINDOW
        self.rate_limits[ip_address] = [
            req_time for req_time in self.rate_limits[ip_address]
            if req_time > cutoff
        ]
        
        # Check if over limit
        if len(self.rate_limits[ip_address]) > requests_per_hour:
            self.ban_ip(
                ip_address,
                f"Rate limit exceeded ({requests_per_hour} requests/hour)",
                'temporary',
                duration_hours=2
            )
            return False
        
        return True
    
    def detect_suspicious_activity(self, username_or_email):
        """Detect suspicious login patterns"""
        ip_address = self.get_client_ip()
        
        # Check for common attack patterns
        suspicious = False
        reasons = []
        
        if username_or_email:
            username_lower = username_or_email.lower()
            for pattern in self.SUSPICIOUS_PATTERNS:
                if pattern in username_lower:
                    suspicious = True
                    reasons.append(f"Suspicious username pattern: {pattern}")
        
        # Check user agent
        user_agent = request.headers.get('User-Agent', '').lower()
        if not user_agent or 'bot' in user_agent or 'scan' in user_agent:
            suspicious = True
            reasons.append("Suspicious user agent")
        
        if suspicious:
            self.log_security_event('suspicious_activity', {
                'reasons': reasons,
                'username_or_email': username_or_email
            })
            
            # Immediate ban for very suspicious activity
            if len(reasons) > 1:
                self.ban_ip(
                    ip_address,
                    f"Suspicious activity: {', '.join(reasons)}",
                    'temporary',
                    duration_hours=24
                )
                return True
        
        return False
    
    def log_security_event(self, event_type, event_data=None):
        """Log security events to database"""
        ip_address = self.get_client_ip()
        
        log_entry = SecurityLog(
            ip_address=ip_address,
            event_type=event_type,
            event_data=json.dumps(event_data) if event_data else None,
            user_agent=request.headers.get('User-Agent', ''),
            endpoint=request.endpoint,
            method=request.method,
            status_code=200  # Will be updated if different
        )
        
        db.session.add(log_entry)
        db.session.commit()
    
    def get_security_stats(self):
        """Get security statistics for admin dashboard"""
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_week = now - timedelta(days=7)
        
        stats = {
            'active_bans': SecurityBan.query.filter_by(is_active=True).count(),
            'bans_24h': SecurityBan.query.filter(SecurityBan.created_at >= last_24h).count(),
            'failed_logins_24h': SecurityLog.query.filter(
                SecurityLog.event_type == 'failed_login',
                SecurityLog.timestamp >= last_24h
            ).count(),
            'successful_logins_24h': SecurityLog.query.filter(
                SecurityLog.event_type == 'successful_login',
                SecurityLog.timestamp >= last_24h
            ).count(),
            'suspicious_activity_week': SecurityLog.query.filter(
                SecurityLog.event_type == 'suspicious_activity',
                SecurityLog.timestamp >= last_week
            ).count()
        }
        
        return stats

# Global security manager instance
security_manager = SecurityManager()

def security_check(f):
    """Decorator to add security checks to routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip_address = security_manager.get_client_ip()
        
        # Check if IP is banned
        if security_manager.is_ip_banned(ip_address):
            logging.warning(f"Blocked request from banned IP: {ip_address}")
            abort(403)  # Forbidden
        
        # Check rate limits
        if not security_manager.check_rate_limit():
            logging.warning(f"Rate limit exceeded for IP: {ip_address}")
            abort(429)  # Too Many Requests
        
        return f(*args, **kwargs)
    
    return decorated_function

def login_security_check(f):
    """Special decorator for login routes with enhanced security"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip_address = security_manager.get_client_ip()
        
        # Check if IP is banned
        if security_manager.is_ip_banned(ip_address):
            logging.warning(f"Blocked login attempt from banned IP: {ip_address}")
            abort(403)
        
        # Check for suspicious patterns in form data
        if request.method == 'POST':
            username = request.form.get('username', '')
            if security_manager.detect_suspicious_activity(username):
                logging.warning(f"Suspicious login activity from IP: {ip_address}")
                abort(403)
        
        return f(*args, **kwargs)
    
    return decorated_function