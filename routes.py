from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db, csrf
from models import Email, EmailConfig, User, PasswordResetToken, EmailVerificationToken, APIToken, SystemConfig, FirewallRule, AppRelease
from email_service import EmailService
from identity_emails import send_verification_email, send_password_reset_email
from forms import (LoginForm, RegistrationForm, ProfileForm, ChangePasswordForm, AdminUserForm,
                   ForgotPasswordForm, ResetPasswordForm, TwoFactorSetupForm, TwoFactorVerifyForm, APITokenForm)
from security import security_manager, security_check, login_security_check, SecurityBan, SecurityLog
from backup_service import backup_service
from domain_config import domain_manager, DomainConfig
from datetime import datetime, timedelta
import logging
import os
import io
import base64
import secrets
import pyotp
import qrcode
import qrcode.image.pil
from werkzeug.utils import secure_filename
from PIL import Image

email_service = EmailService()

# ── Maintenance mode middleware ────────────────────────────────────────────────

MAINTENANCE_BYPASS_ROUTES = {'login', 'logout', 'static', 'maintenance_page',
                              'admin_toggle_maintenance', 'pwa_sw', 'pwa_offline',
                              'download_page', 'download_release', 'api_app_version', 'api_update_banner',
                              'oauth_authorize', 'oauth_token', 'oauth_userinfo',
                              'oauth_discovery', 'oauth_widget'}

def _client_ip():
    """Return the real client IP, respecting X-Forwarded-For."""
    return (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or '127.0.0.1')

def _ip_matches(client_ip, pattern):
    """Return True if client_ip matches pattern (single IP or CIDR)."""
    import ipaddress
    try:
        if '/' in pattern:
            return ipaddress.ip_address(client_ip) in ipaddress.ip_network(pattern, strict=False)
        return client_ip == pattern
    except ValueError:
        return False

@app.before_request
def check_firewall():
    """Block or allow IPs based on active firewall rules."""
    if request.endpoint in ('static',):
        return None
    client_ip = _client_ip()
    try:
        rules = FirewallRule.query.filter_by(is_active=True).all()
    except Exception:
        return None
    for rule in rules:
        if _ip_matches(client_ip, rule.ip_or_cidr):
            rule.hits = (rule.hits or 0) + 1
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            if rule.rule_type == 'block':
                return render_template('firewall_blocked.html', ip=client_ip), 403
    return None

