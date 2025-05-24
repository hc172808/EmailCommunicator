"""
Domain Configuration Manager
Handles domain settings, DNS configuration, and SSL certificates
"""

import os
import json
import subprocess
import logging
from datetime import datetime
from app import db
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

class DomainConfig(db.Model):
    """Model for storing domain configuration"""
    __tablename__ = 'domain_config'
    
    id = Column(Integer, primary_key=True)
    domain_name = Column(String(255), unique=True, nullable=False)
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)
    
    # SSL Configuration
    ssl_enabled = Column(Boolean, default=False)
    ssl_cert_path = Column(String(500))
    ssl_key_path = Column(String(500))
    ssl_expires_at = Column(DateTime)
    auto_ssl = Column(Boolean, default=True)  # Let's Encrypt auto-renewal
    
    # Email Configuration
    mail_server_enabled = Column(Boolean, default=True)
    webmail_enabled = Column(Boolean, default=True)
    
    # DNS Settings
    dns_configured = Column(Boolean, default=False)
    mx_record = Column(String(255))
    a_record = Column(String(255))
    txt_record = Column(Text)  # SPF, DKIM records
    
    # API Settings for mobile
    api_enabled = Column(Boolean, default=True)
    api_key = Column(String(255))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<DomainConfig {self.domain_name}>'
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'domain_name': self.domain_name,
            'is_primary': self.is_primary,
            'is_active': self.is_active,
            'ssl_enabled': self.ssl_enabled,
            'ssl_expires_at': self.ssl_expires_at.isoformat() if self.ssl_expires_at else None,
            'mail_server_enabled': self.mail_server_enabled,
            'webmail_enabled': self.webmail_enabled,
            'dns_configured': self.dns_configured,
            'api_enabled': self.api_enabled,
            'created_at': self.created_at.isoformat()
        }

