#!/bin/bash

# Email Server Installation Script for Ubuntu
# This script installs and configures a complete email server with security features
# Compatible with Ubuntu 20.04, 22.04, and newer versions

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root for security reasons."
        error "Please run as a regular user with sudo privileges."
        exit 1
    fi
}

# Check Ubuntu version
check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release; then
        error "This script is designed for Ubuntu systems only."
        exit 1
    fi
    
    UBUNTU_VERSION=$(lsb_release -rs)
    log "Detected Ubuntu version: $UBUNTU_VERSION"
    
    if [[ $(echo "$UBUNTU_VERSION >= 20.04" | bc) -eq 0 ]]; then
        warning "Ubuntu 20.04 or newer is recommended."
    fi
}

# Update system packages
update_system() {
    log "Updating system packages..."
    sudo apt update
    sudo apt upgrade -y
    sudo apt autoremove -y
}

# Install system dependencies
install_system_deps() {
    log "Installing system dependencies..."
    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        libpq-dev \
        postgresql \
        postgresql-contrib \
        nginx \
        ufw \
        fail2ban \
        git \
        curl \
        wget \
        unzip \
        supervisor \
        certbot \
        python3-certbot-nginx \
        htop \
        tree \
        vim \
        nano
}

# Configure PostgreSQL
setup_postgresql() {
    log "Setting up PostgreSQL database..."
    
    # Start PostgreSQL service
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
    
    # Create database and user
    DB_NAME="emailserver"
    DB_USER="emailserver_user"
    DB_PASSWORD=$(openssl rand -base64 32)
    
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;"
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    sudo -u postgres psql -c "ALTER USER $DB_USER CREATEDB;"
    
    # Save database credentials
    cat > .env << EOF
# Database Configuration
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
PGHOST=localhost
PGPORT=5432
PGUSER=$DB_USER
PGPASSWORD=$DB_PASSWORD
PGDATABASE=$DB_NAME

# Flask Configuration
SESSION_SECRET=$(openssl rand -base64 32)
FLASK_ENV=production
FLASK_DEBUG=False

# Email Server Configuration (Update these with your SMTP settings)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
DEFAULT_SENDER=noreply@yourdomain.com
EOF
    
    log "Database credentials saved to .env file"
    info "Database Password: $DB_PASSWORD"
}

# Setup Python environment
setup_python_env() {
    log "Setting up Python virtual environment..."
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install Python dependencies
    log "Installing Python packages..."
    pip install \
        flask \
        flask-login \
        flask-wtf \
        flask-sqlalchemy \
        wtforms \
        email-validator \
        werkzeug \
        gunicorn \
        psycopg2-binary \
        pillow \
        python-dotenv
    
    # Save requirements
    pip freeze > requirements.txt
    
    log "Python environment setup complete"
}

# Configure Firewall (UFW)
setup_firewall() {
    log "Configuring UFW firewall..."
    
    # Reset UFW to defaults
    sudo ufw --force reset
    
    # Default policies
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    
    # Allow SSH (be careful!)
    sudo ufw allow ssh
    
    # Allow HTTP and HTTPS
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    
    # Allow email ports
    sudo ufw allow 25/tcp   # SMTP
    sudo ufw allow 587/tcp  # SMTP with STARTTLS
    sudo ufw allow 993/tcp  # IMAPS
    sudo ufw allow 995/tcp  # POP3S
    
    # Enable UFW
    sudo ufw --force enable
    
    log "Firewall configured and enabled"
}

# Configure Fail2Ban
setup_fail2ban() {
    log "Configuring Fail2Ban..."
    
    # Create custom jail for our email server
    sudo tee /etc/fail2ban/jail.d/emailserver.conf > /dev/null << 'EOF'
[emailserver-login]
enabled = true
port = http,https
filter = emailserver-login
logpath = /var/log/emailserver/security.log
maxretry = 5
bantime = 3600
findtime = 600

[nginx-http-auth]
enabled = true
port = http,https
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 6
bantime = 3600

[nginx-limit-req]
enabled = true
port = http,https
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 3600
EOF

    # Create custom filter for email server
    sudo tee /etc/fail2ban/filter.d/emailserver-login.conf > /dev/null << 'EOF'
[Definition]
failregex = ^.*failed_login.*ip_address.*<HOST>.*$
ignoreregex =
EOF

    # Create log directory
    sudo mkdir -p /var/log/emailserver
    sudo chown $USER:$USER /var/log/emailserver
    
    # Restart fail2ban
    sudo systemctl restart fail2ban
    sudo systemctl enable fail2ban
    
    log "Fail2Ban configured for email server protection"
}

