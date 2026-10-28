"""Server-side authorization-code login; provider tokens never leave the request."""
import os
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlsplit

from authlib.integrations.flask_client import OAuth
from authlib.integrations.flask_client.integration import FlaskIntegration
from authlib.integrations.base_client.errors import OAuthError
from joserfc.errors import JoseError
from flask import current_app, g, jsonify, redirect, request, session
from requests.exceptions import RequestException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash

from .accounts import accounts, account_owner_error, current_user, establish_session, protected, rate_limit, valid_email
from .database import OAuthIdentity, OAuthState, User, get_db

LABELS = {'google': 'Google', 'github': 'GitHub'}
FLOW_TTL = 600
NOTICE_COOKIE = 'lexi_oauth_notice'
MESSAGES = {
    'cancelled': 'Sign-in was cancelled. You can try again or use your email and password.',
    'expired': 'This sign-in request expired or changed. Please start again.',
    'unavailable': 'That sign-in service could not be reached. Please try again shortly.',
    'email': 'A verified email is needed. Verify an email with Google or GitHub, then try again.',
    'existing': 'This email already has an account. Sign in the way you used before, then connect this service in your profile.',
    'connected': 'That service is already connected to another account. Your accounts have not been merged.',
    'different': 'Another account from this service is already connected to your LEXI profile.',
}


class IdentityProblem(Exception):
    pass


def browser_binding():
    return hashlib.sha256(session.get('_csrf', '').encode()).hexdigest()


def state_key(provider, state):
    return hashlib.sha256(('_state_'+provider+'_'+state).encode()).hexdigest()


class DatabaseStateCache:
    def get(self, key):
        row = get_db().get(OAuthState, hashlib.sha256(key.encode()).hexdigest())
        return row.data if row and row.expires_at > time.time() else None

    def set(self, key, value, timeout):
        database = get_db()
        database.execute(delete(OAuthState).where(OAuthState.expires_at <= int(time.time())))
        database.add(OAuthState(key=hashlib.sha256(key.encode()).hexdigest(), data=value,
                               expires_at=int(time.time())+min(timeout, FLOW_TTL), **g.oauth_flow))
        database.commit()

    def delete(self, key):
        database = get_db()
        database.execute(delete(OAuthState).where(OAuthState.key == hashlib.sha256(key.encode()).hexdigest()))
        database.commit()


class DatabaseStateIntegration(FlaskIntegration):
    """Keep Authlib state server-side; start must not rewrite an old login cookie."""
    def get_state_data(self, session, state):
        value = self.cache.get('_state_'+self.name+'_'+str(state))
        return json.loads(value).get('data') if value else None

    def set_state_data(self, session, state, data):
        self.cache.set('_state_'+self.name+'_'+state, json.dumps({'data': data}), self.expires_in)

    def clear_state_data(self, session, state):
        self.cache.delete('_state_'+self.name+'_'+str(state))


