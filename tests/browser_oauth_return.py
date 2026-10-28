"""Exercise real callback/session/UI after simulated Google Continue, locally only."""
import html
import os
import secrets
import shutil
from urllib.parse import parse_qs, urlencode, urlsplit

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('LEXI_TEST_URL', 'http://127.0.0.1:5010').rstrip('/')
checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)
    print('PASS', label, flush=True)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox'])
        for width, height, workers in ((390, 844, 'allow'), (1440, 1000, 'block')):
            context = browser.new_context(viewport={'width': width, 'height': height}, service_workers=workers, reduced_motion='reduce')
            page = context.new_page()
            errors = [];password_requests = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: password_requests.append(request.url) if request.method == 'POST' and urlsplit(request.url).path in ('/api/account/login', '/api/account/register') else None)
            email = 'oauth-browser-'+secrets.token_hex(5)+'@example.com'

            def consent(route):
                query = parse_qs(urlsplit(route.request.url).query)
                target = BASE+'/__test/oauth/google/continue?'+urlencode({
                    'state': query['state'][0], 'nonce': query['nonce'][0],
                    'challenge': query['code_challenge'][0], 'email': email,
                })
                route.fulfill(content_type='text/html', body='<a href="'+html.escape(target, quote=True)+'">Continue</a>')

            page.route('https://accounts.google.com/o/oauth2/v2/auth**', consent)
            page.goto(BASE+'/auth/complete', wait_until='networkidle')
            expect(page.locator('#account-error')).to_contain_text('could not finish your sign-in')
            expect(page.locator('#auth-screen')).to_be_visible()
            expect(page.locator('#learning-app')).not_to_be_visible()
            check(context.request.get(BASE+'/api/account/session').json()['user'] is None, f'{width}px: visiting the completion page alone cannot sign in or expose the app')
            page.goto(BASE, wait_until='networkidle')
            page.get_by_role('button', name='Continue with Google', exact=True).click()
            page.get_by_role('link', name='Continue', exact=True).click()
            page.wait_for_url(BASE+'/**', wait_until='networkidle')
            expect(page.locator('#auth-screen')).to_be_hidden()
            expect(page.locator('#learning-app')).to_be_visible()
            expect(page.locator('#onboarding-language')).to_be_visible()
            data = context.request.get(BASE+'/api/account/session').json()
            check(data['user']['email'] == email and data['user']['linkedProviders'] == ['google'], f'{width}px: Continue establishes a real signed-in session and starts new-user onboarding')
            original_id = data['user']['id']
            catalog = context.request.get(BASE+'/api/catalog').json()
            word = catalog['words'][0]['id']
            state = {'version': 2, 'theme': 'studio', 'interests': ['ielts'], 'saved': [word],
                     'history': [], 'hiddenWords': [], 'updateTime': '08:00', 'onboarded': True,
                     'reduceMotion': True, 'guideLanguage': 'en', 'guideStep': 'done'}
            response = context.request.put(BASE+'/api/account/state', data={'state': state, 'revision': data['revision'], 'progressVersion': data['progressVersion']}, headers={'X-CSRF-Token': data['csrfToken'], 'X-Account-Id': str(original_id)})
            check(response.status == 200, f'{width}px: OAuth account can save its own progress')
            page.reload(wait_until='networkidle')
            page.locator('#account-button').click()
            page.get_by_role('button', name='Sign out', exact=True).click()
            expect(page.locator('#auth-screen')).to_be_visible()
            session_reads = []

            def old_session_once(route):
                response = route.fetch();data = response.json()
                if page.url.startswith(BASE+'/auth/complete'):
                    session_reads.append(data['user'])
                    if len(session_reads) == 1:
                        data.update(user=None, guestId=None, state=None)
                route.fulfill(response=response, json=data)

            page.route('**/api/account/session', old_session_once)
            page.get_by_role('button', name='Continue with Google', exact=True).click()
            page.get_by_role('link', name='Continue', exact=True).click()
            page.wait_for_url(BASE+'/**', wait_until='networkidle')
            expect(page.locator('#auth-screen')).to_be_hidden()
            expect(page.locator('#learning-app')).to_be_visible()
            expect(page.locator('#onboarding-dialog')).not_to_be_visible()
            data = context.request.get(BASE+'/api/account/session').json()
            check(data['user']['id'] == original_id and data['state']['saved'] == [word], f'{width}px: returning Google user goes directly to the same profile with saved progress')
            check(len(session_reads) >= 2 and all(user and user['id'] == original_id for user in session_reads), f'{width}px: one delayed session read is retried automatically after Continue')
            check(urlsplit(page.url).path == '/' and not page.locator('#oauth-completing').is_visible(), f'{width}px: completed sign-in removes the progress screen and returns to Home')
            check(not password_requests, f'{width}px: neither Google Continue requires a LEXI password or another Sign in submission')
            check(not errors, f'{width}px: no browser errors during complete Google sign-in')
            context.close()
        browser.close()
    print(f'All {len(checks)} Google return checks passed.', flush=True)


if __name__ == '__main__':
    run()
