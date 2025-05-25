#!/bin/bash

# Quick Install Script for Email Server on Ubuntu
# This is a simplified version for users who want to get started quickly

set -e

echo "🚀 Email Server Quick Installation"
echo "=================================="
echo ""

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    echo "❌ This script is for Ubuntu systems only."
    exit 1
fi

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run as root or with sudo."
    echo "Please run: sudo ./quick_install.sh"
    exit 1
fi

echo "✅ Ubuntu system detected"
echo "✅ Sudo privileges confirmed"
echo ""

# Update system
echo "📦 Updating system packages..."
apt update -qq

# Install basic requirements
echo "🔧 Installing basic requirements..."
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx ufw curl

# Create database
echo "🗄️  Setting up database..."
DB_PASSWORD=$(openssl rand -base64 12)
su - postgres -c "psql -c \"CREATE DATABASE emailserver;\"" 2>/dev/null || echo "Database may already exist"
su - postgres -c "psql -c \"CREATE USER emailserver_user WITH PASSWORD '$DB_PASSWORD';\"" 2>/dev/null || echo "User may already exist"
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE emailserver TO emailserver_user;\"" 2>/dev/null

# Create environment file
echo "⚙️  Creating configuration..."
cat > .env << EOF
DATABASE_URL=postgresql://emailserver_user:$DB_PASSWORD@localhost:5432/emailserver
SESSION_SECRET=$(openssl rand -base64 32)
FLASK_ENV=production

# Update these with your email settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
DEFAULT_SENDER=noreply@yourdomain.com
EOF

# Setup Python environment
echo "🐍 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip

# Install Python packages
pip install -q flask flask-login flask-sqlalchemy flask-wtf wtforms email-validator werkzeug gunicorn psycopg2-binary pillow python-dotenv

# Create directories
mkdir -p static/profile_pics logs

# Initialize database
echo "🔑 Creating admin user..."
python3 create_admin.py

# Setup basic firewall
echo "🛡️  Configuring firewall..."
ufw --force enable
ufw allow ssh
ufw allow 80
ufw allow 443

# Create simple start script
cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
source .env
echo "Starting Email Server on http://localhost:5000"
python3 main.py
EOF
chmod +x start.sh

echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo ""
echo "📋 Quick Start:"
echo "1. Edit .env file with your email settings"
echo "2. Run: ./start.sh"
echo "3. Open: http://localhost:5000"
echo ""
echo "🔐 Default Login:"
echo "Username: admin"
echo "Password: admin123"
echo ""
echo "⚠️  Important:"
echo "- Change the admin password after first login"
echo "- Configure your SMTP settings in .env file"
echo "- For production, run the full install_ubuntu.sh script"
echo ""
echo "🔗 Access your email server at: http://$(hostname -I | awk '{print $1}'):5000"