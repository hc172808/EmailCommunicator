from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app, db
from models import Email, EmailConfig
from email_service import EmailService
from datetime import datetime
import logging

email_service = EmailService()

@app.route('/')
def index():
    """Main dashboard showing email statistics"""
    total_emails = Email.query.count()
    sent_emails = Email.query.filter_by(is_sent=True).count()
    received_emails = Email.query.filter_by(is_received=True).count()
    draft_emails = Email.query.filter_by(is_draft=True).count()
    
    recent_emails = Email.query.order_by(Email.created_at.desc()).limit(5).all()
    
    return render_template('index.html', 
                         total_emails=total_emails,
                         sent_emails=sent_emails,
                         received_emails=received_emails,
                         draft_emails=draft_emails,
                         recent_emails=recent_emails)

@app.route('/compose', methods=['GET', 'POST'])
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