# Configure Nginx
setup_nginx() {
    log "Configuring Nginx web server..."
    
    DOMAIN=${1:-"localhost"}
    
    # Create Nginx configuration
    sudo tee /etc/nginx/sites-available/emailserver > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
    
    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=login:10m rate=5r/m;
    limit_req_zone \$binary_remote_addr zone=general:10m rate=10r/s;
    
    location / {
        limit_req zone=general burst=20 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
    
    location /login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /static {
        alias $(pwd)/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    # Enable site
    sudo ln -sf /etc/nginx/sites-available/emailserver /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test configuration
    sudo nginx -t
    
    # Start Nginx
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    
    log "Nginx configured and started"
}

# Setup Supervisor for process management
setup_supervisor() {
    log "Setting up Supervisor for process management..."
    
    sudo tee /etc/supervisor/conf.d/emailserver.conf > /dev/null << EOF
[program:emailserver]
command=$(pwd)/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 3 --timeout 60 --keep-alive 2 --max-requests 1000 --max-requests-jitter 100 main:app
directory=$(pwd)
user=$USER
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/emailserver/app.log
stderr_logfile=/var/log/emailserver/error.log
environment=PATH="$(pwd)/venv/bin"
EOF

    # Update supervisor
    sudo supervisorctl reread
    sudo supervisorctl update
    
    log "Supervisor configured for automatic process management"
}

# Create systemd service as alternative
create_systemd_service() {
    log "Creating systemd service..."
    
    sudo tee /etc/systemd/system/emailserver.service > /dev/null << EOF
[Unit]
Description=Email Server Flask Application
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=exec
User=$USER
Group=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 3 main:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable emailserver
    
    log "Systemd service created and enabled"
}

# Initialize database
init_database() {
    log "Initializing database..."
    
    source venv/bin/activate
    
    # Load environment variables
    export $(cat .env | xargs)
    
    # Create admin user
    python3 create_admin.py
    
    log "Database initialized with admin user"
}

# Create management scripts
create_scripts() {
    log "Creating management scripts..."
    
    # Start script
    cat > start_server.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
source .env
gunicorn --bind 0.0.0.0:5000 --workers 3 main:app
EOF

    # Stop script
    cat > stop_server.sh << 'EOF'
#!/bin/bash
sudo supervisorctl stop emailserver
# or
# sudo systemctl stop emailserver
EOF

    # Restart script
    cat > restart_server.sh << 'EOF'
#!/bin/bash
sudo supervisorctl restart emailserver
# or
# sudo systemctl restart emailserver
EOF

    # Status script
    cat > status_server.sh << 'EOF'
#!/bin/bash
echo "=== Email Server Status ==="
sudo supervisorctl status emailserver
echo ""
echo "=== Nginx Status ==="
sudo systemctl status nginx --no-pager -l
echo ""
echo "=== PostgreSQL Status ==="
sudo systemctl status postgresql --no-pager -l
echo ""
echo "=== Fail2Ban Status ==="
sudo systemctl status fail2ban --no-pager -l
echo ""
echo "=== UFW Status ==="
sudo ufw status
EOF

    # Make scripts executable
    chmod +x *.sh
    
    log "Management scripts created"
}

# Setup SSL certificate (optional)
setup_ssl() {
    read -p "Do you want to setup SSL certificate with Let's Encrypt? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your domain name: " DOMAIN
        if [[ -n "$DOMAIN" ]]; then
            log "Setting up SSL certificate for $DOMAIN..."
            sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN
            log "SSL certificate installed"
        fi
    fi
}

# Main installation function
main() {
    log "Starting Email Server installation on Ubuntu..."
    
    check_root
    check_ubuntu
    
    log "This will install:"
    log "- Python 3 with Flask web framework"
    log "- PostgreSQL database"
    log "- Nginx web server with security configurations"
    log "- UFW firewall protection"
    log "- Fail2Ban intrusion prevention"
    log "- SSL certificate support"
    log "- Process management with Supervisor"
    
    read -p "Continue with installation? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    update_system
    install_system_deps
    setup_postgresql
    setup_python_env
    setup_firewall
    setup_fail2ban
    setup_nginx
    setup_supervisor
    create_systemd_service
    init_database
    create_scripts
    setup_ssl
    
    log "Installation completed successfully!"
    echo
    info "=== IMPORTANT INFORMATION ==="
    info "Database credentials are saved in .env file"
    info "Admin login: username=admin, password=admin123"
    info "Please change the admin password after first login"
    echo
    info "=== NEXT STEPS ==="
    info "1. Edit .env file with your email server settings"
    info "2. Start the server: sudo supervisorctl start emailserver"
    info "3. Check status: ./status_server.sh"
    info "4. Access your server at: http://your-server-ip"
    echo
    info "=== SECURITY NOTES ==="
    info "- Firewall is enabled and configured"
    info "- Fail2Ban is monitoring for attacks"
    info "- SSL certificate can be added with certbot"
    info "- Regular updates are recommended"
    echo
    warning "Remember to:"
    warning "- Change default passwords"
    warning "- Configure your email SMTP settings in .env"
    warning "- Set up domain name and DNS records"
    warning "- Monitor logs regularly"
    
    log "Email server is ready to use!"
}

# Run main function
main "$@"