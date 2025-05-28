#!/bin/bash

# Complete Email Server Installation Script for Ubuntu
# This script includes all features: domain management, backup system, security, and mobile API

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Complete Email Server Installation${NC}"
echo -e "${BLUE}====================================${NC}"
echo ""

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}❌ This script must be run as root or with sudo.${NC}"
    echo "Please run: sudo ./install_complete.sh"
    exit 1
fi

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    echo -e "${RED}❌ This script is for Ubuntu systems only.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Ubuntu system detected${NC}"
echo -e "${GREEN}✅ Root privileges confirmed${NC}"
echo ""

# Update system
echo -e "${YELLOW}📦 Updating system packages...${NC}"
apt update -qq
apt upgrade -y -qq

# Install required packages
echo -e "${YELLOW}🔧 Installing required packages...${NC}"
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx ufw curl openssl fail2ban certbot python3-certbot-nginx

# Create application directory
APP_DIR="/opt/emailserver"
echo -e "${YELLOW}📁 Creating application directory: $APP_DIR${NC}"
mkdir -p $APP_DIR
cd $APP_DIR

# Copy application files (assuming script is run from project directory)
echo -e "${YELLOW}📋 Copying application files...${NC}"
cp -r /home/runner/workspace/* $APP_DIR/ 2>/dev/null || {
    echo -e "${YELLOW}⚠️  Please copy your email server files to $APP_DIR${NC}"
    echo "Required files: *.py, templates/, static/, mobile_app/, etc."
}

# Set up Python environment
echo -e "${YELLOW}🐍 Setting up Python environment...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy flask-wtf wtforms email-validator werkzeug gunicorn psycopg2-binary pillow python-dotenv psutil

# Create database
echo -e "${YELLOW}🗄️  Setting up PostgreSQL database...${NC}"
DB_PASSWORD=$(openssl rand -base64 16)
SESSION_SECRET=$(openssl rand -base64 32)

# Configure PostgreSQL
systemctl start postgresql
systemctl enable postgresql

su - postgres -c "psql -c \"CREATE DATABASE emailserver;\"" 2>/dev/null || echo "Database may already exist"
su - postgres -c "psql -c \"CREATE USER emailserver_user WITH PASSWORD '$DB_PASSWORD';\"" 2>/dev/null || echo "User may already exist"
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE emailserver TO emailserver_user;\"" 2>/dev/null

# Create environment configuration
echo -e "${YELLOW}⚙️  Creating environment configuration...${NC}"
cat > .env << EOF
# Database Configuration
DATABASE_URL=postgresql://emailserver_user:$DB_PASSWORD@localhost:5432/emailserver

# Security Configuration
SESSION_SECRET=$SESSION_SECRET
FLASK_ENV=production

# Email Server Configuration (Update with your settings)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
DEFAULT_SENDER=noreply@yourdomain.com

# Server Configuration
SERVER_NAME=localhost
PREFERRED_URL_SCHEME=https
EOF

# Create required directories
mkdir -p static/profile_pics logs backups

# Initialize database with all tables
echo -e "${YELLOW}🔑 Initializing database and creating admin user...${NC}"
source venv/bin/activate
python3 -c "
from app import app, db
try:
    from domain_config import DomainConfig
    from backup_service import backup_service
    from security import SecurityBan, SecurityLog
except ImportError as e:
    print(f'Warning: Some modules not found: {e}')

with app.app_context():
    db.create_all()
    print('✅ All database tables created successfully!')
"

# Create admin user
python3 create_admin.py

# Configure Nginx
echo -e "${YELLOW}🌐 Configuring Nginx...${NC}"
cat > /etc/nginx/sites-available/emailserver << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API endpoints for mobile app
    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers for mobile app
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS, PUT, DELETE';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/emailserver /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Configure fail2ban
echo -e "${YELLOW}🛡️  Configuring fail2ban security...${NC}"
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
EOF

systemctl enable fail2ban
systemctl start fail2ban

# Configure firewall
echo -e "${YELLOW}🔥 Configuring firewall...${NC}"
ufw --force enable
ufw allow ssh
ufw allow 80
ufw allow 443
ufw allow 5000

# Create systemd service
echo -e "${YELLOW}⚙️  Creating systemd service...${NC}"
cat > /etc/systemd/system/emailserver.service << EOF
[Unit]
Description=Email Server
After=network.target

[Service]
Type=notify
User=root
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start and enable service
systemctl daemon-reload
systemctl enable emailserver
systemctl start emailserver

# Create management scripts
echo -e "${YELLOW}📝 Creating management scripts...${NC}"

# Start script
cat > start.sh << 'EOF'
#!/bin/bash
systemctl start emailserver
systemctl status emailserver
EOF

# Stop script
cat > stop.sh << 'EOF'
#!/bin/bash
systemctl stop emailserver
EOF

# Restart script
cat > restart.sh << 'EOF'
#!/bin/bash
systemctl restart emailserver
systemctl status emailserver
EOF

# Status script
cat > status.sh << 'EOF'
#!/bin/bash
echo "=== Email Server Status ==="
systemctl status emailserver
echo ""
echo "=== Database Status ==="
systemctl status postgresql
echo ""
echo "=== Nginx Status ==="
systemctl status nginx
echo ""
echo "=== Firewall Status ==="
ufw status
echo ""
echo "=== Recent Logs ==="
journalctl -u emailserver --no-pager -n 10
EOF

chmod +x *.sh

# Set proper permissions
chown -R root:root $APP_DIR
chmod -R 755 $APP_DIR
chmod 600 $APP_DIR/.env

echo ""
echo -e "${GREEN}🎉 Email Server Installation Complete!${NC}"
echo -e "${GREEN}====================================${NC}"
echo ""
echo -e "${BLUE}📋 Installation Summary:${NC}"
echo "• Email Server installed at: $APP_DIR"
echo "• Database: PostgreSQL configured and running"
echo "• Web Server: Nginx configured and running"
echo "• Security: fail2ban and UFW firewall enabled"
echo "• Service: systemd service created and started"
echo ""
echo -e "${BLUE}🔐 Default Admin Credentials:${NC}"
echo "• Username: netlifegy"
echo "• Password: Zxcvbnm90"
echo "• Email: netlifegy@emailserver.local"
echo ""
echo -e "${BLUE}🌐 Access Your Email Server:${NC}"
echo "• Local: http://localhost"
echo "• Network: http://$(hostname -I | awk '{print $1}')"
echo ""
echo -e "${BLUE}📱 Mobile App:${NC}"
echo "• Flutter app package: $APP_DIR/EmailServer_Mobile_App.tar.gz"
echo "• Update API URL in lib/services/api_service.dart"
echo ""
echo -e "${BLUE}⚙️  Management Commands:${NC}"
echo "• Start server: ./start.sh or systemctl start emailserver"
echo "• Stop server: ./stop.sh or systemctl stop emailserver"
echo "• Restart server: ./restart.sh or systemctl restart emailserver"
echo "• Check status: ./status.sh"
echo "• View logs: journalctl -u emailserver -f"
echo ""
echo -e "${YELLOW}⚠️  Important Next Steps:${NC}"
echo "1. Update .env file with your SMTP/IMAP settings"
echo "2. Configure your domain in the admin panel"
echo "3. Set up SSL certificates with: certbot --nginx"
echo "4. Test email functionality"
echo ""
echo -e "${GREEN}✅ Your email server is now ready for production use!${NC}"