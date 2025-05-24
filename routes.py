from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import Email, EmailConfig, User
from email_service import EmailService
from forms import LoginForm, RegistrationForm, ProfileForm, ChangePasswordForm, AdminUserForm
from security import security_manager, security_check, login_security_check, SecurityBan, SecurityLog
from backup_service import backup_service
from datetime import datetime
import logging
import os
from werkzeug.utils import secure_filename
from PIL import Image

email_service = EmailService()

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
            # Record successful login
            security_manager.record_successful_login(user)
            
            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
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
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # Handle profile picture upload
            profile_picture = None
            if form.profile_photo.data:
                profile_picture = save_profile_picture(form.profile_photo.data)
            
            # Create new user
            user = User(
                username=form.username.data,
                email=form.email.data,
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
                use_tls=form.use_tls.data
            )
            user.set_password(form.password.data)
            
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Registration error: {str(e)}")
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html', form=form)

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
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         active_users=active_users,
                         admin_users=admin_users,
                         total_emails=total_emails,
                         security_stats=security_stats,
                         recent_users=recent_users)

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin user management"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

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
def email_status():
    """API endpoint to check email sending status"""
    pending_emails = Email.query.filter_by(is_sent=False, is_draft=False).count()
    return jsonify({'pending_emails': pending_emails})

@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message='Internal server error'), 500
