import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# configure the database, relative to the app instance folder
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///emailserver.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Email configuration from environment variables
app.config.update(
    SMTP_SERVER=os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
    SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
    SMTP_USERNAME=os.environ.get("SMTP_USERNAME", ""),
    SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
    IMAP_SERVER=os.environ.get("IMAP_SERVER", "imap.gmail.com"),
    IMAP_PORT=int(os.environ.get("IMAP_PORT", "993")),
    DEFAULT_SENDER=os.environ.get("DEFAULT_SENDER", "noreply@example.com")
)

# initialize the app with the extension, flask-sqlalchemy >= 3.0.x
db.init_app(app)

# Enable CSRF protection (also registers csrf_token() as a Jinja2 global)
csrf = CSRFProtect(app)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    import security  # noqa: F401

    db.create_all()

    # Run safe column migrations for columns added after initial table creation
    from sqlalchemy import text
    _migrations = [
        "ALTER TABLE oauth_authorization_codes ADD COLUMN IF NOT EXISTS nonce VARCHAR(256)",
        "ALTER TABLE oauth_authorization_codes ADD COLUMN IF NOT EXISTS code_challenge VARCHAR(256)",
        "ALTER TABLE oauth_authorization_codes ADD COLUMN IF NOT EXISTS code_challenge_method VARCHAR(10)",
        "ALTER TABLE oauth_apps ADD COLUMN IF NOT EXISTS allowed_scopes VARCHAR(500) DEFAULT 'openid profile email phone'",
        "ALTER TABLE oauth_apps ADD COLUMN IF NOT EXISTS is_pending BOOLEAN DEFAULT FALSE",
        "ALTER TABLE oauth_apps ADD COLUMN IF NOT EXISTS developer_email VARCHAR(255)",
        "ALTER TABLE oauth_apps ADD COLUMN IF NOT EXISTS developer_name VARCHAR(255)",
    ]
    for _sql in _migrations:
        try:
            db.session.execute(text(_sql))
        except Exception:
            pass
    db.session.commit()

    # Import routes after app context is established
    import routes  # noqa: F401
    import oauth   # noqa: F401
