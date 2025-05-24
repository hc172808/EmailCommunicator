import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, make_msgid
import ssl
import logging
from app import app, db
from models import Email
from datetime import datetime
import re

class EmailService:
    """Service for handling email operations"""
    
    def __init__(self):
        self.smtp_server = app.config['SMTP_SERVER']
        self.smtp_port = app.config['SMTP_PORT']
        self.smtp_username = app.config['SMTP_USERNAME']
        self.smtp_password = app.config['SMTP_PASSWORD']
        self.imap_server = app.config['IMAP_SERVER']
        self.imap_port = app.config['IMAP_PORT']
        self.default_sender = app.config['DEFAULT_SENDER']
    
    def send_email(self, email_obj):
        """
        Send an email using SMTP
        Returns tuple (success: bool, message: str)
        """
        try:
            # Validate email configuration
            if not all([self.smtp_server, self.smtp_username, self.smtp_password]):
                return False, "SMTP configuration is incomplete. Please check environment variables."
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = email_obj.sender or self.default_sender
            msg['To'] = email_obj.recipient
            msg['Subject'] = email_obj.subject
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid()
            
            # Add text content
            if email_obj.body_text:
                text_part = MIMEText(email_obj.body_text, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Add HTML content if available
            if email_obj.body_html:
                html_part = MIMEText(email_obj.body_html, 'html', 'utf-8')
                msg.attach(html_part)
            
            # If no HTML content, convert text to HTML
            if not email_obj.body_html and email_obj.body_text:
                html_content = email_obj.body_text.replace('\n', '<br>')
                html_part = MIMEText(f'<html><body>{html_content}</body></html>', 'html', 'utf-8')
                msg.attach(html_part)
            
            # Connect to SMTP server
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                
                # Send email
                text = msg.as_string()
                server.sendmail(msg['From'], email_obj.recipient, text)
                
                logging.info(f"Email sent successfully to {email_obj.recipient}")
                return True, msg['Message-ID']
                
        except smtplib.SMTPAuthenticationError:
            error_msg = "SMTP Authentication failed. Please check your email credentials."
            logging.error(error_msg)
            return False, error_msg
            
        except smtplib.SMTPRecipientsRefused:
            error_msg = f"Recipient {email_obj.recipient} was refused by the server."
            logging.error(error_msg)
            return False, error_msg
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error occurred: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error sending email: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
    
    def fetch_emails(self, limit=50):
        """
        Fetch emails from IMAP server
        Returns tuple (success: bool, message: str)
        """
        try:
            # Check if IMAP configuration is available
            if not all([self.imap_server, self.smtp_username, self.smtp_password]):
                logging.warning("IMAP configuration is incomplete. Cannot fetch emails.")
                return False, "IMAP configuration is incomplete."
            
            # Connect to IMAP server
            context = ssl.create_default_context()
            
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port, ssl_context=context) as mail:
                mail.login(self.smtp_username, self.smtp_password)
                mail.select('INBOX')
                
                # Search for emails
                status, messages = mail.search(None, 'ALL')
                
                if status != 'OK':
                    return False, "Failed to search emails"
                
                email_ids = messages[0].split()
                
                # Fetch recent emails (limit to avoid overwhelming)
                recent_ids = email_ids[-limit:] if len(email_ids) > limit else email_ids
                
                for email_id in reversed(recent_ids):  # Most recent first
                    try:
                        # Fetch email
                        status, msg_data = mail.fetch(email_id, '(RFC822)')
                        
                        if status != 'OK':
                            continue
                        
                        # Parse email
                        email_message = email.message_from_bytes(msg_data[0][1])
                        
                        # Extract email details
                        sender = email_message['From']
                        recipient = email_message['To'] or self.smtp_username
                        subject = email_message['Subject'] or '(No Subject)'
                        message_id = email_message['Message-ID']
                        
                        # Check if email already exists
                        if message_id and Email.query.filter_by(message_id=message_id).first():
                            continue
                        
                        # Extract body
                        body_text = ""
                        body_html = ""
                        
                        if email_message.is_multipart():
                            for part in email_message.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if "attachment" not in content_disposition:
                                    if content_type == "text/plain":
                                        body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    elif content_type == "text/html":
                                        body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        else:
                            content_type = email_message.get_content_type()
                            if content_type == "text/plain":
                                body_text = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                            elif content_type == "text/html":
                                body_html = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        # Create email record
                        new_email = Email(
                            sender=sender,
                            recipient=recipient,
                            subject=subject,
                            body_text=body_text,
                            body_html=body_html,
                            is_received=True,
                            message_id=message_id,
                            created_at=datetime.utcnow()
                        )
                        
                        db.session.add(new_email)
                        
                    except Exception as e:
                        logging.error(f"Error processing email {email_id}: {str(e)}")
                        continue
                
                db.session.commit()
                logging.info(f"Successfully fetched emails")
                return True, "Emails fetched successfully"
                
        except imaplib.IMAP4.error as e:
            error_msg = f"IMAP error: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Error fetching emails: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
    
    def validate_email(self, email_address):
        """Validate email address format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email_address) is not None
    
    def test_connection(self):
        """Test SMTP and IMAP connections"""
        results = {}
        
        # Test SMTP
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                results['smtp'] = True
        except Exception as e:
            results['smtp'] = str(e)
        
        # Test IMAP
        try:
            context = ssl.create_default_context()
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port, ssl_context=context) as mail:
                mail.login(self.smtp_username, self.smtp_password)
                results['imap'] = True
        except Exception as e:
            results['imap'] = str(e)
        
        return results
