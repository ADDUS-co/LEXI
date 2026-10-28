"""Real OAuth state/PKCE/OIDC validation with locally signed tokens and mocked providers."""
import time
import json
import hashlib
import base64
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from joserfc import jwt
from joserfc.jwk import RSAKey
from requests import Response
from sqlalchemy import func, select

from app import create_app
from lexi.database import OAuthIdentity, OAuthState, User, get_db
from lexi.oauth import state_key


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = RSAKey.generate_key(2048, parameters={'kid': 'local-test-key'})

    def setUp(self):
        self.app = create_app({'TESTING': True, 'LEXI_PUBLIC_URL': 'https://lexi.example',
                               'GOOGLE_CLIENT_ID': 'google-test-client', 'GOOGLE_CLIENT_SECRET': 'google-test-secret',
                               'GITHUB_CLIENT_ID': 'github-test-client', 'GITHUB_CLIENT_SECRET': 'github-test-secret'})
        self.client = self.app.test_client()
        self.google = self.app.extensions['lexi_oauth'].create_client('google')
        self.google.server_metadata.update(issuer='https://accounts.google.com', authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',
                                           token_endpoint='https://oauth2.googleapis.com/token', id_token_signing_alg_values_supported=['RS256'],
                                           jwks={'keys': [self.key.as_dict(private=False)]}, _loaded_at=time.time())
        self.github = self.app.extensions['lexi_oauth'].create_client('github')

    def tearDown(self):
        self.app.extensions['account_engine'].dispose()

    def session(self):
        return self.client.get('/api/account/session').json

    def start(self, provider='google', intent='signin', owner=None):
        headers = {'X-CSRF-Token': self.session()['csrfToken']}
        if owner is not None:
            headers['X-Account-Id'] = str(owner)
        response = self.client.post('/api/account/oauth/'+provider+'/start', json={'intent': intent}, headers=headers)
        self.assertEqual(response.status_code, 200, response.json)
        return parse_qs(urlsplit(response.json['url']).query)

    def google_callback(self, query, claims=None, key=None):
        now = int(time.time())
        payload = {'iss': 'https://accounts.google.com', 'aud': 'google-test-client', 'sub': 'google-subject-1',
                   'iat': now, 'exp': now+600, 'nonce': query['nonce'][0], 'email': 'ada@example.com', 'email_verified': True, 'name': 'Ada'}
        payload.update(claims or {})
        token = jwt.encode({'alg': 'RS256', 'kid': 'local-test-key'}, payload, key or self.key)
        with patch.object(self.google, 'fetch_access_token', return_value={'access_token': 'provider-token-not-for-storage', 'token_type': 'Bearer', 'id_token': token}) as exchange:
            response = self.client.get('/api/account/oauth/google/callback', query_string={'state': query['state'][0], 'code': 'one-use-test-code'})
        self.assertEqual(response.status_code, 303)
        self.last_callback = response
        return self.session(), exchange

    def counts(self):
        with self.app.app_context():
            return tuple(get_db().scalar(select(func.count()).select_from(model)) for model in (User, OAuthIdentity))

    def password_account(self):
        return self.client.post('/api/account/register', json={'username': 'Local_Ada', 'email': 'ada@example.com', 'password': 'Local-password-42'},
                                headers={'X-CSRF-Token': self.session()['csrfToken']}).json

    def logout(self):
        data = self.session()
        response = self.client.post('/api/account/logout', headers={'X-CSRF-Token': data['csrfToken'], 'X-Account-Id': str(data['user']['id'])})
        self.assertEqual(response.status_code, 200)

    def test_only_configured_providers_render_without_secrets(self):
        response = self.client.get('/')
        self.assertIn(b'data-provider="google"', response.data)
        self.assertIn(b'data-provider="github"', response.data)
        self.assertNotIn(b'google-test-secret', response.data)
        disabled = create_app({'TESTING': True, 'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': '', 'GITHUB_CLIENT_ID': '', 'GITHUB_CLIENT_SECRET': ''})
        self.assertNotIn(b'data-provider="google"', disabled.test_client().get('/').data)
        disabled.extensions['account_engine'].dispose()

    def test_start_requires_csrf_and_explicit_link_owner(self):
        self.assertEqual(self.client.get('/api/account/oauth/google/start').status_code, 405)
        self.assertEqual(self.client.post('/api/account/oauth/google/start', json={'intent': 'signin'}).status_code, 403)
        csrf = self.session()['csrfToken']
        self.assertEqual(self.client.post('/api/account/oauth/google/start', json={'intent': 'link'}, headers={'X-CSRF-Token': csrf}).status_code, 401)
        account = self.password_account()
        self.assertEqual(self.client.post('/api/account/oauth/google/start', json={'intent': 'link'}, headers={'X-CSRF-Token': account['csrfToken']}).status_code, 409)

    def test_pkce_nonce_and_callback_are_pinned_to_public_origin(self):
        for provider in ('google', 'github'):
            query = self.start(provider)
            self.assertEqual(query['code_challenge_method'], ['S256'])
            self.assertEqual(len(query['code_challenge'][0]), 43)
            self.assertEqual(query['redirect_uri'], ['https://lexi.example/api/account/oauth/'+provider+'/callback'])
            self.assertNotIn('client_secret', query)
            if provider == 'google':
                self.assertTrue(query['nonce'][0])
                self.assertEqual(query['prompt'], ['select_account'])
            else:
                self.assertNotIn('prompt', query)

    def test_valid_google_creates_clean_account_and_never_stores_tokens(self):
        query = self.start()
        data, exchange = self.google_callback(query)
        self.assertEqual(self.counts(), (1, 1))
        self.assertIsNone(data['state'])
        self.assertEqual(data['user']['linkedProviders'], ['google'])
        self.assertTrue(exchange.call_args.kwargs['code_verifier'])
        with self.client.session_transaction() as cookie:
            self.assertNotIn('provider-token-not-for-storage', str(dict(cookie)))
            self.assertNotIn('id_token', str(dict(cookie)))
            self.assertFalse(any(key.startswith('_state_') for key in cookie))
        with self.app.app_context():
            user = get_db().get(User, data['user']['id'])
            self.assertTrue(user.password_hash.startswith('scrypt:'))
        self.assertIsNone(self.session()['oauthNotice'])

    def test_google_continue_establishes_session_before_completion_page(self):
        data, _ = self.google_callback(self.start())
        self.assertEqual(self.last_callback.headers['Location'], '/auth/complete')
        response = self.client.get('/auth/complete')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-oauth-return', response.data)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.session()['user']['id'], data['user']['id'])
        self.assertEqual(self.client.get('/api/catalog').status_code, 200)

    def test_completion_page_does_not_authenticate_an_anonymous_visitor(self):
        response = self.client.get('/auth/complete')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.session()['user'])
        self.assertEqual(self.client.get('/api/catalog').status_code, 401)

    def test_returning_subject_restores_same_progress_after_email_and_name_change(self):
        first, _ = self.google_callback(self.start())
        with self.app.app_context():
            user = get_db().get(User, first['user']['id'])
            user.preferences = {'theme': 'experimental', 'saved': ['ielts-coherent']}
            user.revision = 7
            get_db().commit()
        self.logout()
        data, _ = self.google_callback(self.start(), {'email': 'changed@example.com', 'name': 'A different display name'})
        self.assertEqual(data['user']['id'], first['user']['id'])
        self.assertEqual(data['state']['saved'], ['ielts-coherent'])
        self.assertEqual(data['revision'], 7)
        self.assertEqual(self.counts(), (1, 1))

    def test_signed_tokens_still_require_correct_nonce_audience_issuer_and_expiry(self):
        for changes in ({'nonce': 'wrong'}, {'nonce': 'wrong', 'nonce_supported': False}, {'aud': 'someone-else'}, {'iss': 'https://attacker.example'}, {'exp': int(time.time())-1000}):
            with self.subTest(claims=changes):
                data, _ = self.google_callback(self.start(), changes)
                self.assertIsNone(data['user'])
                self.assertEqual(self.counts(), (0, 0))

    def test_bad_signature_and_unverified_email_are_rejected(self):
        data, _ = self.google_callback(self.start(), key=RSAKey.generate_key(2048))
        self.assertIsNone(data['user'])
        for verified in (False, 'true', None):
            data, _ = self.google_callback(self.start(), {'email_verified': verified})
            self.assertIsNone(data['user'])
        self.assertEqual(self.counts(), (0, 0))

    def test_google_cannot_skip_the_id_token(self):
        query = self.start()
        with patch.object(self.google, 'fetch_access_token', return_value={'access_token': 'test-token', 'userinfo': {'sub': 'spoofed', 'email': 'ada@example.com', 'email_verified': True}}):
            self.client.get('/api/account/oauth/google/callback', query_string={'state': query['state'][0], 'code': 'missing-id-token'})
        self.assertIsNone(self.session()['user'])
        self.assertEqual(self.counts(), (0, 0))

    def test_missing_or_replayed_state_never_exchanges_a_code(self):
        with patch.object(self.google, 'fetch_access_token') as exchange:
            response = self.client.get('/api/account/oauth/google/callback?code=untrusted&state=unknown')
            self.assertEqual(response.status_code, 303)
            exchange.assert_not_called()
        query = self.start()
        self.google_callback(query)
        with patch.object(self.google, 'fetch_access_token') as exchange:
            self.client.get('/api/account/oauth/google/callback', query_string={'state': query['state'][0], 'code': 'same-code'})
            exchange.assert_not_called()
        self.assertEqual(self.counts(), (1, 1))

    def test_expired_provider_mismatch_and_replaced_flow_are_rejected(self):
        old = self.start()
        latest = self.start()
        self.client.get('/api/account/oauth/google/callback', query_string={'state': old['state'][0], 'code': 'old'})
        with self.app.app_context():
            get_db().get(OAuthState, state_key('google', latest['state'][0])).expires_at -= 700
            get_db().commit()
        with patch.object(self.google, 'fetch_access_token') as exchange:
            self.client.get('/api/account/oauth/google/callback', query_string={'state': latest['state'][0], 'code': 'expired'})
            exchange.assert_not_called()
        query = self.start()
        with patch.object(self.github, 'fetch_access_token') as exchange:
            self.client.get('/api/account/oauth/github/callback', query_string={'state': query['state'][0], 'code': 'wrong-provider'})
            exchange.assert_not_called()
        self.assertEqual(self.counts(), (0, 0))

    def test_cancellation_is_readable_and_does_not_reflect_provider_error(self):
        query = self.start()
        self.client.get('/api/account/oauth/google/callback', query_string={'state': query['state'][0], 'error': 'access_denied', 'error_description': '<script>secret</script>'})
        notice = self.session()['oauthNotice']
        self.assertIn('cancelled', notice['message'])
        self.assertNotIn('script', notice['message'])
        self.assertEqual(self.counts(), (0, 0))

    def test_email_collision_cannot_take_over_a_password_account(self):
        original = self.password_account()
        self.logout()
        data, _ = self.google_callback(self.start())
        self.assertIsNone(data['user'])
        self.assertTrue(data['oauthNotice']['signin'])
        self.assertEqual(self.last_callback.headers['Location'], '/#home')
        self.assertEqual(self.counts(), (1, 0))
        with self.app.app_context():
            self.assertEqual(get_db().get(User, original['user']['id']).username, 'Local_Ada')

    def test_google_retry_after_email_collision_can_select_another_account(self):
        original = self.password_account()
        with self.app.app_context():
            user = get_db().get(User, original['user']['id'])
            original_hash = user.password_hash
            user.preferences = {'saved': ['law-equity'], 'theme': 'studio'}
            user.revision = 4
            get_db().commit()
        self.logout()
        first = self.start()
        data, _ = self.google_callback(first)
        self.assertIsNone(data['user'])
        self.assertTrue(data['oauthNotice']['signin'])
        self.assertEqual(self.counts(), (1, 0))

        retry = self.start()
        self.assertEqual(retry['prompt'], ['select_account'])
        for key in ('state', 'nonce', 'code_challenge'):
            self.assertNotEqual(retry[key], first[key])
        data, _ = self.google_callback(retry, {'sub': 'another-google-subject', 'email': 'another@example.com', 'name': 'Another learner'})
        self.assertEqual(data['user']['email'], 'another@example.com')
        self.assertNotEqual(data['user']['id'], original['user']['id'])
        self.assertEqual(data['user']['linkedProviders'], ['google'])
        self.assertIsNone(data['state'])
        self.assertEqual(self.counts(), (2, 1))
        with self.app.app_context():
            user = get_db().get(User, original['user']['id'])
            self.assertEqual(user.password_hash, original_hash)
            self.assertEqual(user.preferences, {'saved': ['law-equity'], 'theme': 'studio'})
            self.assertEqual(user.revision, 4)
            self.assertEqual(get_db().scalar(select(OAuthIdentity)).user_id, data['user']['id'])

    def test_explicit_link_preserves_password_profile_and_progress(self):
        original = self.password_account()
        with self.app.app_context():
            user = get_db().get(User, original['user']['id'])
            before = user.password_hash
            user.preferences = {'saved': ['law-equity'], 'theme': 'studio'}
            user.revision = 4
            get_db().commit()
        query = self.start(intent='link', owner=original['user']['id'])
        self.assertEqual(query['prompt'], ['select_account'])
        before_cookie = self.client.get_cookie('lexi_session').value
        data, _ = self.google_callback(query)
        self.assertEqual(data['user']['id'], original['user']['id'])
        self.assertEqual(data['state']['saved'], ['law-equity'])
        self.assertEqual(data['revision'], 4)
        self.assertEqual(data['user']['linkedProviders'], ['google'])
        self.assertFalse(any(value.startswith('lexi_session=') for value in self.last_callback.headers.getlist('Set-Cookie')))
        self.assertEqual(self.client.get_cookie('lexi_session').value, before_cookie)
        with self.app.app_context():
            self.assertEqual(get_db().get(User, original['user']['id']).password_hash, before)

    def test_github_uses_verified_private_email_and_stable_numeric_id(self):
        query = self.start('github')
        profile = Mock();profile.json.return_value = {'id': 1234, 'login': 'Ada-GH', 'email': None}
        emails = Mock();emails.json.return_value = [{'email': 'unverified@example.com', 'verified': False, 'primary': True}, {'email': 'private@example.com', 'verified': True, 'primary': False}]
        with patch.object(self.github, 'authorize_access_token', return_value={'access_token': 'private-token', 'token_type': 'Bearer'}), patch.object(self.github, 'get', side_effect=[profile, emails]) as get:
            self.client.get('/api/account/oauth/github/callback', query_string={'state': query['state'][0], 'code': 'github-code'})
        data = self.session()
        self.assertEqual(data['user']['email'], 'private@example.com')
        self.assertEqual(data['user']['linkedProviders'], ['github'])
        self.assertEqual([call.args[0] for call in get.call_args_list], ['user', 'user/emails'])
        with self.app.app_context():
            self.assertEqual(get_db().scalar(select(OAuthIdentity)).subject, '1234')

    def test_github_unverified_email_and_unknown_providers_fail_closed(self):
        self.assertEqual(self.client.post('/api/account/oauth/unknown/start', json={'intent': 'signin'}, headers={'X-CSRF-Token': self.session()['csrfToken']}).status_code, 404)
        query = self.start('github')
        response = Mock();response.json.return_value = {'id': 1234, 'login': 'Ada'}
        emails = Mock();emails.json.return_value = [{'email': 'ada@example.com', 'verified': False}]
        with patch.object(self.github, 'authorize_access_token', return_value={'access_token': 'private-token'}), patch.object(self.github, 'get', side_effect=[response, emails]):
            self.client.get('/api/account/oauth/github/callback', query_string={'state': query['state'][0], 'code': 'code'})
        self.assertIsNone(self.session()['user'])
        self.assertEqual(self.counts(), (0, 0))

    def test_github_real_client_exchanges_code_with_secret_and_pkce_on_server_only(self):
        query = self.start('github')
        sent = []
        def send(prepared, **kwargs):
            sent.append(prepared)
            if prepared.url == 'https://github.com/login/oauth/access_token':
                body = {'access_token': 'transport-test-token', 'token_type': 'bearer'}
            elif prepared.url == 'https://api.github.com/user':
                body = {'id': 5678, 'login': 'Transport_user'}
            elif prepared.url == 'https://api.github.com/user/emails':
                body = [{'email': 'transport@example.com', 'verified': True, 'primary': True}]
            else:
                self.fail('Unexpected provider endpoint')
            response = Response();response.status_code = 200
            response._content = json.dumps(body).encode()
            response.headers['Content-Type'] = 'application/json';response.url = prepared.url;response.request = prepared
            return response
        with patch('requests.sessions.Session.send', side_effect=send):
            result = self.client.get('/api/account/oauth/github/callback', query_string={'state': query['state'][0], 'code': 'github-code'})
        self.assertEqual(result.status_code, 303)
        self.assertEqual(self.session()['user']['email'], 'transport@example.com')
        token_request = sent[0]
        body = parse_qs(token_request.body.decode() if isinstance(token_request.body, bytes) else token_request.body)
        self.assertEqual(body['client_secret'], ['github-test-secret'])
        self.assertEqual(body['client_id'], ['github-test-client'])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'][0].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(query['code_challenge'], [challenge])
        self.assertNotIn('github-test-secret', token_request.url)
        self.assertEqual(sent[1].headers['Authorization'], 'Bearer transport-test-token')

    def test_link_cannot_move_an_identity_between_accounts(self):
        first, _ = self.google_callback(self.start())
        self.logout()
        response = self.client.post('/api/account/register', json={'username': 'Other_user', 'email': 'other@example.com', 'password': 'Other-password-42'}, headers={'X-CSRF-Token': self.session()['csrfToken']})
        second = response.json
        data, _ = self.google_callback(self.start(intent='link', owner=second['user']['id']))
        self.assertEqual(data['user']['id'], second['user']['id'])
        self.assertIn('another account', data['oauthNotice']['message'])
        self.assertEqual(self.counts(), (2, 1))
        with self.app.app_context():
            self.assertEqual(get_db().scalar(select(OAuthIdentity)).user_id, first['user']['id'])

    def test_link_never_replaces_an_existing_provider_identity(self):
        first, _ = self.google_callback(self.start())
        data, _ = self.google_callback(self.start(intent='link', owner=first['user']['id']), {'sub': 'different-subject', 'email': 'different@example.com'})
        self.assertEqual(data['user']['id'], first['user']['id'])
        self.assertIn('already connected', data['oauthNotice']['message'])
        self.assertEqual(self.counts(), (1, 1))

    def test_session_change_during_link_aborts_before_token_exchange(self):
        account = self.password_account()
        query = self.start(intent='link', owner=account['user']['id'])
        self.logout()
        with patch.object(self.google, 'fetch_access_token') as exchange:
            self.client.get('/api/account/oauth/google/callback', query_string={'state': query['state'][0], 'code': 'stale'})
            exchange.assert_not_called()
        self.assertEqual(self.counts(), (1, 0))

    def test_start_does_not_rewrite_the_login_cookie(self):
        self.password_account()
        data = self.session()
        before = self.client.get_cookie('lexi_session').value
        response = self.client.post('/api/account/oauth/google/start', json={'intent': 'link'}, headers={'X-CSRF-Token': data['csrfToken'], 'X-Account-Id': str(data['user']['id'])})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.headers.getlist('Set-Cookie'))
        self.assertEqual(self.client.get_cookie('lexi_session').value, before)
        with self.client.session_transaction() as cookie:
            self.assertFalse(any(key.startswith(('_state_', '_lexi_oauth_')) for key in cookie))

    def test_public_origin_configuration_and_cookie_security(self):
        self.assertTrue(self.app.config['SESSION_COOKIE_SECURE'])
        for origin in ('http://public.example', 'https://user:password@example.com', 'https://lexi.example/path', 'https://lexi.example?next=evil'):
            with self.subTest(origin=origin), self.assertRaises(RuntimeError):
                create_app({'TESTING': True, 'LEXI_PUBLIC_URL': origin, 'GOOGLE_CLIENT_ID': 'enabled', 'GOOGLE_CLIENT_SECRET': 'secret'})


if __name__ == '__main__':
    unittest.main()