@app.before_request
def check_maintenance():
    """Redirect non-admin users to the maintenance page when maintenance mode is on."""
    # Always allow static files and the maintenance/login routes through
    if request.endpoint in MAINTENANCE_BYPASS_ROUTES:
        return None
    # Check DB flag
    try:
        mode = SystemConfig.get('maintenance_mode', 'off')
    except Exception:
        return None
    if mode != 'on':
        return None
    # Admins (already logged in) may pass through
    if current_user.is_authenticated and current_user.is_admin:
        return None
    # Everyone else sees the maintenance page
    features_raw = SystemConfig.get('maintenance_features', '')
    features = [f.strip() for f in features_raw.split('|') if f.strip()]
    message = SystemConfig.get('maintenance_message', '')
    return render_template('maintenance.html', features=features, message=message), 503


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def save_profile_picture(form_picture):
    random_hex = os.urandom(8).hex()
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(picture_path), exist_ok=True)
    
    output_size = (150, 150)
    img = Image.open(form_picture)
    img.thumbnail(output_size)
    img.save(picture_path)
    
    return picture_fn

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
@login_security_check
def login():
    """User login with security protection"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        # Check if login is username or email
        user = User.query.filter(
            (User.username == form.username.data) | 
            (User.email == form.username.data)
        ).first()
        
        if user and user.check_password(form.password.data):
            # Block inactive / pending-approval accounts
            if not user.active:
                flash('Your account is pending admin approval. Please wait for an administrator to activate it.', 'warning')
                return render_template('login.html', form=form)

            # Record successful login
            security_manager.record_successful_login(user)
            
            # Check for 2FA
            if user.totp_enabled:
                session['pending_2fa_user_id'] = user.id
                session['pending_2fa_remember'] = form.remember_me.data
                return redirect(url_for('two_factor_verify'))
            
            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = session.pop('oauth_next', None) or request.args.get('next')
            if not next_page or (not next_page.startswith('/') and 'oauth/authorize' not in next_page):
                next_page = url_for('index')
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(next_page)
        else:
            # Record failed login attempt
            security_manager.record_failed_login(form.username.data)
            flash('Invalid username or password', 'error')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
@security_check
def register():
    """User registration — email is auto-assigned as username@org_domain."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # Check if registration is invite-only or closed
    reg_mode = SystemConfig.get('registration_mode', 'open')
    if reg_mode == 'closed':
        flash('Account registration is currently closed. Contact the administrator.', 'info')
        return redirect(url_for('login'))

    org_domain = SystemConfig.get('org_domain', 'netlifegy.com')
    min_pw_len = int(SystemConfig.get('min_password_length', '8'))
    require_approval = SystemConfig.get('require_account_approval', 'off') == 'on'

    form = RegistrationForm()
    if form.validate_on_submit():
        # Enforce password length from policy
        if len(form.password.data) < min_pw_len:
            form.password.errors.append(f'Password must be at least {min_pw_len} characters.')
            return render_template('register.html', form=form, org_domain=org_domain, min_pw_len=min_pw_len)

        auto_email = f"{form.username.data.lower()}@{org_domain}"

        try:
            profile_picture = None
            if form.profile_photo.data:
                profile_picture = save_profile_picture(form.profile_photo.data)

            user = User(
                username=form.username.data,
                email=auto_email,
                full_name=form.full_name.data,
                phone_number=form.phone_number.data,
                location=form.location.data,
                bio=form.bio.data,
                profile_photo=profile_picture,
                smtp_server=form.smtp_server.data,
                smtp_port=int(form.smtp_port.data) if form.smtp_port.data else None,
                smtp_username=form.smtp_username.data,
                smtp_password=form.smtp_password.data,
                imap_server=form.imap_server.data,
                imap_port=int(form.imap_port.data) if form.imap_port.data else None,
                use_tls=form.use_tls.data,
                # Pending approval means account is inactive until admin approves
                active=not require_approval,
            )
            user.set_password(form.password.data)

            db.session.add(user)
            db.session.flush()

            token = EmailVerificationToken(
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.session.add(token)
            db.session.commit()

            base_url = request.host_url.rstrip('/')
            send_verification_email(user, token.token, base_url)

            if require_approval:
                flash(f'Account created ({auto_email}). An admin must approve it before you can sign in.', 'info')
            else:
                flash(f'Welcome! Your account {auto_email} was created. Check your email to verify.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Registration error: {str(e)}")
            flash('Registration failed. Please try again.', 'error')

    return render_template('register.html', form=form, org_domain=org_domain, min_pw_len=min_pw_len)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard showing email statistics"""
    # Get user's emails
    user_emails = Email.query.filter(
        (Email.sender_id == current_user.id) | 
        (Email.recipient_id == current_user.id)
    )
    
    total_emails = user_emails.count()
    sent_emails = user_emails.filter_by(is_sent=True, sender_id=current_user.id).count()
    received_emails = user_emails.filter_by(is_received=True, recipient_id=current_user.id).count()
    draft_emails = user_emails.filter_by(is_draft=True, sender_id=current_user.id).count()
    
    recent_emails = user_emails.order_by(Email.created_at.desc()).limit(5).all()
    
    return render_template('index.html', 
                         total_emails=total_emails,
                         sent_emails=sent_emails,
                         received_emails=received_emails,
                         draft_emails=draft_emails,
                         recent_emails=recent_emails)

# Profile management routes
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management"""
    form = ProfileForm()
    
    if form.validate_on_submit():
        try:
            # Handle profile picture upload
            if form.profile_photo.data:
                picture_file = save_profile_picture(form.profile_photo.data)
                current_user.profile_photo = picture_file
            
            # Update user information
            current_user.full_name = form.full_name.data
            current_user.phone_number = form.phone_number.data
            current_user.location = form.location.data
            current_user.bio = form.bio.data
            current_user.smtp_server = form.smtp_server.data
            current_user.smtp_port = int(form.smtp_port.data) if form.smtp_port.data else None
            current_user.smtp_username = form.smtp_username.data
            if form.smtp_password.data:
                current_user.smtp_password = form.smtp_password.data
            current_user.imap_server = form.imap_server.data
            current_user.imap_port = int(form.imap_port.data) if form.imap_port.data else None
            current_user.use_tls = form.use_tls.data
            
            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Profile update error: {str(e)}")
            flash('Profile update failed. Please try again.', 'error')
    
    elif request.method == 'GET':
        # Pre-populate form with current user data
        form.full_name.data = current_user.full_name
        form.phone_number.data = current_user.phone_number
        form.location.data = current_user.location
        form.bio.data = current_user.bio
        form.smtp_server.data = current_user.smtp_server
        form.smtp_port.data = str(current_user.smtp_port) if current_user.smtp_port else ''
        form.smtp_username.data = current_user.smtp_username
        form.imap_server.data = current_user.imap_server
        form.imap_port.data = str(current_user.imap_port) if current_user.imap_port else ''
        form.use_tls.data = current_user.use_tls
    
    return render_template('profile.html', form=form)

# Admin routes
@app.route('/admin')
@login_required
@security_check
def admin_dashboard():
    """Admin dashboard with security monitoring"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(active=True).count()
    admin_users = User.query.filter_by(is_admin=True).count()
    total_emails = Email.query.count()
    
    # Get security statistics
    security_stats = security_manager.get_security_stats()
    
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    maintenance_on = SystemConfig.get('maintenance_mode', 'off') == 'on'
    maintenance_message = SystemConfig.get('maintenance_message', '')
    maintenance_features = SystemConfig.get('maintenance_features', '')
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         active_users=active_users,
                         admin_users=admin_users,
                         total_emails=total_emails,
                         security_stats=security_stats,
                         recent_users=recent_users,
                         maintenance_on=maintenance_on,
                         maintenance_message=maintenance_message,
                         maintenance_features=maintenance_features)

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin user management"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    pending_count = sum(1 for u in users if not u.active)
    return render_template('admin/users.html', users=users, pending_count=pending_count)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    """Admin edit user"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    form = AdminUserForm()
    
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.active = form.active.data
        user.is_admin = form.is_admin.data
        user.is_verified = form.is_verified.data
        
        db.session.commit()
        flash(f'User {user.username} has been updated!', 'success')
        return redirect(url_for('admin_users'))
    
    elif request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
        form.full_name.data = user.full_name
        form.active.data = user.active
        form.is_admin.data = user.is_admin
        form.is_verified.data = user.is_verified
    
    return render_template('admin/edit_user.html', form=form, user=user)

@app.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@login_required
def admin_approve_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    user = User.query.get_or_404(user_id)
    user.active = True
    db.session.commit()
    flash(f'Account for {user.username} ({user.email}) has been approved and activated.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
def admin_deactivate_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin_users'))
    user.active = False
    db.session.commit()
    flash(f'Account for {user.username} has been deactivated.', 'info')
    return redirect(url_for('admin_users'))

# Security management routes
@app.route('/admin/security')
@login_required
@security_check
def admin_security():
    """Admin security dashboard"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get security data
    active_bans = SecurityBan.query.filter_by(is_active=True).order_by(SecurityBan.created_at.desc()).all()
    recent_logs = SecurityLog.query.order_by(SecurityLog.timestamp.desc()).limit(50).all()
    security_stats = security_manager.get_security_stats()
    
    return render_template('admin/security.html',
                         active_bans=active_bans,
                         recent_logs=recent_logs,
                         security_stats=security_stats)

@app.route('/admin/security/unban/<string:ip_address>', methods=['POST'])
@login_required
@security_check
def admin_unban_ip(ip_address):
    """Unban an IP address"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    if security_manager.unban_ip(ip_address):
        flash(f'IP address {ip_address} has been unbanned.', 'success')
    else:
        flash(f'IP address {ip_address} was not found in ban list.', 'error')
    
    return redirect(url_for('admin_security'))

@app.route('/admin/security/ban', methods=['POST'])
@login_required
@security_check
def admin_ban_ip():
    """Manually ban an IP address"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    ip_address = request.form.get('ip_address')
    reason = request.form.get('reason', 'Manually banned by admin')
    ban_type = request.form.get('ban_type', 'temporary')
    duration = int(request.form.get('duration', 24))
    
    if ip_address:
        security_manager.ban_ip(ip_address, reason, ban_type, duration)
        flash(f'IP address {ip_address} has been banned.', 'success')
    else:
        flash('IP address is required.', 'error')
    
    return redirect(url_for('admin_security'))

# Backup management routes
@app.route('/admin/backup')
@login_required
@security_check
def admin_backup():
    """Admin backup management dashboard"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get external drives
    external_drives = backup_service.detect_external_drives()
    
    # Get backup configuration
    backup_config = backup_service.get_backup_config()
    
    # Get list of existing backups
    backups = backup_service.list_backups(backup_config.get('external_drive_path'))
    
    return render_template('admin/backup.html',
                         external_drives=external_drives,
                         backup_config=backup_config,
                         backups=backups)

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@security_check
def admin_create_backup():
    """Create a new backup"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        external_drive_path = request.form.get('external_drive_path')
        backup_info = backup_service.create_full_backup(external_drive_path)
        
        flash('Backup created successfully!', 'success')
        logging.info(f"Backup created by admin {current_user.username}: {backup_info}")
        
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'error')
        logging.error(f"Backup creation failed: {str(e)}")
    
    return redirect(url_for('admin_backup'))

@app.route('/admin/backup/config', methods=['POST'])
@login_required
@security_check
def admin_backup_config():
    """Update backup configuration"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        config = {
            'auto_backup_enabled': 'auto_backup_enabled' in request.form,
            'backup_frequency': request.form.get('backup_frequency', 'daily'),
            'retention_days': int(request.form.get('retention_days', 30)),
            'backup_database': 'backup_database' in request.form,
            'backup_files': 'backup_files' in request.form,
            'backup_configs': 'backup_configs' in request.form,
            'compression_enabled': 'compression_enabled' in request.form,
            'external_drive_path': request.form.get('external_drive_path')
        }
        
        backup_service.update_backup_config(config)
        flash('Backup configuration updated successfully!', 'success')
        
    except Exception as e:
        flash(f'Configuration update failed: {str(e)}', 'error')
        logging.error(f"Backup config update failed: {str(e)}")
    
    return redirect(url_for('admin_backup'))

@app.route('/admin/backup/delete/<path:backup_id>', methods=['POST'])
@login_required
@security_check
def admin_delete_backup(backup_id):
    """Delete a backup"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Decode the backup path
        import base64
        backup_path = base64.b64decode(backup_id.encode()).decode()
        
        if backup_service.delete_backup(backup_path):
            flash('Backup deleted successfully!', 'success')
        else:
            flash('Failed to delete backup.', 'error')
            
    except Exception as e:
        flash(f'Delete operation failed: {str(e)}', 'error')
        logging.error(f"Backup deletion failed: {str(e)}")
    
    return redirect(url_for('admin_backup'))

@app.route('/admin/backup/cleanup', methods=['POST'])
@login_required
@security_check
def admin_cleanup_backups():
    """Clean up old backups"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        backup_config = backup_service.get_backup_config()
        external_drive_path = backup_config.get('external_drive_path')
        
        cleaned_count = backup_service.cleanup_old_backups(external_drive_path)
        flash(f'Cleaned up {cleaned_count} old backup(s).', 'success')
        
    except Exception as e:
        flash(f'Cleanup failed: {str(e)}', 'error')
        logging.error(f"Backup cleanup failed: {str(e)}")
    
    return redirect(url_for('admin_backup'))

# Domain management routes
@app.route('/admin/domains')
@login_required
@security_check
def admin_domains():
    """Admin domain management"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    domains = DomainConfig.query.all()
    return render_template('admin/domains.html', domains=domains)

@app.route('/admin/domains/add', methods=['POST'])
@login_required
@security_check
def admin_add_domain():
    """Add new domain"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    domain_name = request.form.get('domain_name')
    is_primary = 'is_primary' in request.form
    
    if domain_name:
        success, result = domain_manager.add_domain(domain_name, is_primary)
        if success:
            flash(f'Domain {domain_name} added successfully!', 'success')
        else:
            flash(f'Failed to add domain: {result}', 'error')
    else:
        flash('Domain name is required.', 'error')
    
    return redirect(url_for('admin_domains'))

@app.route('/admin/domains/<int:domain_id>/ssl', methods=['POST'])
@login_required
@security_check
def admin_configure_ssl(domain_id):
    """Configure SSL for domain"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    domain = DomainConfig.query.get_or_404(domain_id)
    auto_ssl = 'auto_ssl' in request.form
    
    success, message = domain_manager.configure_ssl(domain.domain_name, auto_ssl)
    if success:
        flash(f'SSL configuration updated for {domain.domain_name}', 'success')
    else:
        flash(f'SSL configuration failed: {message}', 'error')
    
    return redirect(url_for('admin_domains'))

# API routes for mobile app
@app.route('/api/auth/login', methods=['POST'])
@csrf.exempt
def api_login():
    """API login for mobile app"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user and user.check_password(password) and user.active:
            # Generate API token for mobile
            import jwt
            import os
            
            payload = {
                'user_id': user.id,
                'username': user.username,
                'exp': datetime.utcnow().timestamp() + 86400  # 24 hours
            }
            
            token = jwt.encode(payload, os.environ.get('SESSION_SECRET', 'secret'), algorithm='HS256')
            
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.full_name,
                    'profile_photo': user.profile_photo
                }
            })
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/emails', methods=['GET'])
def api_get_emails():
    """Get emails for mobile app"""
    try:
        # Verify API token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401
        
        import jwt
        payload = jwt.decode(token, os.environ.get('SESSION_SECRET', 'secret'), algorithms=['HS256'])
        user_id = payload['user_id']
        
        # Get user's emails
        emails = Email.query.filter(
            (Email.sender_id == user_id) | (Email.recipient_id == user_id)
        ).order_by(Email.created_at.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'emails': [email.to_dict() for email in emails]
        })
        
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expired'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/emails/send', methods=['POST'])
@csrf.exempt
def api_send_email():
    """Send email via API for mobile app"""
    try:
        # Verify API token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401
        
        import jwt
        payload = jwt.decode(token, os.environ.get('SESSION_SECRET', 'secret'), algorithms=['HS256'])
        user_id = payload['user_id']
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        recipient = data.get('recipient')
        subject = data.get('subject')
        body = data.get('body')
        
        if not all([recipient, subject, body]):
            return jsonify({'error': 'Recipient, subject, and body are required'}), 400
        
        # Create email
        email = Email(
            sender=user.email,
            recipient=recipient,
            sender_id=user.id,
            subject=subject,
            body_text=body,
            is_draft=False
        )
        
        db.session.add(email)
        db.session.commit()
        
        # Send email
        email_service = EmailService()
        success, message = email_service.send_email(email)
        
        if success:
            email.is_sent = True
            email.sent_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Email sent successfully',
                'email_id': email.id
            })
        else:
            email.error_message = message
            db.session.commit()
            return jsonify({'error': f'Failed to send email: {message}'}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expired'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    """Compose and send new email"""
    if request.method == 'POST':
        try:
            sender = request.form['sender']
            recipient = request.form['recipient']
            subject = request.form['subject']
            body_text = request.form['body_text']
            body_html = request.form.get('body_html', '')
            is_draft = 'save_draft' in request.form
            
            # Validate required fields
            if not all([sender, recipient, subject]):
                flash('Sender, recipient, and subject are required fields.', 'error')
                return render_template('compose.html')
            
            # Create email record
            email = Email(
                sender=sender,
                recipient=recipient,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                is_draft=is_draft
            )
            
            db.session.add(email)
            db.session.commit()
            
            if not is_draft:
                # Send the email
                success, message = email_service.send_email(email)
                if success:
                    email.is_sent = True
                    email.sent_at = datetime.utcnow()
                    email.message_id = message  # message contains message_id on success
                    flash('Email sent successfully!', 'success')
                else:
                    email.error_message = message
                    flash(f'Failed to send email: {message}', 'error')
                
                db.session.commit()
                return redirect(url_for('sent'))
            else:
                flash('Email saved as draft.', 'info')
                return redirect(url_for('index'))
                
        except Exception as e:
            logging.error(f"Error composing email: {str(e)}")
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('compose.html')

@app.route('/inbox')
def inbox():
    """View received emails"""
    # Attempt to fetch new emails
    try:
        email_service.fetch_emails()
    except Exception as e:
        logging.error(f"Error fetching emails: {str(e)}")
        flash(f'Error fetching new emails: {str(e)}', 'warning')
    
    emails = Email.query.filter_by(is_received=True).order_by(Email.created_at.desc()).all()
    return render_template('inbox.html', emails=emails)

@app.route('/sent')
def sent():
    """View sent emails"""
    emails = Email.query.filter_by(is_sent=True).order_by(Email.sent_at.desc()).all()
    return render_template('sent.html', emails=emails)

@app.route('/email/<int:email_id>')
def email_detail(email_id):
    """View email details"""
    email = Email.query.get_or_404(email_id)
    return render_template('email_detail.html', email=email)

@app.route('/email/<int:email_id>/delete', methods=['POST'])
def delete_email(email_id):
    """Delete an email"""
    try:
        email = Email.query.get_or_404(email_id)
        db.session.delete(email)
        db.session.commit()
        flash('Email deleted successfully.', 'success')
    except Exception as e:
        logging.error(f"Error deleting email: {str(e)}")
        flash(f'Error deleting email: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(request.referrer or url_for('index'))

@app.route('/drafts')
def drafts():
    """View draft emails"""
    emails = Email.query.filter_by(is_draft=True).order_by(Email.created_at.desc()).all()
    return render_template('sent.html', emails=emails, page_title='Drafts')

@app.route('/draft/<int:email_id>/edit')
def edit_draft(email_id):
    """Edit a draft email"""
    email = Email.query.get_or_404(email_id)
    if not email.is_draft:
        flash('This email is not a draft and cannot be edited.', 'error')
        return redirect(url_for('index'))
    
    return render_template('compose.html', email=email)

@app.route('/draft/<int:email_id>/send', methods=['POST'])
def send_draft(email_id):
    """Send a draft email"""
    try:
        email = Email.query.get_or_404(email_id)
        if not email.is_draft:
            flash('This email is not a draft.', 'error')
            return redirect(url_for('index'))
        
        success, message = email_service.send_email(email)
        if success:
            email.is_sent = True
            email.is_draft = False
            email.sent_at = datetime.utcnow()
            email.message_id = message
            flash('Draft sent successfully!', 'success')
        else:
            email.error_message = message
            flash(f'Failed to send draft: {message}', 'error')
        
        db.session.commit()
        
    except Exception as e:
        logging.error(f"Error sending draft: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('sent'))

@app.route('/api/emails/status')
@csrf.exempt
def email_status():
    """API endpoint to check email sending status"""
    pending_emails = Email.query.filter_by(is_sent=False, is_draft=False).count()
    return jsonify({'pending_emails': pending_emails})

# ── Maintenance Mode Admin Controls ──────────────────────────────────────────

@app.route('/maintenance')
def maintenance_page():
    """Direct URL to view the maintenance page (for preview purposes)."""
    features_raw = SystemConfig.get('maintenance_features', '')
    features = [f.strip() for f in features_raw.split('|') if f.strip()]
    message = SystemConfig.get('maintenance_message', '')
    return render_template('maintenance.html', features=features, message=message)


@app.route('/admin/maintenance/toggle', methods=['POST'])
@login_required
@security_check
def admin_toggle_maintenance():
    """Enable or disable maintenance mode."""
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    action = request.form.get('action')
    if action == 'enable':
        message = request.form.get('message', '').strip()
        features_raw = request.form.get('features', '').strip()
        SystemConfig.set('maintenance_mode', 'on')
        SystemConfig.set('maintenance_message', message)
        SystemConfig.set('maintenance_features', features_raw)
        flash('Maintenance mode is now ON. Regular users will see the maintenance page.', 'warning')
    elif action == 'disable':
        SystemConfig.set('maintenance_mode', 'off')
        flash('Maintenance mode is now OFF. The site is live for all users.', 'success')
    return redirect(url_for('admin_dashboard'))


# ── Password Reset ────────────────────────────────────────────────────────────

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Invalidate old tokens
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({'used': True})
            token = PasswordResetToken(
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            db.session.add(token)
            db.session.commit()
            base_url = request.host_url.rstrip('/')
            send_password_reset_email(user, token.token, base_url)
        # Always show success to prevent email enumeration
        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', form=form)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    record = PasswordResetToken.query.filter_by(token=token).first()
    if not record or not record.is_valid():
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        record.user.set_password(form.password.data)
        record.used = True
        db.session.commit()
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form, token=token)


# ── Email Verification ────────────────────────────────────────────────────────

@app.route('/verify-email/<token>')
def verify_email(token):
    record = EmailVerificationToken.query.filter_by(token=token).first()
    if not record or not record.is_valid():
        return render_template('verify_email.html', success=False, error='This link is invalid or has expired.')
    record.user.is_verified = True
    record.used = True
    db.session.commit()
    return render_template('verify_email.html', success=True)


@app.route('/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    if current_user.is_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('profile'))
    # Invalidate old tokens
    EmailVerificationToken.query.filter_by(user_id=current_user.id, used=False).update({'used': True})
    token = EmailVerificationToken(
        user_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.session.add(token)
    db.session.commit()
    base_url = request.host_url.rstrip('/')
    send_verification_email(current_user, token.token, base_url)
    flash('Verification email sent! Check your inbox.', 'success')
    return redirect(url_for('profile'))


# ── Two-Factor Authentication ─────────────────────────────────────────────────

@app.route('/profile/2fa/setup', methods=['GET', 'POST'])
@login_required
def two_factor_setup():
    if current_user.totp_enabled:
        flash('2FA is already enabled.', 'info')
        return redirect(url_for('profile'))

    # Generate or reuse a pending secret stored in session
    if 'pending_totp_secret' not in session:
        session['pending_totp_secret'] = pyotp.random_base32()
    secret = session['pending_totp_secret']

    # Build TOTP URI and QR code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.email, issuer_name='Email Server')
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    form = TwoFactorSetupForm()
    if form.validate_on_submit():
        if totp.verify(form.code.data, valid_window=1):
            # Generate backup codes
            backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
            current_user.totp_secret = secret
            current_user.totp_enabled = True
            current_user.totp_backup_codes = ','.join(backup_codes)
            db.session.commit()
            session.pop('pending_totp_secret', None)
            flash('Two-factor authentication is now enabled! Save your backup codes: ' + ', '.join(backup_codes), 'success')
            return redirect(url_for('profile'))
        else:
            flash('Invalid code. Please try again.', 'error')

    return render_template('2fa_setup.html', form=form, secret=secret, qr_code=qr_b64)


@app.route('/profile/2fa/disable', methods=['POST'])
@login_required
def two_factor_disable():
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    db.session.commit()
    flash('Two-factor authentication has been disabled.', 'info')
    return redirect(url_for('profile'))


@app.route('/auth/2fa/verify', methods=['GET', 'POST'])
def two_factor_verify():
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if not user:
        session.pop('pending_2fa_user_id', None)
        return redirect(url_for('login'))

    form = TwoFactorVerifyForm()
    if form.validate_on_submit():
        code = form.code.data.strip()
        totp = pyotp.TOTP(user.totp_secret)
        valid = totp.verify(code, valid_window=1)

        # Check backup codes
        if not valid and user.totp_backup_codes:
            backup_codes = user.totp_backup_codes.split(',')
            if code.upper() in backup_codes:
                valid = True
                backup_codes.remove(code.upper())
                user.totp_backup_codes = ','.join(backup_codes)
                db.session.commit()

        if valid:
            remember = session.pop('pending_2fa_remember', False)
            session.pop('pending_2fa_user_id', None)
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid code. Please try again.', 'error')

    return render_template('2fa_verify.html', form=form)


# ── API Token Management ──────────────────────────────────────────────────────

@app.route('/profile/api-tokens')
@login_required
def api_tokens():
    form = APITokenForm()
    tokens = APIToken.query.filter_by(user_id=current_user.id).order_by(APIToken.created_at.desc()).all()
    new_token = session.pop('new_api_token', None)
    return render_template('api_tokens.html', form=form, tokens=tokens, new_token=new_token)


@app.route('/profile/api-tokens/create', methods=['POST'])
@login_required
def create_api_token():
    form = APITokenForm()
    if form.validate_on_submit():
        token = APIToken(user_id=current_user.id, name=form.name.data)
        db.session.add(token)
        db.session.commit()
        session['new_api_token'] = token.token
        flash(f'Token "{token.name}" created. Copy it now — it won\'t be shown again.', 'success')
    return redirect(url_for('api_tokens'))


@app.route('/profile/api-tokens/<int:token_id>/revoke', methods=['POST'])
@login_required
def revoke_api_token(token_id):
    token = APIToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    token.is_active = False
    db.session.commit()
    flash(f'Token "{token.name}" has been revoked.', 'info')
    return redirect(url_for('api_tokens'))


# ── Updated API auth: support both JWT and long-lived API tokens ──────────────

def _get_api_user():
    """Resolve a user from Authorization header — supports API tokens and JWTs."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    raw = auth[7:]
    # Try API token first
    token_record = APIToken.query.filter_by(token=raw, is_active=True).first()
    if token_record:
        token_record.last_used_at = datetime.utcnow()
        db.session.commit()
        return token_record.user
    # Fall back to JWT
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(raw, os.environ.get('SESSION_SECRET', 'secret'), algorithms=['HS256'])
        return User.query.get(payload['user_id'])
    except Exception:
        return None


@app.route('/api/user/me')
@csrf.exempt
def api_user_me():
    """Return the authenticated user's profile."""
    user = _get_api_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'is_verified': user.is_verified,
        'is_admin': user.is_admin,
        'totp_enabled': user.totp_enabled,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
    })


# ── Admin Settings & Firewall ────────────────────────────────────────────────

@app.route('/admin/settings')
@login_required
@security_check
def admin_settings():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    maintenance_on = SystemConfig.get('maintenance_mode', 'off') == 'on'
    maintenance_message = SystemConfig.get('maintenance_message', '')
    maintenance_features = SystemConfig.get('maintenance_features', '')
    policy = {
        'max_login_attempts': SystemConfig.get('max_login_attempts', '5'),
        'ban_duration_minutes': SystemConfig.get('ban_duration_minutes', '30'),
        'session_timeout': SystemConfig.get('session_timeout', '0'),
        'min_password_length': SystemConfig.get('min_password_length', '8'),
        'require_2fa': SystemConfig.get('require_2fa', 'off') == 'on',
        'require_email_verify': SystemConfig.get('require_email_verify', 'off') == 'on',
    }
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(active=True).count(),
        'sso_apps': OAuthApp.query.count(),
        'blocked_ips': FirewallRule.query.filter_by(rule_type='block', is_active=True).count(),
    }
    firewall_rules = FirewallRule.query.order_by(FirewallRule.created_at.desc()).all()
    base_url = request.host_url.rstrip('/')
    org = {
        'domain': SystemConfig.get('org_domain', 'netlifegy.com'),
        'registration_mode': SystemConfig.get('registration_mode', 'open'),
        'require_approval': SystemConfig.get('require_account_approval', 'off') == 'on',
    }
    # Pending approval count
    pending_users = User.query.filter_by(active=False).count()
    return render_template('admin/settings.html',
        maintenance_on=maintenance_on,
        maintenance_message=maintenance_message,
        maintenance_features=maintenance_features,
        policy=policy,
        stats=stats,
        firewall_rules=firewall_rules,
        base_url=base_url,
        org=org,
        pending_users=pending_users)


@app.route('/admin/firewall/add', methods=['POST'])
@login_required
@security_check
def admin_firewall_add():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    ip_or_cidr = request.form.get('ip_or_cidr', '').strip()
    rule_type = request.form.get('rule_type', 'block')
    description = request.form.get('description', '').strip()
    if not ip_or_cidr:
        flash('IP address or CIDR is required.', 'error')
        return redirect(url_for('admin_settings') + '#firewall')
    import ipaddress
    try:
        if '/' in ip_or_cidr:
            ipaddress.ip_network(ip_or_cidr, strict=False)
        else:
            ipaddress.ip_address(ip_or_cidr)
    except ValueError:
        flash(f'"{ip_or_cidr}" is not a valid IP address or CIDR range.', 'error')
        return redirect(url_for('admin_settings') + '#firewall')
    rule = FirewallRule(rule_type=rule_type, ip_or_cidr=ip_or_cidr,
                        description=description, created_by=current_user.id)
    db.session.add(rule)
    db.session.commit()
    flash(f'Firewall rule added: {rule_type.upper()} {ip_or_cidr}', 'success')
    return redirect(url_for('admin_settings') + '#firewall')


@app.route('/admin/firewall/<int:rule_id>/toggle', methods=['POST'])
@login_required
@security_check
def admin_firewall_toggle(rule_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    rule = FirewallRule.query.get_or_404(rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    flash(f'Rule {"activated" if rule.is_active else "paused"}.', 'success')
    return redirect(url_for('admin_settings') + '#firewall')


@app.route('/admin/firewall/<int:rule_id>/delete', methods=['POST'])
@login_required
@security_check
def admin_firewall_delete(rule_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    rule = FirewallRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    flash('Firewall rule deleted.', 'success')
    return redirect(url_for('admin_settings') + '#firewall')


@app.route('/admin/settings/policy', methods=['POST'])
@login_required
@security_check
def admin_save_policy():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    fields = ['max_login_attempts', 'ban_duration_minutes', 'session_timeout', 'min_password_length']
    for f in fields:
        val = request.form.get(f, '').strip()
        if val:
            SystemConfig.set(f, val)
    SystemConfig.set('require_2fa', 'on' if request.form.get('require_2fa') else 'off')
    SystemConfig.set('require_email_verify', 'on' if request.form.get('require_email_verify') else 'off')
    flash('Security policy saved.', 'success')
    return redirect(url_for('admin_settings') + '#policy')


@app.route('/admin/save-org', methods=['POST'])
@login_required
@security_check
def admin_save_org():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    domain = request.form.get('org_domain', '').strip().lower()
    if domain:
        # Strip any leading '@' or 'username@' text if typed
        if '@' in domain:
            domain = domain.split('@')[-1]
        SystemConfig.set('org_domain', domain)
    SystemConfig.set('registration_mode', request.form.get('registration_mode', 'open'))
    SystemConfig.set('require_account_approval', 'on' if request.form.get('require_account_approval') else 'off')
    flash('Organization settings saved.', 'success')
    return redirect(url_for('admin_settings') + '#org')


# ── OAuth / SSO Admin Routes ──────────────────────────────────────────────────

@app.route('/admin/oauth-apps')
@login_required
@security_check
def admin_oauth_apps():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    pending_apps = OAuthApp.query.filter_by(is_pending=True).order_by(OAuthApp.created_at.desc()).all()
    active_apps  = OAuthApp.query.filter_by(is_pending=False).order_by(OAuthApp.created_at.desc()).all()
    base_url = request.host_url.rstrip('/')
    return render_template('admin/oauth_apps.html',
                           apps=active_apps, pending_apps=pending_apps, base_url=base_url)


@app.route('/admin/oauth-apps/create', methods=['POST'])
@login_required
@security_check
def admin_create_oauth_app():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    name = request.form.get('name', '').strip()
    redirect_uris = request.form.get('redirect_uris', '').strip()
    if not name or not redirect_uris:
        flash('App name and at least one redirect URI are required.', 'error')
        return redirect(url_for('admin_oauth_apps'))
    app_record = OAuthApp(
        name=name,
        description=request.form.get('description', '').strip(),
        website_url=request.form.get('website_url', '').strip(),
        logo_url=request.form.get('logo_url', '').strip(),
        redirect_uris=redirect_uris,
        created_by=current_user.id
    )
    db.session.add(app_record)
    db.session.commit()
    flash(f'"{name}" registered successfully.', 'success')
    return redirect(url_for('admin_oauth_apps'))


@app.route('/admin/oauth-apps/<int:app_id>/regenerate-secret', methods=['POST'])
@login_required
@security_check
def admin_regenerate_oauth_secret(app_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    import secrets as _secrets
    app_record = OAuthApp.query.get_or_404(app_id)
    app_record.client_secret = _secrets.token_urlsafe(64)
    db.session.commit()
    flash('Client secret regenerated. Update your integration immediately.', 'warning')
    return redirect(url_for('admin_oauth_apps'))


@app.route('/admin/oauth-apps/<int:app_id>/toggle', methods=['POST'])
@login_required
@security_check
def admin_toggle_oauth_app(app_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    app_record = OAuthApp.query.get_or_404(app_id)
    app_record.is_active = not app_record.is_active
    db.session.commit()
    status = 'activated' if app_record.is_active else 'deactivated'
    flash(f'"{app_record.name}" has been {status}.', 'success')
    return redirect(url_for('admin_oauth_apps'))


@app.route('/admin/oauth-apps/<int:app_id>/delete', methods=['POST'])
@login_required
@security_check
def admin_delete_oauth_app(app_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    app_record = OAuthApp.query.get_or_404(app_id)
    name = app_record.name
    db.session.delete(app_record)
    db.session.commit()
    flash(f'"{name}" has been deleted.', 'success')
    return redirect(url_for('admin_oauth_apps'))


# ── Developer Portal ─────────────────────────────────────────────────────────

@app.route('/developers')
def developers():
    base_url = request.host_url.rstrip('/')
    return render_template('developers.html', base_url=base_url)


@app.route('/developers/apps')
@login_required
def developer_my_apps():
    from models import OAuthApp
    my_apps = OAuthApp.query.filter_by(created_by=current_user.id).order_by(OAuthApp.created_at.desc()).all()
    base_url = request.host_url.rstrip('/')
    return render_template('developer_apps.html', apps=my_apps, base_url=base_url)


@app.route('/developers/apps/register', methods=['GET', 'POST'])
@login_required
def developer_register_app():
    from models import OAuthApp
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        redirect_uris = request.form.get('redirect_uris', '').strip()
        if not name or not redirect_uris:
            flash('App name and at least one redirect URI are required.', 'error')
            return redirect(url_for('developer_register_app'))

        # Admins get immediate approval; regular users submit for review
        is_pending = not current_user.is_admin
        app_record = OAuthApp(
            name=name,
            description=request.form.get('description', '').strip(),
            website_url=request.form.get('website_url', '').strip(),
            logo_url=request.form.get('logo_url', '').strip(),
            redirect_uris=redirect_uris,
            is_pending=is_pending,
            is_active=not is_pending,
            developer_email=current_user.email,
            developer_name=current_user.full_name,
            created_by=current_user.id,
        )
        db.session.add(app_record)
        db.session.commit()

        if is_pending:
            flash(f'"{name}" submitted for admin review. You\'ll be able to use it once approved.', 'info')
        else:
            flash(f'"{name}" registered and ready to use.', 'success')
        return redirect(url_for('developer_my_apps'))

    return render_template('developer_register.html')


@app.route('/admin/oauth-apps/<int:app_id>/approve', methods=['POST'])
@login_required
@security_check
def admin_approve_oauth_app(app_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    from models import OAuthApp
    app_record = OAuthApp.query.get_or_404(app_id)
    app_record.is_pending = False
    app_record.is_active = True
    db.session.commit()
    flash(f'"{app_record.name}" approved and activated.', 'success')
    return redirect(url_for('admin_oauth_apps'))


@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message='Internal server error'), 500

# ── App Release routes ─────────────────────────────────────────────────────────

RELEASES_DIR = os.path.join(os.path.dirname(__file__), 'static', 'releases')
ALLOWED_RELEASE_EXT = {'.apk', '.ipa', '.zip'}
MAX_RELEASE_SIZE = 200 * 1024 * 1024  # 200 MB

@app.route('/download')
def download_page():
    android = (AppRelease.query
               .filter_by(platform='android', is_active=True)
               .order_by(AppRelease.created_at.desc()).first())
    ios = (AppRelease.query
           .filter_by(platform='ios', is_active=True)
           .order_by(AppRelease.created_at.desc()).first())
    return render_template('download.html', android=android, ios=ios)

@app.route('/download/release/<int:release_id>')
def download_release(release_id):
    from flask import send_from_directory
    rel = AppRelease.query.get_or_404(release_id)
    return send_from_directory(RELEASES_DIR, rel.filename,
                               as_attachment=True,
                               download_name=rel.original_name or rel.filename)

@app.route('/download/android-studio-project')
def download_android_project():
    """Download the pre-built Android Studio project ZIP."""
    from flask import send_from_directory
    zip_path = os.path.join(RELEASES_DIR, 'netlifegy-android-studio.zip')
    if not os.path.exists(zip_path):
        flash('Android Studio project file not found.', 'error')
        return redirect(url_for('download_page'))
    return send_from_directory(RELEASES_DIR, 'netlifegy-android-studio.zip',
                               as_attachment=True,
                               download_name='NetlifegyMail-AndroidStudio.zip')

@app.route('/api/app/version')
@csrf.exempt
def api_app_version():
    android = (AppRelease.query
               .filter_by(platform='android', is_active=True)
               .order_by(AppRelease.created_at.desc()).first())
    ios = (AppRelease.query
           .filter_by(platform='ios', is_active=True)
           .order_by(AppRelease.created_at.desc()).first())
    return jsonify({
        'android': android.to_dict() if android else None,
        'ios':     ios.to_dict()     if ios else None,
    })

@app.route('/admin/app-releases')
@login_required
def admin_app_releases():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    releases = AppRelease.query.order_by(AppRelease.created_at.desc()).all()
    return render_template('admin/app_releases.html', releases=releases)

@app.route('/admin/app-releases/upload', methods=['POST'])
@login_required
def admin_upload_release():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    version  = request.form.get('version', '').strip()
    platform = request.form.get('platform', 'android')
    notes    = request.form.get('release_notes', '').strip()
    notify   = 'notify_users' in request.form
    f        = request.files.get('release_file')

    if not version or not f or not f.filename:
        flash('Version and file are required.', 'error')
        return redirect(url_for('admin_app_releases'))

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_RELEASE_EXT:
        flash(f'File type {ext} not allowed.', 'error')
        return redirect(url_for('admin_app_releases'))

    os.makedirs(RELEASES_DIR, exist_ok=True)
    safe_ver  = version.replace('/', '-').replace('..', '')
    stored    = f"netlifegy-{platform}-v{safe_ver}-{secrets.token_hex(4)}{ext}"
    dest      = os.path.join(RELEASES_DIR, stored)
    f.save(dest)
    size      = os.path.getsize(dest)

    # Deactivate previous releases for this platform
    AppRelease.query.filter_by(platform=platform, is_active=True).update({'is_active': False})

    rel = AppRelease(
        version=version,
        platform=platform,
        filename=stored,
        original_name=f.filename,
        file_size=size,
        release_notes=notes,
        is_active=True,
        uploaded_by=current_user.id,
    )
    db.session.add(rel)

    # Store notify flag in SystemConfig so the update banner picks it up
    if notify:
        cfg = SystemConfig.query.filter_by(key='app_update_version').first()
        if not cfg:
            cfg = SystemConfig(key='app_update_version')
            db.session.add(cfg)
        cfg.value = version

        cfg2 = SystemConfig.query.filter_by(key='app_update_platform').first()
        if not cfg2:
            cfg2 = SystemConfig(key='app_update_platform')
            db.session.add(cfg2)
        cfg2.value = platform

    db.session.commit()
    flash(f'Version {version} uploaded and published successfully.', 'success')
    return redirect(url_for('admin_app_releases'))

@app.route('/admin/app-releases/<int:release_id>/delete', methods=['POST'])
@login_required
def admin_delete_release(release_id):
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    rel = AppRelease.query.get_or_404(release_id)
    try:
        fp = os.path.join(RELEASES_DIR, rel.filename)
        if os.path.exists(fp):
            os.remove(fp)
    except Exception:
        pass
    db.session.delete(rel)
    db.session.commit()
    flash(f'Release v{rel.version} deleted.', 'success')
    return redirect(url_for('admin_app_releases'))

@app.route('/api/app/update-banner')
@csrf.exempt
def api_update_banner():
    """Returns pending update info so the PWA can show an update banner."""
    ver_cfg = SystemConfig.query.filter_by(key='app_update_version').first()
    plt_cfg = SystemConfig.query.filter_by(key='app_update_platform').first()
    if not ver_cfg:
        return jsonify({'update': False})
    return jsonify({
        'update': True,
        'version': ver_cfg.value,
        'platform': plt_cfg.value if plt_cfg else 'android',
        'download_url': url_for('download_page', _external=True),
    })

# ── PWA routes ─────────────────────────────────────────────────────────────────

@app.route('/sw.js')
def pwa_sw():
    """Serve service worker from root scope (required by browsers)."""
    from flask import send_from_directory
    response = send_from_directory('static', 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.route('/offline')
def pwa_offline():
    return render_template('offline.html')
