"""Account isolation, credential handling, uploads, persistence and sync conflicts."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from werkzeug.security import check_password_hash

from app import create_app
from lexi.database import User, get_db


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/account/session').json['csrfToken']

    def tearDown(self):
        self.app.extensions['account_engine'].dispose()

    def register(self, client=None, username='Ada_lexi', email='ada@example.com'):
        client = client or self.client
        token = client.get('/api/account/session').json['csrfToken']
        response = client.post('/api/account/register', json={
            'username': username, 'email': email, 'password': 'Sample-password-42',
        }, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def headers(self, data):
        return {'X-CSRF-Token': data['csrfToken'], 'X-Account-Id': str(data['user']['id'])}

    def state(self, **patch):
        return {'theme': 'studio', 'interests': ['ielts'], 'saved': [], 'history': [],
                'hiddenWords': [], 'updateTime': '09:15', 'onboarded': True,
                'reduceMotion': True, **patch}

    def save(self, account, state=None, revision=0, client=None):
        return (client or self.client).put('/api/account/state', json={
            'state': state if state is not None else self.state(), 'revision': revision,
        }, headers=self.headers(account))

    def photo(self, account, content, filename='photo.png', client=None):
        return (client or self.client).put('/api/account/avatar', data={
            'photo': (BytesIO(content), filename),
        }, headers=self.headers(account))

    def image(self, size=(800, 600), format='PNG'):
        output = BytesIO()
        Image.new('RGB', size, '#a8bc7c').save(output, format=format)
        return output.getvalue()

    def test_registration_hashes_password_and_uses_private_cookie(self):
        data = self.register(email='ADA@EXAMPLE.COM')
        self.assertEqual(data['user']['email'], 'ada@example.com')
        self.assertNotIn('password', str(data))
        with self.app.app_context():
            user = get_db().get(User, data['user']['id'])
            self.assertTrue(user.password_hash.startswith('scrypt:'))
            self.assertTrue(check_password_hash(user.password_hash, 'Sample-password-42'))
        cookie = self.client.get_cookie('lexi_session')
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, 'Lax')
        self.assertNotEqual(data['csrfToken'], self.csrf)

    def test_private_responses_are_never_cached(self):
        for path in ('/api/account/session', '/api/account/avatar'):
            response = self.client.get(path)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertIn('Cookie', response.headers['Vary'])

    def test_csrf_required_even_for_registration_and_login(self):
        for path in ('register', 'login', 'logout', 'state', 'avatar'):
            method = self.client.put if path in ('state', 'avatar') else self.client.post
            self.assertEqual(method('/api/account/' + path, json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/account/login', json={}, headers={
            'X-CSRF-Token': 'кириллица',
        }).status_code, 403)

    def test_login_accepts_case_insensitive_username_or_email(self):
        data = self.register()
        self.client.post('/api/account/logout', headers=self.headers(data))
        for identifier in ('ADA_LEXI', 'ADA@EXAMPLE.COM'):
            token = self.client.get('/api/account/session').json['csrfToken']
            response = self.client.post('/api/account/login', json={
                'identifier': identifier, 'password': 'Sample-password-42',
            }, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 200)
            self.client.post('/api/account/logout', headers=self.headers(response.json))

    def test_wrong_password_and_unknown_account_have_same_error(self):
        self.register()
        errors = []
        token = self.client.get('/api/account/session').json['csrfToken']
        for identifier in ('Ada_lexi', 'not_registered'):
            response = self.client.post('/api/account/login', json={
                'identifier': identifier, 'password': 'wrong-password',
            }, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 401)
            errors.append(response.json)
        self.assertEqual(*errors)

    def test_duplicate_email_or_username_cannot_replace_account(self):
        self.register()
        token = self.client.get('/api/account/session').json['csrfToken']
        for username, email in [('ADA_LEXI', 'new@example.com'), ('new_login', 'ADA@EXAMPLE.COM')]:
            response = self.client.post('/api/account/register', json={
                'username': username, 'email': email, 'password': 'Another-password-42',
            }, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 409)

    def test_registration_validation_and_rate_limit(self):
        for patch in ({'username': '<script>'}, {'email': 'not-an-email'}, {'password': 'short'}):
            response = self.client.post('/api/account/register', json={
                'username': 'Ada_lexi', 'email': 'ada@example.com',
                'password': 'Sample-password-42', **patch,
            }, headers={'X-CSRF-Token': self.csrf})
            self.assertEqual(response.status_code, 400)
        for _ in range(3):
            response = self.client.post('/api/account/register', json={}, headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers['Retry-After']), 0)

    def test_login_rate_limit_shared_across_clients(self):
        for index in range(11):
            client = self.app.test_client()
            token = client.get('/api/account/session').json['csrfToken']
            response = client.post('/api/account/login', json={
                'identifier': 'unknown', 'password': 'wrong-password',
            }, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 401 if index < 10 else 429)

    def test_state_round_trip_and_compare_and_swap(self):
        data = self.register()
        response = self.save(data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['revision'], 1)
        self.assertEqual(response.json['state']['theme'], 'studio')
        conflict = self.save(data, self.state(theme='noir'))
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json['code'], 'conflict')
        self.assertEqual(conflict.json['state']['theme'], 'studio')
        self.assertEqual(self.save(data, self.state(theme='noir'), revision=1).status_code, 200)
        self.assertEqual(self.client.get('/api/account/session').json['state']['theme'], 'noir')

    def test_states_and_photos_belong_to_current_account(self):
        ada = self.register()
        other = self.app.test_client()
        bob = self.register(other, 'Bob_lexi', 'bob@example.com')
        self.save(ada)
        self.photo(ada, self.image())
        session = other.get('/api/account/session').json
        self.assertIsNone(session['state'])
        self.assertIsNone(session['user']['avatarUrl'])
        self.assertEqual(other.get('/api/account/avatar').status_code, 404)
        stale = {'X-CSRF-Token': bob['csrfToken'], 'X-Account-Id': str(ada['user']['id'])}
        for method, path in ((other.put, 'state'), (other.put, 'avatar'), (other.delete, 'avatar'), (other.post, 'logout')):
            response = method('/api/account/' + path, json={}, headers=stale)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json['code'], 'account_changed')

    def test_guest_cannot_write_learning_state_or_read_photo(self):
        self.assertEqual(self.client.put('/api/account/state', json={}, headers={
            'X-CSRF-Token': self.csrf,
        }).status_code, 401)
        self.assertEqual(self.client.get('/api/account/avatar').status_code, 401)

    def test_server_filters_unknown_words_and_deduplicates(self):
        data = self.register()
        catalog = self.client.get('/api/catalog').json
        word = catalog['words'][0]['id']
        response = self.save(data, self.state(saved=[word, word, 'deleted-word'],
            hiddenWords=[word], interests=['ielts', 'deleted-collection'],
            history=[{'id': word, 'date': '2026-10-21'}] * 2))
        self.assertEqual(response.status_code, 200)
        state = response.json['state']
        self.assertEqual(state['saved'], [word])
        self.assertEqual(state['interests'], ['ielts'])
        self.assertEqual(len(state['history']), 1)
        self.assertEqual(state['hiddenWords'], [word])

    def test_bad_state_is_rejected_without_changing_revision(self):
        data = self.register()
        for patch in ({'history': [{'id': 'word', 'date': '2026-02-30'}]},
                      {'updateTime': '25:00'}, {'theme': 'missing'}, {'interests': 'ielts'},
                      {'onboarded': 1}, {'saved': [1]}, {'history': [None]}):
            self.assertEqual(self.save(data, self.state(**patch)).status_code, 400, patch)
        for revision in (True, -1, '0'):
            self.assertEqual(self.save(data, revision=revision).status_code, 400)
        self.assertEqual(self.client.get('/api/account/session').json['revision'], 0)

    def test_photo_is_resized_reencoded_and_can_be_deleted(self):
        data = self.register()
        response = self.photo(data, self.image())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['avatarUrl'], '/api/account/avatar?v=1')
        avatar = self.client.get('/api/account/avatar')
        self.assertEqual(avatar.mimetype, 'image/jpeg')
        with Image.open(BytesIO(avatar.data)) as image:
            self.assertEqual(image.size, (384, 288))
            self.assertFalse(image.getexif())
        response = self.client.delete('/api/account/avatar', headers=self.headers(data))
        self.assertIsNone(response.json['user']['avatarUrl'])
        self.assertEqual(self.client.get('/api/account/avatar').status_code, 404)

    def test_invalid_oversized_or_disguised_photos_rejected(self):
        data = self.register()
        for content in (b'<svg onload="alert(1)"></svg>', b'not an image', self.image(format='GIF'),
                        b'x' * (5 * 1024 * 1024 + 1), self.image(size=(4001, 4000))):
            self.assertEqual(self.photo(data, content).status_code, 400)
        self.assertEqual(self.client.get('/api/account/avatar').status_code, 404)

    def test_phone_photo_orientation_is_applied_and_metadata_removed(self):
        data = self.register()
        output = BytesIO()
        exif = Image.Exif()
        exif[274] = 6  # A phone photo rotated 90 degrees clockwise.
        exif[315] = 'Private artist metadata'
        Image.new('RGB', (800, 400)).save(output, format='JPEG', exif=exif)
        self.assertEqual(self.photo(data, output.getvalue(), filename='phone.jpg').status_code, 200)
        with Image.open(BytesIO(self.client.get('/api/account/avatar').data)) as photo:
            self.assertEqual(photo.size, (192, 384))
            self.assertFalse(photo.getexif())

    def test_logout_invalidates_authenticated_session(self):
        data = self.register()
        response = self.client.post('/api/account/logout', headers=self.headers(data))
        self.assertIsNone(response.json['user'])
        self.assertNotEqual(response.json['csrfToken'], data['csrfToken'])
        self.assertEqual(self.client.get('/api/account/avatar').status_code, 401)
        self.assertIsNone(self.client.get('/api/account/session').json['user'])

    def test_database_survives_app_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'TESTING': True, 'DATABASE_URL': f'sqlite:///{Path(directory) / "accounts.sqlite3"}'}
            first = create_app(config)
            client = first.test_client()
            data = self.register(client)
            self.save(data, client=client)
            self.photo(data, self.image(), client=client)
            cookie = client.get_cookie('lexi_session').value
            first.extensions['account_engine'].dispose()
            second = create_app(config)
            client = second.test_client()
            client.set_cookie('lexi_session', cookie)
            response = client.get('/api/account/session').json
            self.assertEqual(response['user']['username'], 'Ada_lexi')
            self.assertEqual(response['state']['updateTime'], '09:15')
            self.assertEqual(client.get('/api/account/avatar').status_code, 200)
            second.extensions['account_engine'].dispose()


if __name__ == '__main__':
    unittest.main()
