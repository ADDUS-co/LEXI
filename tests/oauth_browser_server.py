"""Disposable localhost OAuth fixture: fake keys, temporary DB, local discovery."""
import os
import base64
import hashlib
from pathlib import Path
import secrets
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    port = int(os.environ.get('LEXI_OAUTH_TEST_PORT', '5010'))
    with tempfile.TemporaryDirectory(prefix='lexi-oauth-browser-') as directory:
        # Override inherited credentials; this fixture must never use real accounts.
        os.environ.update(
            DATABASE_URL='sqlite:///'+str(Path(directory)/'accounts.sqlite3'),
            SECRET_KEY=secrets.token_hex(32), LEXI_PUBLIC_URL=f'http://127.0.0.1:{port}',
            GOOGLE_CLIENT_ID='google-test-client', GOOGLE_CLIENT_SECRET='google-test-secret',
            GITHUB_CLIENT_ID='github-test-client', GITHUB_CLIENT_SECRET='github-test-secret',
            LEXI_COOKIE_SECURE='0', LEXI_TRUST_PROXY='0',
        )
        from app import app
        from flask import abort, redirect, request
        from joserfc import jwt
        from joserfc.jwk import RSAKey
        from urllib.parse import urlencode

        signing_key = RSAKey.generate_key(2048, parameters={'kid': 'browser-fixture'})
        codes = {}
        google = app.extensions['lexi_oauth'].create_client('google')
        google.server_metadata.update(
            issuer='https://accounts.google.com',
            authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',
            token_endpoint='https://oauth2.googleapis.com/token',
            id_token_signing_alg_values_supported=['RS256'],
            jwks={'keys': [signing_key.as_dict(private=False)]}, _loaded_at=time.time(),
        )

        # Only this standalone fixture exposes a fake consent result. Production
        # has no test routes or alternate token validation path.
        @app.get('/__test/oauth/google/continue')
        def continue_google():
            values = {key: request.args.get(key, '') for key in ('state', 'nonce', 'challenge', 'email')}
            if not all(values.values()) or not values['email'].endswith('@example.com'):
                abort(400)
            code = secrets.token_urlsafe(32)
            codes[code] = values
            return redirect('/api/account/oauth/google/callback?'+urlencode({'state': values['state'], 'code': code}), code=303)

        def exchange_test_code(**params):
            values = codes.pop(params.get('code'), None)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(params.get('code_verifier', '').encode()).digest()).rstrip(b'=').decode()
            if not values or challenge != values['challenge']:
                raise ValueError('Invalid fixture code or PKCE verifier')
            now = int(time.time())
            claims = {'iss': 'https://accounts.google.com', 'aud': 'google-test-client',
                      'sub': 'fixture:'+values['email'], 'email': values['email'], 'email_verified': True,
                      'name': 'Google learner', 'nonce': values['nonce'], 'iat': now, 'exp': now+120}
            return {'access_token': 'fixture-token-not-for-storage', 'token_type': 'Bearer',
                    'id_token': jwt.encode({'alg': 'RS256', 'kid': 'browser-fixture'}, claims, signing_key)}

        google.fetch_access_token = exchange_test_code
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    run()
