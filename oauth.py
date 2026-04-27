"""
Full OpenID Connect / OAuth 2.0 provider.

Endpoints
─────────────────────────────────────────────────
GET/POST /oauth/authorize          – consent screen (PKCE-aware)
POST     /oauth/token              – code↔token exchange (+ refresh)
GET      /oauth/userinfo           – profile info (Bearer token)
POST     /oauth/revoke             – revoke access or refresh token
POST     /oauth/introspect         – validate a token (RFC 7662)
GET      /oauth/.well-known/openid-configuration  – discovery
GET      /oauth/.well-known/jwks.json             – JWKS
GET      /oauth/widget.js          – embeddable "Sign in" button
"""

from flask import request, redirect, url_for, render_template, jsonify, session, current_app, Response
from flask_login import current_user
from app import app, db, csrf
from models import OAuthApp, OAuthAuthorizationCode, OAuthAccessToken, OAuthRefreshToken, User
from datetime import datetime, timedelta
import logging
import hashlib
import base64
import time
import jwt as pyjwt
import secrets


# ── helpers ────────────────────────────────────────────────────────────────────

def _base():
    return request.host_url.rstrip('/')


def _bearer_user():
    """Return the User for a valid Bearer token in the Authorization header."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    raw = auth[7:].strip()
    rec = OAuthAccessToken.query.filter_by(token=raw).first()
    if not rec or not rec.is_valid():
        return None
    return rec.user


def _make_id_token(user, app_record, nonce=None):
    """Create a signed JWT ID token (HS256)."""
    now = int(time.time())
    payload = {
        'iss': _base(),
        'sub': str(user.id),
        'aud': app_record.client_id,
        'exp': now + 3600,
        'iat': now,
        'name': user.full_name,
        'preferred_username': user.username,
        'email': user.email,
        'email_verified': bool(user.is_verified),
        'picture': (
            _base() + url_for('static', filename='profile_pics/' + user.profile_photo)
            if user.profile_photo else None
        ),
    }
    if nonce:
        payload['nonce'] = nonce
    return pyjwt.encode(payload, current_app.secret_key, algorithm='HS256')


def _verify_pkce(code_record, code_verifier):
    """Return True if code_verifier satisfies the stored code_challenge."""
    if not code_record.code_challenge:
        return True  # no PKCE was used
    method = (code_record.code_challenge_method or 'plain').upper()
    if method == 'S256':
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    else:
        challenge = code_verifier
    return secrets.compare_digest(challenge, code_record.code_challenge)


def _issue_tokens(app_record, user, scope):
    """Create and persist a new access token + refresh token pair."""
    access = OAuthAccessToken(
        app_id=app_record.id,
        user_id=user.id,
        scope=scope,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    refresh = OAuthRefreshToken(
        app_id=app_record.id,
        user_id=user.id,
        scope=scope,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.session.add_all([access, refresh])
    db.session.commit()
    return access, refresh


# ── Authorization endpoint ─────────────────────────────────────────────────────

@app.route('/oauth/authorize', methods=['GET', 'POST'])
def oauth_authorize():
    client_id     = request.values.get('client_id', '')
    redirect_uri  = request.values.get('redirect_uri', '')
    state         = request.values.get('state', '')
    scope         = request.values.get('scope', 'openid profile email')
    response_type = request.values.get('response_type', 'code')
    nonce         = request.values.get('nonce', '')
    code_challenge        = request.values.get('code_challenge', '')
    code_challenge_method = request.values.get('code_challenge_method', 'plain')

    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True, is_pending=False).first()
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

        code = OAuthAuthorizationCode(
            app_id=app_record.id,
            user_id=current_user.id,
            redirect_uri=redirect_uri,
            scope=scope,
            nonce=nonce or None,
            code_challenge=code_challenge or None,
            code_challenge_method=code_challenge_method if code_challenge else None,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.session.add(code)
        db.session.commit()

        sep = '&' if '?' in redirect_uri else '?'
        url = f"{redirect_uri}{sep}code={code.code}"
        if state:
            url += f"&state={state}"
        return redirect(url)

    # Build scope list for display
    scope_descriptions = {
        'openid': ('log-in', 'Verify your identity'),
        'profile': ('user', 'Read your name, username and profile picture'),
        'email': ('mail', 'Read your email address'),
        'phone': ('phone', 'Read your phone number'),
    }
    requested_scopes = [s.strip() for s in scope.split() if s.strip()]
    scope_items = [(scope_descriptions.get(s, ('info', s))) for s in requested_scopes]

    return render_template('oauth/authorize.html',
                           oauth_app=app_record,
                           redirect_uri=redirect_uri,
                           state=state,
                           scope=scope,
                           nonce=nonce,
                           code_challenge=code_challenge,
                           code_challenge_method=code_challenge_method,
                           scope_items=scope_items)


# ── Token endpoint ─────────────────────────────────────────────────────────────

@app.route('/oauth/token', methods=['POST'])
@csrf.exempt
def oauth_token():
    grant_type = request.form.get('grant_type', '')

    # ── authorization_code grant ──
    if grant_type == 'authorization_code':
        code_val      = request.form.get('code', '')
        redirect_uri  = request.form.get('redirect_uri', '')
        client_id     = request.form.get('client_id', '')
        client_secret = request.form.get('client_secret', '')
        code_verifier = request.form.get('code_verifier', '')

        code = OAuthAuthorizationCode.query.filter_by(code=code_val).first()
        if not code or not code.is_valid():
            return jsonify({'error': 'invalid_grant', 'error_description': 'Code is invalid or expired.'}), 400
        if code.redirect_uri != redirect_uri:
            return jsonify({'error': 'redirect_uri_mismatch'}), 400

        app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
        if not app_record or app_record.id != code.app_id:
            return jsonify({'error': 'invalid_client'}), 401

        # PKCE public client: skip secret check, verify code_verifier instead
        if code.code_challenge:
            if not code_verifier:
                return jsonify({'error': 'invalid_grant', 'error_description': 'code_verifier is required.'}), 400
            if not _verify_pkce(code, code_verifier):
                return jsonify({'error': 'invalid_grant', 'error_description': 'PKCE verification failed.'}), 400
        else:
            # Confidential client — require client_secret
            if not client_secret or app_record.client_secret != client_secret:
                return jsonify({'error': 'invalid_client'}), 401

        code.used = True
        access, refresh = _issue_tokens(app_record, code.user, code.scope)

        resp = {
            'access_token': access.token,
            'token_type': 'Bearer',
            'expires_in': 3600,
            'refresh_token': refresh.token,
            'scope': access.scope,
        }
        if 'openid' in (code.scope or ''):
            resp['id_token'] = _make_id_token(code.user, app_record, nonce=code.nonce)
        return jsonify(resp)

    # ── refresh_token grant ──
    elif grant_type == 'refresh_token':
        refresh_val   = request.form.get('refresh_token', '')
        client_id     = request.form.get('client_id', '')
        client_secret = request.form.get('client_secret', '')

        refresh = OAuthRefreshToken.query.filter_by(token=refresh_val).first()
        if not refresh or not refresh.is_valid():
            return jsonify({'error': 'invalid_grant', 'error_description': 'Refresh token is invalid or expired.'}), 400

        app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
        if not app_record or app_record.id != refresh.app_id:
            return jsonify({'error': 'invalid_client'}), 401
        if app_record.client_secret != client_secret:
            return jsonify({'error': 'invalid_client'}), 401

        # Rotate: revoke old refresh token, issue new pair
        refresh.revoked = True
        new_access, new_refresh = _issue_tokens(app_record, refresh.user, refresh.scope)

        resp = {
            'access_token': new_access.token,
            'token_type': 'Bearer',
            'expires_in': 3600,
            'refresh_token': new_refresh.token,
            'scope': new_access.scope,
        }
        if 'openid' in (refresh.scope or ''):
            resp['id_token'] = _make_id_token(refresh.user, app_record)
        return jsonify(resp)

    return jsonify({'error': 'unsupported_grant_type'}), 400


# ── UserInfo endpoint ──────────────────────────────────────────────────────────

@app.route('/oauth/userinfo')
@csrf.exempt
def oauth_userinfo():
    user = _bearer_user()
    if not user:
        return jsonify({'error': 'invalid_token'}), 401

    # Get the token record to check scope
    auth = request.headers.get('Authorization', '')[7:].strip()
    token_rec = OAuthAccessToken.query.filter_by(token=auth).first()
    scope = token_rec.scope if token_rec else ''

    data = {'sub': str(user.id)}
    if 'profile' in scope or 'openid' in scope:
        data.update({
            'name': user.full_name,
            'preferred_username': user.username,
            'picture': (
                _base() + url_for('static', filename='profile_pics/' + user.profile_photo)
                if user.profile_photo else None
            ),
            'locale': user.location or None,
        })
    if 'email' in scope:
        data.update({'email': user.email, 'email_verified': bool(user.is_verified)})
    if 'phone' in scope and user.phone_number:
        data['phone_number'] = user.phone_number

    return jsonify(data)


# ── Token revocation (RFC 7009) ────────────────────────────────────────────────

@app.route('/oauth/revoke', methods=['POST'])
@csrf.exempt
def oauth_revoke():
    token_val = request.form.get('token', '')
    hint      = request.form.get('token_type_hint', '')

    # Try access token first
    at = OAuthAccessToken.query.filter_by(token=token_val).first()
    if at:
        at.expires_at = datetime.utcnow()  # expire immediately
        db.session.commit()
        return ('', 200)

    # Try refresh token
    rt = OAuthRefreshToken.query.filter_by(token=token_val).first()
    if rt:
        rt.revoked = True
        db.session.commit()
        return ('', 200)

    return ('', 200)  # RFC 7009: always return 200


# ── Token introspection (RFC 7662) ────────────────────────────────────────────

@app.route('/oauth/introspect', methods=['POST'])
@csrf.exempt
def oauth_introspect():
    client_id     = request.form.get('client_id', '')
    client_secret = request.form.get('client_secret', '')
    token_val     = request.form.get('token', '')

    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
    if not app_record or app_record.client_secret != client_secret:
        return jsonify({'error': 'invalid_client'}), 401

    at = OAuthAccessToken.query.filter_by(token=token_val).first()
    if at and at.is_valid():
        u = at.user
        return jsonify({
            'active': True,
            'sub': str(u.id),
            'username': u.username,
            'email': u.email,
            'scope': at.scope,
            'client_id': app_record.client_id,
            'exp': int(at.expires_at.timestamp()),
            'iat': int(at.created_at.timestamp()),
            'token_type': 'Bearer',
        })

    return jsonify({'active': False})


# ── JWKS endpoint ──────────────────────────────────────────────────────────────

@app.route('/oauth/.well-known/jwks.json')
@csrf.exempt
def oauth_jwks():
    # HS256 is symmetric — no public key to publish.
    # Return an empty JWKS to satisfy OIDC clients that check the endpoint.
    return jsonify({'keys': []})


# ── Discovery document ─────────────────────────────────────────────────────────

@app.route('/oauth/.well-known/openid-configuration')
@csrf.exempt
def oauth_discovery():
    base = _base()
    return jsonify({
        'issuer': base,
        'authorization_endpoint': f'{base}/oauth/authorize',
        'token_endpoint': f'{base}/oauth/token',
        'userinfo_endpoint': f'{base}/oauth/userinfo',
        'revocation_endpoint': f'{base}/oauth/revoke',
        'introspection_endpoint': f'{base}/oauth/introspect',
        'jwks_uri': f'{base}/oauth/.well-known/jwks.json',
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'subject_types_supported': ['public'],
        'id_token_signing_alg_values_supported': ['HS256'],
        'scopes_supported': ['openid', 'profile', 'email', 'phone'],
        'token_endpoint_auth_methods_supported': ['client_secret_post', 'none'],
        'claims_supported': [
            'sub', 'iss', 'aud', 'exp', 'iat',
            'name', 'preferred_username', 'email', 'email_verified',
            'picture', 'phone_number', 'locale',
        ],
        'code_challenge_methods_supported': ['S256', 'plain'],
    })


# ── Embeddable "Sign in" widget ────────────────────────────────────────────────

@app.route('/oauth/widget.js')
@csrf.exempt
def oauth_widget():
    client_id    = request.args.get('client_id', '')
    redirect_uri = request.args.get('redirect_uri', '')
    state        = request.args.get('state', '')
    scope        = request.args.get('scope', 'openid profile email')
    label        = request.args.get('label', 'Sign in')
    theme        = request.args.get('theme', 'auto')   # auto | light | dark
    popup        = request.args.get('popup', 'false')  # true | false
    base         = _base()

    app_record = OAuthApp.query.filter_by(client_id=client_id, is_active=True).first()
    app_name   = app_record.name if app_record else 'Netlifegy'

    auth_url = (
        f"{base}/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        + (f"&state={state}" if state else '')
    )

    js = f"""