class DomainManager:
    """Manager for domain configuration operations"""
    
    def __init__(self):
        self.config_file = 'domain_config.json'
        self.nginx_config_path = '/etc/nginx/sites-available'
        self.ssl_path = '/etc/letsencrypt/live'
        
    def add_domain(self, domain_name, is_primary=False):
        """Add a new domain configuration"""
        try:
            # Check if domain already exists
            existing = DomainConfig.query.filter_by(domain_name=domain_name).first()
            if existing:
                return False, "Domain already exists"
            
            # If this is set as primary, unset other primary domains
            if is_primary:
                DomainConfig.query.filter_by(is_primary=True).update({'is_primary': False})
            
            # Create new domain config
            domain = DomainConfig(
                domain_name=domain_name,
                is_primary=is_primary,
                api_key=self._generate_api_key()
            )
            
            db.session.add(domain)
            db.session.commit()
            
            # Generate DNS instructions
            dns_instructions = self._generate_dns_instructions(domain)
            
            return True, {
                'domain': domain.to_dict(),
                'dns_instructions': dns_instructions
            }
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error adding domain: {str(e)}")
            return False, str(e)
    
    def configure_ssl(self, domain_name, auto_ssl=True):
        """Configure SSL for domain"""
        try:
            domain = DomainConfig.query.filter_by(domain_name=domain_name).first()
            if not domain:
                return False, "Domain not found"
            
            if auto_ssl:
                # Use Let's Encrypt
                success, message = self._setup_letsencrypt(domain_name)
                if success:
                    domain.ssl_enabled = True
                    domain.auto_ssl = True
                    domain.ssl_cert_path = f"{self.ssl_path}/{domain_name}/fullchain.pem"
                    domain.ssl_key_path = f"{self.ssl_path}/{domain_name}/privkey.pem"
                    db.session.commit()
                return success, message
            else:
                # Manual SSL configuration
                domain.ssl_enabled = False
                domain.auto_ssl = False
                db.session.commit()
                return True, "SSL disabled for manual configuration"
                
        except Exception as e:
            logging.error(f"SSL configuration error: {str(e)}")
            return False, str(e)
    
    def configure_nginx(self, domain_name):
        """Generate and configure Nginx for the domain"""
        try:
            domain = DomainConfig.query.filter_by(domain_name=domain_name).first()
            if not domain:
                return False, "Domain not found"
            
            # Generate Nginx configuration
            nginx_config = self._generate_nginx_config(domain)
            
            # Write configuration file
            config_file = f"{self.nginx_config_path}/{domain_name}"
            with open(config_file, 'w') as f:
                f.write(nginx_config)
            
            # Enable site
            symlink_path = f"/etc/nginx/sites-enabled/{domain_name}"
            if not os.path.exists(symlink_path):
                os.symlink(config_file, symlink_path)
            
            # Test and reload Nginx
            test_result = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
            if test_result.returncode == 0:
                subprocess.run(['systemctl', 'reload', 'nginx'])
                return True, "Nginx configured successfully"
            else:
                return False, f"Nginx configuration error: {test_result.stderr}"
                
        except Exception as e:
            logging.error(f"Nginx configuration error: {str(e)}")
            return False, str(e)
    
    def _generate_api_key(self):
        """Generate API key for mobile app access"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _generate_dns_instructions(self, domain):
        """Generate DNS configuration instructions"""
        server_ip = self._get_server_ip()
        
        return {
            'a_record': {
                'type': 'A',
                'name': '@',
                'value': server_ip,
                'ttl': 3600
            },
            'www_record': {
                'type': 'A', 
                'name': 'www',
                'value': server_ip,
                'ttl': 3600
            },
            'mx_record': {
                'type': 'MX',
                'name': '@',
                'value': f"10 mail.{domain.domain_name}",
                'ttl': 3600
            },
            'mail_a_record': {
                'type': 'A',
                'name': 'mail',
                'value': server_ip,
                'ttl': 3600
            },
            'spf_record': {
                'type': 'TXT',
                'name': '@',
                'value': f'"v=spf1 a mx ip4:{server_ip} ~all"',
                'ttl': 3600
            }
        }
    
    def _get_server_ip(self):
        """Get server's public IP address"""
        try:
            # Try to get public IP
            result = subprocess.run(['curl', '-s', 'ifconfig.me'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        # Fallback to local IP
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split()[0]
        except:
            pass
        
        return '127.0.0.1'
    
    def _setup_letsencrypt(self, domain_name):
        """Setup Let's Encrypt SSL certificate"""
        try:
            # Install certbot if not present
            subprocess.run(['apt', 'update'], check=True)
            subprocess.run(['apt', 'install', '-y', 'certbot', 'python3-certbot-nginx'], check=True)
            
            # Get certificate
            cmd = [
                'certbot', '--nginx',
                '-d', domain_name,
                '-d', f'www.{domain_name}',
                '--non-interactive',
                '--agree-tos',
                '--email', f'admin@{domain_name}',
                '--redirect'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True, "SSL certificate installed successfully"
            else:
                return False, f"Certbot error: {result.stderr}"
                
        except Exception as e:
            return False, f"SSL setup error: {str(e)}"
    
    def _generate_nginx_config(self, domain):
        """Generate Nginx configuration for domain"""
        ssl_config = ""
        if domain.ssl_enabled:
            ssl_config = f"""
    listen 443 ssl http2;
    ssl_certificate {domain.ssl_cert_path};
    ssl_certificate_key {domain.ssl_key_path};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
"""
        
        return f"""
server {{
    listen 80;
    server_name {domain.domain_name} www.{domain.domain_name};
    {ssl_config}
    
    root /var/www/html;
    index index.html index.htm;
    
    # Email server proxy
    location / {{
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    # API endpoints for mobile app
    location /api/ {{
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers for mobile app
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS, PUT, DELETE';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
    }}
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
}}

# Redirect non-www to www (optional)
server {{
    listen 80;
    server_name www.{domain.domain_name};
    return 301 $scheme://{domain.domain_name}$request_uri;
}}
"""
    
    def get_domain_status(self, domain_name):
        """Get comprehensive domain status"""
        domain = DomainConfig.query.filter_by(domain_name=domain_name).first()
        if not domain:
            return None
        
        status = domain.to_dict()
        
        # Check SSL certificate status
        if domain.ssl_enabled and domain.ssl_cert_path:
            ssl_status = self._check_ssl_status(domain.ssl_cert_path)
            status.update(ssl_status)
        
        # Check DNS status
        dns_status = self._check_dns_status(domain_name)
        status['dns_status'] = dns_status
        
        return status
    
    def _check_ssl_status(self, cert_path):
        """Check SSL certificate status"""
        try:
            if os.path.exists(cert_path):
                # Check certificate expiration
                cmd = ['openssl', 'x509', '-in', cert_path, '-noout', '-enddate']
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    date_str = result.stdout.split('=')[1].strip()
                    return {
                        'ssl_valid': True,
                        'ssl_expires': date_str
                    }
            
            return {'ssl_valid': False, 'ssl_error': 'Certificate not found'}
            
        except Exception as e:
            return {'ssl_valid': False, 'ssl_error': str(e)}
    
    def _check_dns_status(self, domain_name):
        """Check DNS configuration status"""
        try:
            # Check A record
            cmd = ['dig', '+short', domain_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                return {
                    'dns_resolves': True,
                    'resolved_ip': result.stdout.strip()
                }
            else:
                return {
                    'dns_resolves': False,
                    'error': 'Domain does not resolve'
                }
                
        except Exception as e:
            return {
                'dns_resolves': False,
                'error': str(e)
            }

# Global domain manager instance
domain_manager = DomainManager()