def init_oauth(app):
    for name in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET'):
        app.config.setdefault(name, os.environ.get(name, ''))
    app.config.setdefault('LEXI_PUBLIC_URL', os.environ.get('LEXI_PUBLIC_URL', ''))
    enabled = [p for p in LABELS if app.config.get(p.upper()+'_CLIENT_ID') and app.config.get(p.upper()+'_CLIENT_SECRET')]
    origin = app.config['LEXI_PUBLIC_URL'].rstrip('/')
    if enabled:
        parts = urlsplit(origin)
        local = parts.hostname in ('localhost', '127.0.0.1', '::1')
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path or not (parts.scheme == 'https' or (parts.scheme == 'http' and local)):
            raise RuntimeError('Set LEXI_PUBLIC_URL to the HTTPS origin of LEXI before enabling Google/GitHub.')
    app.config['LEXI_PUBLIC_URL'] = origin
    if enabled and origin.startswith('https://'):
        app.config['SESSION_COOKIE_SECURE'] = True
    oauth = OAuth(app, cache=DatabaseStateCache())
    oauth.framework_integration_cls = DatabaseStateIntegration
    if 'google' in enabled:
        oauth.register('google', server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                       authorize_params={'prompt': 'select_account'},
                       client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256', 'token_endpoint_auth_method': 'client_secret_post', 'default_timeout': 10})
    if 'github' in enabled:
        oauth.register('github', api_base_url='https://api.github.com/',
                       authorize_url='https://github.com/login/oauth/authorize',
                       access_token_url='https://github.com/login/oauth/access_token',
                       client_kwargs={'scope': 'read:user user:email', 'code_challenge_method': 'S256', 'token_endpoint_auth_method': 'client_secret_post', 'default_timeout': 10},
                       user_agent='LEXI-account-login')
    app.extensions['lexi_oauth'] = oauth
    app.extensions['lexi_oauth_providers'] = enabled


def clear_flows():
    database = get_db()
    database.execute(delete(OAuthState).where(OAuthState.binding == browser_binding()))
    database.commit()


def notice(code, provider=None):
    # A separate short-lived cookie cannot restore a login cookie from an old
    # in-flight link request after another tab signs out or switches accounts.
    serializer = URLSafeTimedSerializer(current_app.secret_key, salt='lexi-oauth-notice')
    response = redirect('/auth/complete' if code in ('linked', 'signed-in') else '/#home', code=303)
    response.set_cookie(NOTICE_COOKIE, serializer.dumps({'code': code, 'provider': provider}), max_age=120,
                        httponly=True, secure=current_app.config['SESSION_COOKIE_SECURE'], samesite='Lax', path='/api/account')
    return response


def read_notice():
    value = request.cookies.get(NOTICE_COOKIE)
    if not value:
        return None
    try:
        data = URLSafeTimedSerializer(current_app.secret_key, salt='lexi-oauth-notice').loads(value, max_age=120)
    except (BadSignature, SignatureExpired):
        return None
    code, provider = data.get('code'), data.get('provider')
    if code in MESSAGES:
        return {'message': MESSAGES[code], 'signin': code == 'existing'}
    if provider in LABELS and code in ('linked', 'signed-in'):
        return {'message': LABELS[provider]+(' connected to your account.' if code == 'linked' else ' sign-in complete.'), 'signin': False, 'sessionChanged': code == 'signed-in'}
    return None


def provider_identity(provider, client, token):
    if provider == 'google':
        # Authlib validates the ID-token signature, issuer, audience, expiry and nonce.
        claims = token.get('userinfo') if token.get('id_token') else None
        if not claims or claims.get('email_verified') is not True:
            raise IdentityProblem('email')
        subject, email = claims.get('sub'), claims.get('email')
        name = claims.get('name', '')
    else:
        profile = client.get('user', token=token, timeout=10)
        profile.raise_for_status()
        profile = profile.json()
        emails = client.get('user/emails', token=token, timeout=10)
        emails.raise_for_status()
        emails = emails.json()
        if not isinstance(profile, dict) or not isinstance(emails, list):
            raise IdentityProblem('email')
        verified = [item for item in emails if isinstance(item, dict) and item.get('verified') is True and valid_email(item.get('email'))]
        verified.sort(key=lambda item: item.get('primary') is not True)
        if not verified or type(profile.get('id')) is not int or profile['id'] <= 0:
            raise IdentityProblem('email')
        subject, email, name = str(profile['id']), verified[0]['email'], profile.get('login', '')
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or not valid_email(email):
        raise IdentityProblem('email')
    return subject, email.strip().casefold(), str(name)


def resolve_identity(provider, subject, email, name, owner, linking):
    database = get_db()
    identity = database.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == provider, OAuthIdentity.subject == subject))
    if identity:
        if linking and identity.user_id != owner.id:
            raise IdentityProblem('connected')
        return database.get(User, identity.user_id)
    if linking:
        if database.scalar(select(OAuthIdentity.id).where(OAuthIdentity.user_id == owner.id, OAuthIdentity.provider == provider)):
            raise IdentityProblem('different')
        user = owner
    else:
        if database.scalar(select(User.id).where(User.email == email)):
            raise IdentityProblem('existing')
        stem = re.sub(r'[^A-Za-z0-9_]', '_', name or email.split('@')[0]).strip('_')[:23]
        if len(stem) < 3:
            stem = 'Lexi_user'
        username = stem
        while database.scalar(select(User.id).where(User.username_key == username.casefold())):
            username = stem+'_'+secrets.token_hex(3)
        # Keep the existing password schema; this random password is discarded.
        user = User(username=username, username_key=username.casefold(), email=email,
                    password_hash=generate_password_hash(secrets.token_urlsafe(64), method='scrypt'))
        database.add(user)
        database.flush()
    database.add(OAuthIdentity(user_id=user.id, provider=provider, subject=subject))
    database.commit()
    return user


