#!/bin/bash

# Quick deployment script for Email Server
# This script handles the application deployment after system setup

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
log "Installing Python dependencies..."
pip install --upgrade pip

# Install required packages
pip install \
    Flask==2.3.3 \
    Flask-Login==0.6.3 \
    Flask-SQLAlchemy==3.0.5 \
    Flask-WTF==1.2.1 \
    WTForms==3.1.0 \
    email-validator==2.1.0 \
    Werkzeug==2.3.7 \
    gunicorn==21.2.0 \
    psycopg2-binary==2.9.9 \
    Pillow==10.1.0 \
    python-dotenv==1.0.0

# Create directories
log "Creating necessary directories..."
mkdir -p static/profile_pics
mkdir -p logs

# Set permissions
chmod +x *.py
chmod 755 static/
chmod 755 templates/

# Load environment variables if .env exists
if [ -f ".env" ]; then
    export $(cat .env | xargs)
fi

# Initialize database and create admin user
if [ -f "create_admin.py" ]; then
    log "Setting up database and admin user..."
    python3 create_admin.py
fi

log "Deployment complete!"
info "You can now start the server with:"
info "  ./start_server.sh"
info "Or use the full installation script: ./install_ubuntu.sh"