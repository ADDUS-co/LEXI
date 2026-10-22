"""Account API. Credentials never enter localStorage or the vocabulary files."""
from functools import wraps
from io import BytesIO
import hashlib
import re
import secrets
import time
import warnings

from flask import Blueprint, current_app, jsonify, request, session, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .database import PROGRESS_VERSION, RateBucket, User, get_db
from .catalog import load_catalog
from .schedule import validate_time
from datetime import date
from pathlib import Path

accounts = Blueprint('accounts', __name__, url_prefix='/api/account')
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    return session['_csrf']


def protected(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        expected = session.get('_csrf', '')
        supplied = request.headers.get('X-CSRF-Token', '')
        if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
            return jsonify(error='Refresh your session and try again.', code='csrf'), 403
        return function(*args, **kwargs)
    return wrapper


def current_user():
    user_id = session.get('user_id')
    return get_db().get(User, user_id) if isinstance(user_id, int) else None


def account_owner_error(user):
    if not user:
        return jsonify(error='Sign in to use your account.', code='auth_required'), 401
    if request.headers.get('X-Account-Id') != str(user.id):
        return jsonify(error='The signed-in account changed. Refresh and try again.', code='account_changed'), 409
    return None


def user_json(user):
    return {'id': user.id, 'username': user.username, 'email': user.email,
            'avatarUrl': f'/api/account/avatar?v={user.avatar_version}' if user.avatar else None,
            'createdAt': user.created_at}


def account_payload(user):
    return {'user': user_json(user) if user else None, 'csrfToken': csrf_token(),
            'guestId': session.get('guest_id') if not user else None,
            'state': user.preferences if user else None, 'revision': user.revision if user else 0,
            'progressVersion': PROGRESS_VERSION}


def establish_session(user):
    session.clear()
    session['user_id'] = user.id
    session.permanent = True
    return account_payload(user)


def rate_limit(action, identity='', limit=10, seconds=900):
    """A database-backed, atomic counter shared by all web workers."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    now = int(time.time())
    window = now // seconds
    fingerprint = hashlib.sha256(f'{action}:{identity or request.remote_addr}'.encode()).hexdigest()
    key = f'{fingerprint}:{window}'
    engine = current_app.extensions['account_engine']
    insert = sqlite_insert if engine.dialect.name == 'sqlite' else postgres_insert
    statement = insert(RateBucket).values(key=key, count=1, expires_at=(window + 1) * seconds)
    statement = statement.on_conflict_do_update(index_elements=['key'], set_={'count': RateBucket.count + 1}).returning(RateBucket.count)
    with engine.begin() as connection:
        connection.execute(delete(RateBucket).where(RateBucket.expires_at < now - 86400))
        count = connection.execute(statement).scalar_one()
    if count > limit:
        response = jsonify(error='Too many attempts. Please wait before trying again.')
        response.status_code = 429
        response.headers['Retry-After'] = str((window + 1) * seconds - now)
        return response
    return None


def valid_email(value):
    if not isinstance(value, str) or len(value) > 254:
        return False
    if value.count('@') != 1:
        return False
    local, domain = value.rsplit('@', 1)
    if not local or len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in local:
        return False
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local, re.I):
        return False
    labels = domain.split('.')
    return len(labels) >= 2 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label, re.I) for label in labels)


@accounts.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store, private'
    response.vary.add('Cookie')
    return response


@accounts.get('/session')
def get_session():
    return jsonify(account_payload(current_user()))


@accounts.post('/register')
@protected
def register():
    limited = rate_limit('register', limit=5, seconds=3600)
    if limited is not None:
        return limited
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error='Send the registration fields as JSON.'), 400
    username = data.get('username', '')
    email = data.get('email', '')
    password = data.get('password', '')
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,30}', username.strip()):
        return jsonify(error='Choose a username with 3–30 letters, numbers, or underscores.'), 400
    username = username.strip()
    email = email.strip().casefold() if isinstance(email, str) else ''
    if not valid_email(email):
        return jsonify(error='Enter a valid email address.'), 400
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        return jsonify(error='Choose a password between 10 and 128 characters.'), 400
    user = User(username=username, username_key=username.casefold(), email=email,
                password_hash=generate_password_hash(password, method='scrypt'))
    database = get_db()
    database.add(user)
    try:
        database.commit()
    except IntegrityError:
        database.rollback()
        return jsonify(error='That email or username is already in use.'), 409
    return jsonify(establish_session(user)), 201


@accounts.post('/login')
@protected
def login():
    limited = rate_limit('login-ip', limit=30)
    if limited is not None:
        return limited
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error='Enter your email or username and password.'), 400
    identifier = data.get('identifier', '')
    password = data.get('password', '')
    if not isinstance(identifier, str) or not isinstance(password, str) or len(identifier) > 254 or len(password) > 128:
        return jsonify(error='Email/username or password is incorrect.'), 401
    identifier = identifier.strip().casefold()
    limited = rate_limit('login-identity', identifier, limit=10)
    if limited is not None:
        return limited
    user = get_db().scalar(select(User).where(or_(User.username_key == identifier, User.email == identifier)))
    password_hash = user.password_hash if user else current_app.extensions['dummy_password_hash']
    correct = check_password_hash(password_hash, password)
    if not user or not correct:
        return jsonify(error='Email/username or password is incorrect.'), 401
    return jsonify(establish_session(user))


@accounts.post('/logout')
@protected
def logout():
    if session.get('guest_id') and not current_user():
        if request.headers.get('X-Guest-Id') != session['guest_id']:
            return jsonify(error='The guest session changed. Refresh and try again.', code='account_changed'), 409
        session.clear()
        return jsonify(account_payload(None))
    error = account_owner_error(current_user())
    if error is not None:
        return error
    session.clear()
    return jsonify(account_payload(None))


@accounts.post('/guest')
@protected
def start_guest():
    if current_user():
        return jsonify(error='Sign out of your account before starting a guest visit.', code='account_changed'), 409
    session.clear()
    session['guest_id'] = secrets.token_urlsafe(24)
    # This cookie grants vocabulary access only. No guest profile is created.
    session.permanent = False
    return jsonify(account_payload(None))


def normalized_photo(content):
    if not content or len(content) > MAX_PHOTO_BYTES:
        raise ValueError('Choose an image up to 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Choose a JPG, PNG, or WebP image.')
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError('Choose an image no larger than 16 megapixels.')
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((384, 384), Image.Resampling.LANCZOS)
                image = image.convert('RGBA')
                clean = Image.new('RGB', image.size, '#e6e5dd')
                clean.paste(image, mask=image.getchannel('A'))
                output = BytesIO()
                clean.save(output, format='JPEG', quality=85, optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError('That image could not be read. Choose a valid JPG, PNG, or WebP file.') from error


@accounts.get('/avatar')
def get_avatar():
    user = current_user()
    if not user:
        return jsonify(error='Sign in to view your profile photo.'), 401
    if not user.avatar:
        return jsonify(error='No profile photo has been added.'), 404
    return Response(user.avatar, mimetype='image/jpeg')


@accounts.put('/avatar')
@protected
def upload_avatar():
    user = current_user()
    error = account_owner_error(user)
    if error is not None:
        return error
    photo = request.files.get('photo')
    if photo is None:
        return jsonify(error='Choose a photo first.'), 400
    try:
        user.avatar = normalized_photo(photo.stream.read(MAX_PHOTO_BYTES + 1))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    user.avatar_version += 1
    get_db().commit()
    return jsonify(user=user_json(user))


@accounts.delete('/avatar')
@protected
def delete_avatar():
    user = current_user()
    error = account_owner_error(user)
    if error is not None:
        return error
    user.avatar = None
    user.avatar_version += 1
    get_db().commit()
    return jsonify(user=user_json(user))


def clean_preferences(value, previous=None):
    if not isinstance(value, dict):
        raise ValueError('Learning preferences must be a JSON object.')
    collections, words, _ = load_catalog(Path(current_app.root_path))
    collection_ids = {item['id'] for item in collections}
    word_ids = {item['id'] for item in words}
    result = {'version': 2}
    for field, allowed in (('interests', collection_ids), ('saved', word_ids), ('hiddenWords', word_ids)):
        entries = value.get(field, [])
        if not isinstance(entries, list) or len(entries) > 1000 or any(not isinstance(item, str) for item in entries):
            raise ValueError(f'Invalid {field} list.')
        result[field] = list(dict.fromkeys(item for item in entries if item in allowed))
    history = value.get('history', [])
    if not isinstance(history, list) or len(history) > 5000:
        raise ValueError('History may contain up to 5,000 entries.')
    result['history'] = []
    seen = set()
    for item in history:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('date'), str):
            raise ValueError('Invalid history entry.')
        day = date.fromisoformat(item['date']).isoformat()
        key = (item['id'], day)
        if item['id'] in word_ids and key not in seen:
            result['history'].append({'id': item['id'], 'date': day})
            seen.add(key)
    result['theme'] = value.get('theme', 'noir')
    if result['theme'] not in ('noir', 'studio', 'experimental'):
        raise ValueError('Choose a valid appearance.')
    result['updateTime'] = value.get('updateTime', '08:00')
    validate_time(result['updateTime'])
    for field in ('onboarded', 'reduceMotion'):
        if not isinstance(value.get(field, False), bool):
            raise ValueError(f'Invalid {field} setting.')
        result[field] = value.get(field, False)
    result['onboarded'] = result['onboarded'] and bool(result['interests'])
    # Older clients omit guide metadata; keep the account's existing guide.
    previous = previous if isinstance(previous, dict) else {}
    result['guideLanguage'] = value.get('guideLanguage', previous.get('guideLanguage'))
    if result['guideLanguage'] not in (None, 'ru', 'kk', 'en'):
        raise ValueError('Choose Russian, Kazakh, or English for the guide.')
    result['guideStep'] = value.get('guideStep', previous.get('guideStep', 'done' if result['onboarded'] else 'language'))
    reading_steps = ('word', 'definition', 'synonyms', 'examples', 'save', 'saved', 'deep')
    if result['guideStep'] not in ('language', 'time', 'collections', 'settings', *reading_steps, 'done'):
        raise ValueError('Choose a valid guide step.')
    if result['guideStep'] in ('time', 'collections', 'settings', *reading_steps) and result['guideLanguage'] is None:
        raise ValueError('Choose a guide language first.')
    if result['guideStep'] in reading_steps and not result['onboarded']:
        raise ValueError('Finish choosing your time and collections first.')
    return result


@accounts.put('/state')
@protected
def save_state():
    user = current_user()
    error = account_owner_error(user)
    if error is not None:
        return error
    if request.content_length and request.content_length > 128 * 1024:
        return jsonify(error='The learning data is too large to sync.'), 413
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get('revision')) is not int or data['revision'] < 0:
        return jsonify(error='Send a valid revision and learning state.'), 400
    if type(data.get('progressVersion')) is not int or data['progressVersion'] != PROGRESS_VERSION:
        return jsonify(error='Your learning profile has been reset. Reload LEXI before continuing.',
                       code='progress_reset', progressVersion=PROGRESS_VERSION), 409
    try:
        state = clean_preferences(data.get('state'), user.preferences)
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    database = get_db()
    changed = database.execute(update(User).where(User.id == user.id, User.revision == data['revision'])
                               .values(preferences=state, revision=User.revision + 1), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        database.rollback()
        database.refresh(user)
        return jsonify(error='Newer changes are available.', code='conflict', state=user.preferences, revision=user.revision), 409
    database.commit()
    return jsonify(state=state, revision=data['revision'] + 1)
