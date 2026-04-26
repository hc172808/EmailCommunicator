"""
OAuth 2.0 Authorization Code flow provider.
Allows external websites to use this server for user authentication (SSO).

Endpoints:
  GET  /oauth/authorize          – show the authorization consent page
  POST /oauth/authorize          – user approves or denies
  POST /oauth/token              – exchange code for access token
  GET  /oauth/userinfo           – return user profile (bearer token required)
  GET  /oauth/widget.js          – embeddable JS snippet for external sites
  GET  /oauth/.well-known/openid-configuration  – discovery document
"""

from flask import request, redirect, url_for, render_template, jsonify, session, current_app
from flask_login import current_user, login_required
from app import app, db
from models import OAuthApp, OAuthAuthorizationCode, OAuthAccessToken, User
from datetime import datetime, timedelta
import logging


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_base_url():
    return request.host_url.rstrip('/')


def _bearer_user():
    """Return the User for a valid Bearer token in the Authorization header, or None."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    raw = auth[7:].strip()
    record = OAuthAccessToken.query.filter_by(token=raw).first()
    if not record or not record.is_valid():
        return None
    return record.user


# ── Authorization endpoint ────────────────────────────────────────────────────

@app.route('/oauth/authorize', methods=['GET', 'POST'])
def oauth_authorize():
    client_id    = request.values.get('client_id', '')
    redirect_uri = request.values.get('redirect_uri', '')
    state        = request.values.get('state', '')
    scope        = request.values.get('scope', 'profile')
    response_type = request.values.get('response_type', 'code')

    # Validate client
    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
    if not app_record:
        return render_template('oauth/error.html',
                               error='Unknown or inactive application.',
                               description='The client_id is not recognized.'), 400
    if not app_record.allowed_redirect(redirect_uri):
        return render_template('oauth/error.html',
                               error='Redirect URI mismatch.',
                               description='The redirect_uri is not registered for this application.'), 400
    if response_type != 'code':
        return render_template('oauth/error.html',
                               error='Unsupported response type.',
                               description='Only response_type=code is supported.'), 400

    # Must be logged in
    if not current_user.is_authenticated:
        session['oauth_next'] = request.url
        return redirect(url_for('login'))

    if request.method == 'POST':
        if request.form.get('action') == 'deny':
            sep = '&' if '?' in redirect_uri else '?'
            url = f"{redirect_uri}{sep}error=access_denied"
            if state:
                url += f"&state={state}"
            return redirect(url)

        # Approve — issue an authorization code (valid 5 minutes)
        code = OAuthAuthorizationCode(
            app_id=app_record.id,
            user_id=current_user.id,
            redirect_uri=redirect_uri,
            scope=scope,
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        db.session.add(code)
        db.session.commit()

        sep = '&' if '?' in redirect_uri else '?'
        url = f"{redirect_uri}{sep}code={code.code}"
        if state:
            url += f"&state={state}"
        return redirect(url)

    return render_template('oauth/authorize.html',
                           oauth_app=app_record,
                           redirect_uri=redirect_uri,
                           state=state,
                           scope=scope)


# ── Token endpoint ────────────────────────────────────────────────────────────

@app.route('/oauth/token', methods=['POST'])
def oauth_token():
    grant_type    = request.form.get('grant_type', '')
    code_val      = request.form.get('code', '')
    redirect_uri  = request.form.get('redirect_uri', '')
    client_id     = request.form.get('client_id', '')
    client_secret = request.form.get('client_secret', '')

    if grant_type != 'authorization_code':
        return jsonify({'error': 'unsupported_grant_type'}), 400

    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
    if not app_record or app_record.client_secret != client_secret:
        return jsonify({'error': 'invalid_client'}), 401

    code = OAuthAuthorizationCode.query.filter_by(code=code_val).first()
    if not code or not code.is_valid() or code.app_id != app_record.id:
        return jsonify({'error': 'invalid_grant'}), 400
    if code.redirect_uri != redirect_uri:
        return jsonify({'error': 'redirect_uri_mismatch'}), 400

    # Mark code used and issue token (valid 1 hour)
    code.used = True
    token = OAuthAccessToken(
        app_id=app_record.id,
        user_id=code.user_id,
        scope=code.scope,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db.session.add(token)
    db.session.commit()

    return jsonify({
        'access_token': token.token,
        'token_type': 'Bearer',
        'expires_in': 3600,
        'scope': token.scope
    })


# ── UserInfo endpoint ─────────────────────────────────────────────────────────

@app.route('/oauth/userinfo')
def oauth_userinfo():
    user = _bearer_user()
    if not user:
        return jsonify({'error': 'invalid_token'}), 401
    return jsonify({
        'sub': str(user.id),
        'name': user.full_name,
        'username': user.username,
        'email': user.email,
        'email_verified': user.is_verified,
        'picture': (request.host_url.rstrip('/') +
                    url_for('static', filename='profile_pics/' + user.profile_photo)
                    if user.profile_photo else None),
        'is_admin': user.is_admin,
    })


# ── Discovery document ────────────────────────────────────────────────────────

@app.route('/oauth/.well-known/openid-configuration')
def oauth_discovery():
    base = _get_base_url()
    return jsonify({
        'issuer': base,
        'authorization_endpoint': f'{base}/oauth/authorize',
        'token_endpoint': f'{base}/oauth/token',
        'userinfo_endpoint': f'{base}/oauth/userinfo',
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code'],
        'scopes_supported': ['profile'],
        'token_endpoint_auth_methods_supported': ['client_secret_post'],
    })


# ── Embeddable widget script ──────────────────────────────────────────────────

@app.route('/oauth/widget.js')
def oauth_widget():
    client_id = request.args.get('client_id', '')
    redirect_uri = request.args.get('redirect_uri', '')
    state = request.args.get('state', '')
    label = request.args.get('label', 'Sign in')
    base = _get_base_url()

    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
    app_name = app_record.name if app_record else 'Identity Server'

    auth_url = (f"{base}/oauth/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri={redirect_uri}"
                f"&response_type=code"
                f"&scope=profile"
                + (f"&state={state}" if state else ''))

    js = f"""
(function() {{
  var btn = document.getElementById('sso-login-btn');
  if (!btn) return;
  var a = document.createElement('a');
  a.href = '{auth_url}';
  a.style.cssText = 'display:inline-flex;align-items:center;gap:8px;padding:10px 20px;background:#0d6efd;color:#fff;border-radius:6px;text-decoration:none;font-family:sans-serif;font-size:15px;font-weight:600;border:none;cursor:pointer;';
  a.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> {label} with {app_name}';
  btn.appendChild(a);
}})();
"""
    from flask import Response
    return Response(js, mimetype='application/javascript')
