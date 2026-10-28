"""Disposable localhost OAuth fixture: fake keys, temporary DB, local discovery."""
import os
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
        google = app.extensions['lexi_oauth'].create_client('google')
        google.server_metadata.update(
            issuer='https://accounts.google.com',
            authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',
            token_endpoint='https://oauth2.googleapis.com/token',
            id_token_signing_alg_values_supported=['RS256'], _loaded_at=time.time(),
        )
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    run()
