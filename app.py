import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

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

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    
    db.create_all()
    
    # Import routes after app context is established
    import routes  # noqa: F401