(function() {{
  "use strict";
  var _nlg = {{
    base: '{base}',
    authUrl: '{auth_url}',
    label: '{label}',
    appName: '{app_name}',
    theme: '{theme}',
    popup: {popup.lower()},
  }};

  function _css(theme) {{
    var isDark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    return isDark
      ? 'background:#1a1d27;color:#e8e8f0;border:1.5px solid #444;'
      : 'background:#ffffff;color:#1f1f1f;border:1.5px solid #dadce0;';
  }}

  function _render(container) {{
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', _nlg.label + ' with ' + _nlg.appName);
    btn.style.cssText = [
      'display:inline-flex;align-items:center;gap:10px;',
      'padding:10px 20px 10px 14px;border-radius:8px;',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;',
      'font-size:15px;font-weight:600;cursor:pointer;',
      'transition:box-shadow .15s,transform .1s;white-space:nowrap;',
      _css(_nlg.theme),
    ].join('');

    // Shield icon
    btn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2.2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
      <span>` + _nlg.label + ' with <strong>' + _nlg.appName + '</strong></span>';

    btn.addEventListener('mouseover', function() {{
      this.style.boxShadow = '0 2px 8px rgba(0,0,0,.2)';
      this.style.transform = 'translateY(-1px)';
    }});
    btn.addEventListener('mouseout', function() {{
      this.style.boxShadow = 'none';
      this.style.transform = '';
    }});
    btn.addEventListener('click', function() {{
      if (_nlg.popup) {{
        var w = 480, h = 640;
        var left = (screen.width - w) / 2, top = (screen.height - h) / 2;
        var pw = window.open(_nlg.authUrl, 'nlg_sso',
          'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top +
          ',toolbar=no,menubar=no,scrollbars=yes,resizable=yes');
        window._nlgPopup = pw;
      }} else {{
        window.location.href = _nlg.authUrl;
      }}
    }});
    container.appendChild(btn);
  }}

  // Auto-render into any element with data-nlg-login attribute
  document.addEventListener('DOMContentLoaded', function() {{
    var containers = document.querySelectorAll('[data-nlg-login], #sso-login-btn');
    if (containers.length === 0) {{
      // fallback: render into body as floating button (dev helper)
      console.info('[Netlifegy SSO] No target element found. Add data-nlg-login to your container.');
      return;
    }}
    containers.forEach(function(el) {{ _render(el); }});
  }});
}})();
"""
    return Response(js, mimetype='application/javascript',
                    headers={'Cache-Control': 'public, max-age=3600'})
