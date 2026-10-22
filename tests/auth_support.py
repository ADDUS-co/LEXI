"""Synthetic accounts for tests; never disables the application's access checks."""
import secrets


def choose_guide_language(page, language='en'):
    if page.locator('#onboarding-language').is_visible():
        page.locator(f'[data-guide-language="{language}"]').click()


def advance_guide_time(page):
    if page.locator('#onboarding-next').is_visible():
        page.locator('#onboarding-next').click()


def finish_onboarding(page):
    from playwright.sync_api import expect
    page.locator('#begin-button').click()
    guided = page.evaluate("async()=>{const s=(await import('/static/js/storage.js')).readStore();return s.guideStep==='settings'&&!!s.guideLanguage;}")
    if guided:
        expect(page.locator('#settings-guide-dialog')).to_be_visible()
        page.locator('#guide-settings-done').click()
        expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
        page.locator('#guide-settings-done').click()
        expect(page.locator('#settings-guide-dialog')).not_to_be_visible()


def signed_in_client(app):
    client = app.test_client()
    token = client.get('/api/account/session').json['csrfToken']
    response = client.post('/api/account/register', json={
        'username': 'Api_fixture', 'email': 'fixture@example.com', 'password': 'Fixture-password-42',
    }, headers={'X-CSRF-Token': token})
    assert response.status_code == 201, response.json
    return client


class BrowserAccount:
    """One real account per script; reuse its cookie across isolated test contexts."""
    def __init__(self, playwright, base):
        self.api = playwright.request.new_context(base_url=base)
        token = self.api.get('/api/account/session').json()['csrfToken']
        self.username = 'Browser_' + secrets.token_hex(5)
        response = self.api.post('/api/account/register', data={
            'username': self.username, 'email': self.username.lower() + '@example.com',
            'password': 'Fixture-password-42',
        }, headers={'X-CSRF-Token': token})
        assert response.status == 201, response.json()
        self.account = response.json()
        response = self.api.get('/api/catalog')
        assert response.status == 200
        self.catalog = response.json()

    def authenticate(self, context, state=None):
        session = self.api.get('/api/account/session').json()
        state = {'version': 2, 'theme': 'noir', 'interests': [], 'saved': [], 'history': [],
                 'hiddenWords': [], 'updateTime': '08:00', 'onboarded': False,
                 'reduceMotion': False, 'guideLanguage': None, 'guideStep':'done' if (state or {}).get('onboarded') else 'language', **(state or {})}
        response = self.api.put('/api/account/state', data={'state': state, 'revision': session['revision'], 'progressVersion': session['progressVersion']}, headers={
            'X-CSRF-Token': session['csrfToken'], 'X-Account-Id': str(session['user']['id']),
        })
        assert response.status == 200, response.json()
        context.add_cookies(self.api.storage_state()['cookies'])

    def dispose(self):
        self.api.dispose()
