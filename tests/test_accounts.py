"""Account isolation, credential handling, uploads, persistence and sync conflicts."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from sqlalchemy import delete, func, select
from werkzeug.security import check_password_hash

from app import create_app
from lexi.database import DataMigration, ISOLATION_MIGRATION, PROGRESS_VERSION, User, get_db


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
                'reduceMotion': True, 'guideLanguage': None, 'guideStep': 'done', **patch}

    def save(self, account, state=None, revision=0, client=None):
        return (client or self.client).put('/api/account/state', json={
            'state': state if state is not None else self.state(), 'revision': revision, 'progressVersion': PROGRESS_VERSION,
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
        for path in ('register', 'login', 'guest', 'logout', 'state', 'avatar'):
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

    def test_old_clients_cannot_restore_progress_after_the_reset(self):
        account = self.register()
        for old_version in (None, 1, True):
            response = self.client.put('/api/account/state', json={
                'state': self.state(), 'revision': 0, 'progressVersion': old_version,
            }, headers=self.headers(account))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json['code'], 'progress_reset')
        self.assertIsNone(self.client.get('/api/account/session').json['state'])
        self.assertEqual(self.save(account).status_code, 200)

    def test_reset_runs_once_for_all_accounts_then_preserves_new_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'TESTING': True, 'DATABASE_URL': f'sqlite:///{Path(directory) / "migration.sqlite3"}'}
            original = create_app(config)
            ada_client, bob_client = original.test_client(), original.test_client()
            ada = self.register(ada_client)
            bob = self.register(bob_client, 'Bob_lexi', 'bob@example.com')
            word = ada_client.get('/api/catalog').json['words'][0]['id']
            for client, account in ((ada_client, ada), (bob_client, bob)):
                self.assertEqual(self.save(account, self.state(saved=[word], hiddenWords=[word],
                    history=[{'id': word, 'date': '2026-10-21'}]), client=client).status_code, 200)
            self.assertEqual(self.photo(ada, self.image(), client=ada_client).status_code, 200)
            cookies = [client.get_cookie('lexi_session').value for client in (ada_client, bob_client)]
            with original.app_context():
                row = get_db().get(User, ada['user']['id'])
                old_hash, old_photo = row.password_hash, row.avatar
                # Simulate a database from the release before the one-time reset.
                get_db().execute(delete(DataMigration).where(DataMigration.key == ISOLATION_MIGRATION))
                get_db().commit()
            original.extensions['account_engine'].dispose()

            upgraded = create_app(config)
            clients = [upgraded.test_client(), upgraded.test_client()]
            for client, cookie in zip(clients, cookies):
                client.set_cookie('lexi_session', cookie)
                session = client.get('/api/account/session').json
                self.assertIsNone(session['state'])
                self.assertEqual(session['revision'], 2)
                self.assertEqual(session['progressVersion'], PROGRESS_VERSION)
            with upgraded.app_context():
                row = get_db().get(User, ada['user']['id'])
                self.assertEqual(row.password_hash, old_hash)
                self.assertEqual(row.avatar, old_photo)
                self.assertEqual(row.username, ada['user']['username'])
            clean = clients[0].get('/api/account/session').json
            response = self.save(clean, self.state(interests=['culture'], saved=[], hiddenWords=[],
                history=[{'id': word, 'date': '2026-10-22'}]), revision=clean['revision'], client=clients[0])
            self.assertEqual(response.status_code, 200)
            expected = response.json['state']
            upgraded.extensions['account_engine'].dispose()

            restarted = create_app(config)
            client = restarted.test_client()
            client.set_cookie('lexi_session', cookies[0])
            self.assertEqual(client.get('/api/account/session').json['state'], expected)
            client.set_cookie('lexi_session', cookies[1])
            self.assertIsNone(client.get('/api/account/session').json['state'])
            restarted.extensions['account_engine'].dispose()

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

    def test_guest_can_learn_without_creating_or_saving_a_profile(self):
        response = self.client.post('/api/account/guest', headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 200)
        guest = response.json
        self.assertIsNone(guest['user'])
        self.assertIsNone(guest['state'])
        self.assertTrue(guest['guestId'])
        self.assertNotEqual(guest['csrfToken'], self.csrf)
        cookie = self.client.get_cookie('lexi_session')
        self.assertIsNone(cookie.expires)
        self.assertTrue(cookie.http_only)
        self.assertEqual(self.client.get('/api/catalog').status_code, 200)
        self.assertEqual(self.client.get('/api/daily?collections=ielts').status_code, 200)
        headers = {'X-CSRF-Token': guest['csrfToken']}
        self.assertEqual(self.client.put('/api/account/state', json={
            'state': self.state(), 'revision': 0, 'progressVersion': PROGRESS_VERSION,
        }, headers=headers).status_code, 401)
        for method in (self.client.get, self.client.put, self.client.delete):
            self.assertEqual(method('/api/account/avatar', headers=headers).status_code, 401)
        self.assertIsNone(self.client.get('/api/account/session').json['state'])
        with self.app.app_context():
            self.assertEqual(get_db().scalar(select(func.count()).select_from(User)), 0)

    def test_guest_exit_is_owned_and_revokes_learning_access(self):
        guest = self.client.post('/api/account/guest', headers={'X-CSRF-Token': self.csrf}).json
        headers = {'X-CSRF-Token': guest['csrfToken'], 'X-Guest-Id': 'stale-guest'}
        self.assertEqual(self.client.post('/api/account/logout', headers=headers).status_code, 409)
        self.assertEqual(self.client.get('/api/catalog').status_code, 200)
        headers['X-Guest-Id'] = guest['guestId']
        response = self.client.post('/api/account/logout', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json['guestId'])
        self.assertEqual(self.client.get('/api/catalog').status_code, 401)
        self.assertEqual(self.client.get('/api/daily').status_code, 401)

    def test_guest_to_account_starts_clean_and_stale_guest_cannot_sign_it_out(self):
        guest = self.client.post('/api/account/guest', headers={'X-CSRF-Token': self.csrf}).json
        account = self.register()
        self.assertIsNone(account['guestId'])
        self.assertIsNone(account['state'])
        self.assertEqual(self.save(account).status_code, 200)
        headers = {'X-CSRF-Token': account['csrfToken'], 'X-Guest-Id': guest['guestId']}
        self.assertEqual(self.client.post('/api/account/logout', headers=headers).status_code, 409)
        self.assertEqual(self.client.post('/api/account/guest', headers=headers).status_code, 409)
        session = self.client.get('/api/account/session').json
        self.assertEqual(session['user']['id'], account['user']['id'])
        self.assertEqual(session['state']['interests'], ['ielts'])

    def test_learning_endpoints_require_registration_or_login(self):
        for endpoint in ('/api/catalog', '/api/daily?collections=ielts'):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json['code'], 'auth_required')
            self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.register()
        self.assertEqual(self.client.get('/api/catalog').status_code, 200)
        self.assertEqual(self.client.get('/api/daily').status_code, 200)

    def test_logout_locks_learning_endpoints_again(self):
        data = self.register()
        self.client.post('/api/account/logout', headers=self.headers(data))
        self.assertEqual(self.client.get('/api/catalog').status_code, 401)
        self.assertEqual(self.client.get('/api/daily').status_code, 401)

    def test_entry_shell_is_public_but_learning_starts_hidden(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="auth-screen"', response.data)
        self.assertIn(b'id="learning-app" hidden inert', response.data)
        self.assertIn(b'class="word-plane"', response.data)
        self.assertNotIn(b'No account. No pressure.', response.data)

    def test_public_offline_shell_installs_before_sign_in(self):
        with self.client.get('/sw.js') as response:
            source = response.data.decode()
            shell = source.split('const SHELL = [', 1)[1].split('];', 1)[0]
            self.assertNotIn('/api/catalog', shell)
            self.assertIn('/static/css/entry.css', shell)

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
                      {'onboarded': 1}, {'saved': [1]}, {'history': [None]},
                      {'guideLanguage': 'de'}, {'guideLanguage': ['ru']}, {'guideStep': 'unknown'},
                      {'guideLanguage': None, 'guideStep': 'time'}):
            self.assertEqual(self.save(data, self.state(**patch)).status_code, 400, patch)
        for revision in (True, -1, '0'):
            self.assertEqual(self.save(data, revision=revision).status_code, 400)
        self.assertEqual(self.client.get('/api/account/session').json['revision'], 0)

    def test_guide_language_and_step_persist_per_account_and_survive_older_clients(self):
        ada = self.register()
        partial = self.state(onboarded=False, interests=[], guideLanguage='ru', guideStep='time')
        self.assertEqual(self.save(ada, partial).status_code, 200)
        state = self.client.get('/api/account/session').json['state']
        self.assertEqual((state['guideLanguage'], state['guideStep']), ('ru', 'time'))
        old_client = {key: value for key, value in partial.items() if key not in ('guideLanguage', 'guideStep')}
        response = self.save(ada, old_client, revision=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json['state']['guideLanguage'], response.json['state']['guideStep']), ('ru', 'time'))
        for revision, language in enumerate(('kk', 'en'), start=2):
            response = self.save(ada, self.state(guideLanguage=language, guideStep='settings'), revision=revision)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['state']['guideLanguage'], language)
        other = self.app.test_client()
        bob = self.register(other, 'Bob_guide', 'bob-guide@example.com')
        self.assertIsNone(bob['state'])
        self.assertEqual(self.client.get('/api/account/session').json['state']['guideLanguage'], 'en')

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
