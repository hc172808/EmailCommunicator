# Overview

This is a complete production-ready email server application built with Flask. It provides a web-based email interface with comprehensive user authentication, email management capabilities, and advanced security features. The application includes both frontend web interfaces and administrative tools, with support for mobile access through a Flutter app. The system is designed for deployment on Ubuntu servers with complete email server functionality including SMTP/IMAP support, security monitoring, and backup management.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework
- **Backend**: Flask web application with SQLAlchemy ORM for database operations
- **Frontend**: Bootstrap-based responsive web interface with Feather icons and custom CSS
- **Authentication**: Flask-Login for session management with custom security middleware
- **Database**: SQLAlchemy with support for both SQLite (development) and PostgreSQL (production)

## Application Structure
- **MVC Pattern**: Separation of models (database), views (templates), and controllers (routes)
- **Modular Design**: Separate modules for email services, security, backup, domain management, and OAuth SSO
- **Security-First Architecture**: Built-in fail2ban-like protection, rate limiting, and intrusion detection
- **Full OpenID Connect / OAuth 2.0 Provider**: Authorization Code + PKCE flows, refresh tokens, JWT ID tokens, token revocation, token introspection, JWKS, discovery document (`oauth.py`)
- **Developer Portal**: Public `/developers` page, self-service app registration (`/developers/apps/register`), admin reviews pending apps before approval
- **Domain-Locked Registration**: All user emails auto-assigned as `username@org_domain`; domain configurable from admin settings
- **Account Approval**: Admin can require approval for new accounts; inactive accounts blocked at login

## Database Models
- **User Management**: Comprehensive user profiles with email server configurations
- **Email Storage**: Full email lifecycle management (drafts, sent, received)
- **Security Logging**: IP bans, security events, and monitoring data
- **Domain Configuration**: Multi-domain support with SSL and DNS management

## Email System
- **SMTP/IMAP Integration**: Support for external email providers (Gmail, custom servers)
- **Email Composition**: Rich text and HTML email support with draft functionality
- **Email Organization**: Inbox, sent, drafts, and custom folder management

## Identity System
- **Email Verification**: Token-based email verification on registration with resend capability
- **Password Reset**: Secure forgot-password / reset-password flow via time-limited tokens
- **Two-Factor Authentication (2FA)**: TOTP-based 2FA using pyotp with QR code setup and 8 one-time backup codes
- **API Tokens**: Long-lived bearer tokens stored in DB for programmatic access; users can create, view, and revoke tokens from their profile
- **API Endpoint `/api/user/me`**: Returns authenticated user profile; supports both JWT and API token auth
- **Login 2FA gate**: After password verification, users with 2FA enabled are redirected to a verification step before session is established

## Security Framework
- **IP Protection**: Automatic IP banning based on failed login attempts
- **Rate Limiting**: Request throttling to prevent abuse
- **Security Monitoring**: Comprehensive logging of security events
- **Session Management**: Secure user session handling with remember-me functionality

## Administrative Features
- **User Management**: Admin dashboard for user oversight and management
- **Security Dashboard**: Real-time security monitoring and ban management
- **Backup System**: Automated backup with external drive support
- **Domain Management**: Multi-domain configuration with SSL certificate handling

# External Dependencies

## Core Framework Dependencies
- **Flask**: Main web framework with SQLAlchemy, Login, and WTF extensions
- **PostgreSQL**: Primary production database (SQLite for development)
- **Bootstrap**: Frontend CSS framework with dark theme support
- **Feather Icons**: Icon library for consistent UI elements

## Email Services
- **SMTP/IMAP Servers**: External email providers (Gmail, custom servers)
- **SSL/TLS**: Secure email communication protocols

## Security and Infrastructure
- **UFW Firewall**: Ubuntu firewall for network security
- **Fail2ban**: Intrusion prevention system (emulated in application)
- **Nginx**: Web server for production deployment
- **SSL Certificates**: Let's Encrypt or custom SSL certificate support

## Development and Deployment
- **Pillow**: Image processing for profile pictures
- **psutil**: System monitoring for backup drive detection
- **Werkzeug**: WSGI utilities and security helpers

## Mobile Integration
- **Flutter Mobile App**: Cross-platform mobile client for email access
- **REST API**: Backend API endpoints for mobile app communication

## System Administration
- **Ubuntu Server**: Target deployment environment
- **Systemd**: Service management for production deployment
- **External Storage**: USB/external drive support for backups