# Email Server - Production Ready Installation

A complete email server with web interface, user authentication, and advanced security features including fail2ban protection and firewall configuration.

## Features

- 🔐 **User Authentication** - Complete login/registration system with profile management
- 📧 **Email Management** - Send, receive, and organize emails with SMTP/IMAP support
- 🛡️ **Advanced Security** - Fail2ban protection, rate limiting, and intrusion detection
- 👨‍💼 **Admin Dashboard** - User management and security monitoring
- 🔥 **Firewall Protection** - UFW firewall with custom rules
- 🚀 **Production Ready** - Nginx, PostgreSQL, SSL support

## Quick Installation on Ubuntu

### Prerequisites
- Ubuntu 20.04 or newer
- User with sudo privileges
- At least 2GB RAM and 10GB disk space

### One-Command Installation

```bash
# Download and run the installation script
curl -O https://raw.githubusercontent.com/yourusername/email-server/main/install_ubuntu.sh
chmod +x install_ubuntu.sh
./install_ubuntu.sh
```

### Manual Installation Steps

1. **Make the script executable:**
   ```bash
   chmod +x install_ubuntu.sh
   ```

2. **Run the installation:**
   ```bash
   ./install_ubuntu.sh
   ```

3. **Follow the prompts** - The script will:
   - Update your system
   - Install all dependencies
   - Configure PostgreSQL database
   - Set up security features (UFW, Fail2Ban)
   - Configure Nginx web server
   - Create systemd services
   - Initialize the database

## Post-Installation Configuration

### 1. Configure Email Settings

Edit the `.env` file with your SMTP credentials:

```bash
nano .env
```

Update these variables:
```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
```

### 2. Start the Server

```bash
# Using Supervisor (recommended)
sudo supervisorctl start emailserver

# Or using systemd
sudo systemctl start emailserver
```

### 3. Check Status

```bash
./status_server.sh
```

## Default Login Credentials

- **Username:** admin
- **Password:** admin123

⚠️ **Important:** Change the password immediately after first login!

## Server Management

### Start/Stop/Restart Server

```bash
# Start
sudo supervisorctl start emailserver

# Stop
sudo supervisorctl stop emailserver

# Restart
sudo supervisorctl restart emailserver
```

### View Logs

```bash
# Application logs
tail -f /var/log/emailserver/app.log

# Error logs
tail -f /var/log/emailserver/error.log

# Security logs
tail -f /var/log/emailserver/security.log

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Security Monitoring

```bash
# Check banned IPs
sudo fail2ban-client status emailserver-login

# View firewall status
sudo ufw status

# Monitor failed login attempts
grep "failed_login" /var/log/emailserver/security.log
```

## Security Features

### Automatic Protection
- **Fail2Ban:** Automatically bans IPs after 5 failed login attempts
- **Rate Limiting:** 100 requests per hour per IP
- **Firewall:** UFW configured with minimal required ports
- **SSL Support:** Let's Encrypt integration available

### Manual IP Management
Access the admin dashboard → Security section to:
- View active bans
- Manually ban/unban IP addresses
- Monitor security events
- View security statistics

## Firewall Configuration

Default open ports:
- **22** - SSH
- **80** - HTTP
- **443** - HTTPS
- **25** - SMTP
- **587** - SMTP with STARTTLS
- **993** - IMAPS
- **995** - POP3S

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   ```bash
   sudo systemctl status postgresql
   sudo systemctl restart postgresql
   ```

2. **Permission Issues**
   ```bash
   sudo chown -R $USER:$USER /var/log/emailserver
   ```

3. **Nginx Configuration Error**
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```

4. **Service Not Starting**
   ```bash
   sudo supervisorctl status
   sudo systemctl status emailserver
   ```

### Log Locations

- Application: `/var/log/emailserver/app.log`
- Errors: `/var/log/emailserver/error.log`
- Security: `/var/log/emailserver/security.log`
- Nginx: `/var/log/nginx/`
- Fail2Ban: `/var/log/fail2ban.log`

## SSL Certificate Setup

For production use with a domain name:

```bash
# Install SSL certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal is configured automatically
sudo certbot renew --dry-run
```

## Backup and Maintenance

### Database Backup

```bash
# Create backup
pg_dump emailserver > backup_$(date +%Y%m%d).sql

# Restore backup
psql emailserver < backup_20240101.sql
```

### System Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Restart services after updates
sudo supervisorctl restart emailserver
sudo systemctl restart nginx
```

## Performance Optimization

### For High Traffic

1. **Increase Gunicorn Workers**
   ```bash
   sudo nano /etc/supervisor/conf.d/emailserver.conf
   # Change --workers 3 to --workers 8
   sudo supervisorctl restart emailserver
   ```

2. **Optimize PostgreSQL**
   ```bash
   sudo nano /etc/postgresql/*/main/postgresql.conf
   # Increase shared_buffers, effective_cache_size
   sudo systemctl restart postgresql
   ```

3. **Enable Nginx Caching**
   ```bash
   sudo nano /etc/nginx/sites-available/emailserver
   # Add caching directives
   sudo systemctl restart nginx
   ```

## Support

For issues and questions:
1. Check the logs first
2. Review the troubleshooting section
3. Ensure all services are running
4. Verify firewall and security settings

## License

This project is licensed under the MIT License.