@accounts.post('/oauth/<provider>/start')
@protected
def oauth_start(provider):
    if provider not in current_app.extensions['lexi_oauth_providers']:
        return jsonify(error='This sign-in method is not enabled yet.'), 404
    limited = rate_limit('oauth-start', limit=20)
    if limited is not None:
        return limited
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or body.get('intent') not in ('signin', 'link'):
        return jsonify(error='Choose whether to sign in or connect an account.'), 400
    owner = current_user()
    linking = body['intent'] == 'link'
    if linking:
        error = account_owner_error(owner)
        if error is not None:
            return error
    elif owner:
        return jsonify(error='Sign out before signing in to a different account.'), 409
    clear_flows()
    state = secrets.token_urlsafe(32)
    g.oauth_flow = {'binding': browser_binding(), 'owner_id': owner.id if owner else None, 'intent': body['intent']}
    client = current_app.extensions['lexi_oauth'].create_client(provider)
    callback = current_app.config['LEXI_PUBLIC_URL']+'/api/account/oauth/'+provider+'/callback'
    try:
        result = client.authorize_redirect(callback, state=state)
    except (OAuthError, RequestException, ValueError, RuntimeError):
        clear_flows()
        return jsonify(error=MESSAGES['unavailable']), 503
    return jsonify(url=result.location)


@accounts.get('/oauth/<provider>/callback')
def oauth_callback(provider):
    if provider not in current_app.extensions['lexi_oauth_providers']:
        return notice('unavailable')
    state = request.args.get('state', '')
    row = get_db().get(OAuthState, state_key(provider, state)) if len(state) <= 128 else None
    owner = current_user()
    if not row or row.expires_at <= time.time() or not hmac.compare_digest(row.binding, browser_binding()) or row.owner_id != (owner.id if owner else None):
        return notice('expired')
    linking = row.intent == 'link'
    cache = current_app.extensions['lexi_oauth'].cache
    if request.args.get('error'):
        cache.delete('_state_'+provider+'_'+state)
        return notice('cancelled')
    client = current_app.extensions['lexi_oauth'].create_client(provider)
    try:
        token = client.authorize_access_token()
        subject, email, name = provider_identity(provider, client, token)
        user = resolve_identity(provider, subject, email, name, owner, linking)
        if not linking:
            establish_session(user)
        return notice('linked' if linking else 'signed-in', provider)
    except IdentityProblem as problem:
        get_db().rollback()
        return notice(str(problem))
    except IntegrityError:
        get_db().rollback()
        return notice('existing')
    except (OAuthError, JoseError, RequestException, ValueError, KeyError, TypeError, RuntimeError, SQLAlchemyError):
        get_db().rollback()
        current_app.logger.warning('OAuth sign-in failed for %s; no account was connected.', provider)
        return notice('unavailable')
    finally:
        try:
            cache.delete('_state_'+provider+'_'+state)
        except SQLAlchemyError:
            get_db().rollback()
