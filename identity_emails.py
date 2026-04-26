import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from app import app


def _get_smtp_config():
    return {
        'server': app.config.get('SMTP_SERVER', ''),
        'port': app.config.get('SMTP_PORT', 587),
        'username': app.config.get('SMTP_USERNAME', ''),
        'password': app.config.get('SMTP_PASSWORD', ''),
        'sender': app.config.get('DEFAULT_SENDER', ''),
    }


def _send_system_email(to_address, subject, body_text, body_html):
    config = _get_smtp_config()
    if not all([config['server'], config['username'], config['password']]):
        logging.warning(f"[Identity] SMTP not configured. Would have sent '{subject}' to {to_address}")
        logging.info(f"[Identity] Email body: {body_text}")
        return False, "SMTP not configured"
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config['sender'] or config['username']
        msg['To'] = to_address
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid()
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        context = ssl.create_default_context()
        with smtplib.SMTP(config['server'], config['port']) as server:
            server.starttls(context=context)
            server.login(config['username'], config['password'])
            server.sendmail(msg['From'], to_address, msg.as_string())
        logging.info(f"[Identity] Sent '{subject}' to {to_address}")
        return True, "Sent"
    except Exception as e:
        logging.error(f"[Identity] Failed to send '{subject}' to {to_address}: {e}")
        return False, str(e)


def send_verification_email(user, token, base_url):
    link = f"{base_url}/verify-email/{token}"
    subject = "Verify your email address"
    body_text = (
        f"Hi {user.full_name},\n\n"
        f"Please verify your email address by clicking the link below:\n\n"
        f"{link}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you did not create an account, you can ignore this email."
    )
    body_html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;">
      <h2>Verify your email address</h2>
      <p>Hi {user.full_name},</p>
      <p>Please verify your email address by clicking the button below:</p>
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#0d6efd;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">
          Verify Email
        </a>
      </p>
      <p>Or copy this link: <code>{link}</code></p>
      <p>This link expires in <strong>24 hours</strong>.</p>
      <hr><p style="color:#888;font-size:12px;">If you did not create an account, you can ignore this email.</p>
    </body></html>
    """
    return _send_system_email(user.email, subject, body_text, body_html)


def send_password_reset_email(user, token, base_url):
    link = f"{base_url}/reset-password/{token}"
    subject = "Reset your password"
    body_text = (
        f"Hi {user.full_name},\n\n"
        f"Someone requested a password reset for your account.\n\n"
        f"Click the link below to reset your password:\n\n"
        f"{link}\n\n"
        f"This link expires in 1 hour.\n\n"
        f"If you did not request this, you can safely ignore this email."
    )
    body_html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;">
      <h2>Reset your password</h2>
      <p>Hi {user.full_name},</p>
      <p>Someone requested a password reset for your account.</p>
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#dc3545;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">
          Reset Password
        </a>
      </p>
      <p>Or copy this link: <code>{link}</code></p>
      <p>This link expires in <strong>1 hour</strong>.</p>
      <hr><p style="color:#888;font-size:12px;">If you did not request this, you can safely ignore this email.</p>
    </body></html>
    """
    return _send_system_email(user.email, subject, body_text, body_html)
