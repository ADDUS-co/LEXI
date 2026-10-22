"""Temporary guest visits and their isolation from persistent accounts.

Run against a disposable DATABASE_URL: creates one synthetic account.
LEXI_TEST_URL=http://127.0.0.1:5011 python3 tests/browser_guest.py
"""
import os
import shutil
import time

from playwright.sync_api import sync_playwright, expect
from auth_support import choose_guide_language, advance_guide_time, finish_onboarding

BASE = os.environ.get('LEXI_TEST_URL', 'http://127.0.0.1:5000').rstrip('/')
checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)
    print('PASS', label, flush=True)


def state(page):
    return page.evaluate("async () => (await import('/static/js/storage.js')).readStore()")


def storage(page):
    return page.evaluate('({local:{...localStorage},session:{...sessionStorage}})')


def fresh(page):
    current = state(page)
    return all(not current[key] for key in ('interests', 'saved', 'history', 'hiddenWords', 'onboarded')) and current['updateTime'] == '08:00'


def enter(page):
    expect(page.locator('#auth-screen')).to_be_visible()
    page.locator('[data-account-action="guest"]').click()
    expect(page.locator('#onboarding-dialog')).to_be_visible()
    expect(page.locator('#guest-banner')).to_be_visible()


def begin(page, collection='ielts', update_time='09:15'):
    choose_guide_language(page)
    page.locator('#onboarding-update-time').fill(update_time)
    advance_guide_time(page)
    page.locator(f'input[name="onboarding"][value="{collection}"]').check()
    finish_onboarding(page)
    expect(page.locator('#onboarding-dialog')).not_to_be_visible()
    page.evaluate("location.hash='home'")
    expect(page.locator('#daily-word')).to_be_visible()


def go(page, route):
    page.evaluate('route=>{location.hash=route}', route)
    expect(page.locator(f'[data-nav="{route}"]')).to_have_attribute('aria-current', 'page')


def wait_synced(page):
    page.wait_for_function("""() => {
      const id=localStorage.getItem('lexi:active-account');
      const meta=JSON.parse(localStorage.getItem('lexi:sync:'+id+':v2')||'null');
      return meta && !meta.dirty;
    }""")


def run():
    with sync_playwright() as p:
        executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
        browser = p.chromium.launch(executable_path=executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='Asia/Bishkek')
        page = context.new_page()
        errors, writes = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' else None)
        page.goto(BASE, wait_until='networkidle')
        check(page.locator('[data-account-action="guest"]').is_visible(), 'Registration offers guest access without filling any fields')
        page.locator('[data-account-action="login-tab"]').click()
        check(page.locator('[data-account-action="guest"]').is_visible(), 'Sign-in also offers guest access')
        check('reload' in page.locator('#guest-help').inner_text(), 'Entry explains the temporary progress before starting')
        initial_storage = storage(page)
        enter(page)
        check(fresh(page), 'First guest starts with empty progress and fresh interests/time')
        check(page.locator('#onboarding-guest-exit').is_visible(), 'Guest can leave before choosing interests')
        page.locator('#onboarding-guest-exit').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        check(fresh(page), 'Leaving onboarding clears guest state')
        enter(page)
        begin(page)
        word = page.locator('[data-action="save"]').first.get_attribute('data-word')
        page.locator('[data-action="save"]').first.click()
        page.locator('.collection-tag').dblclick()
        expect(page.locator('#recall-answer')).to_be_visible()
        check(state(page)['saved'] == [word] and state(page)['hiddenWords'] == [word], 'Guest can save words and flip memory cards during the visit')
        go(page, 'history')
        check(page.locator('.word-card').count() == 1 and word in [item['id'] for item in state(page)['history']], 'Guest history works during navigation')
        go(page, 'settings')
        page.locator('[data-theme-choice="experimental"]').click()
        page.locator('#motion-toggle').check()
        page.locator('#settings-update-time').fill('11:20')
        page.locator('#schedule-form button[type="submit"]').click()
        check(state(page)['theme'] == 'experimental' and state(page)['reduceMotion'] and state(page)['updateTime'] == '11:20', 'Guest appearance, motion and daily rhythm work for the current visit')
        check(storage(page) == initial_storage, 'Guest history, settings and cards never enter localStorage or sessionStorage')
        check(not any('/api/account/state' in url or '/api/account/avatar' in url for url in writes), 'Guest progress is never sent to account storage or photos')
        before = state(page)
        context.set_offline(True)
        context.set_offline(False)
        page.wait_for_timeout(700)
        check(state(page) == before, 'Reconnecting refreshes the session without resetting the active guest visit')
        page.locator('#account-button').click()
        expect(page.locator('#account-dialog')).to_be_visible()
        check('will not be transferred' in page.locator('#account-dialog').inner_text() and page.locator('#profile-photo-form').count() == 0, 'Guest profile explains account isolation and has no photo upload')
        page.locator('#account-dialog [data-account-action="close"]').first.click()
        other = context.new_page()
        other.goto(BASE, wait_until='networkidle')
        expect(other.locator('#onboarding-dialog')).to_be_visible()
        check(fresh(other) and state(page) == before, 'Another guest tab has separate temporary progress')
        begin(other, 'culture', '10:05')
        other.locator('#guest-banner [data-account-action="guest-exit"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        expect(other.locator('#auth-screen')).to_be_visible()
        check(fresh(page) and fresh(other), 'Guest exit clears all open guest tabs through an ephemeral notification')
        check(page.locator('#main-content').inner_html() == '' and other.locator('#main-content').inner_html() == '', 'No previous word or history remains behind the entry screen')
        check(storage(page) == initial_storage, 'Guest exit leaves no persisted progress')
        other.close()
        enter(page)
        check(fresh(page), 'Returning guest chooses interests from scratch')
        begin(page)
        page.locator('[data-action="save"]').first.click()
        page.reload(wait_until='networkidle')
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(fresh(page), 'Reloading cannot restore guest history, saved words or interests')
        begin(page)
        page.locator('[data-action="save"]').first.click()
        page.goto(BASE + '/health')
        page.go_back(wait_until='networkidle')
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(fresh(page), 'Leaving and returning to the page does not revive guest data')
        begin(page)
        page.locator('[data-action="save"]').first.click()
        context.set_offline(True)
        page.locator('#guest-banner [data-account-action="guest-exit"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        check(fresh(page), 'Offline guest exit clears data immediately without needing to sync')
        check(not page.locator('[data-account-action="guest"]').is_enabled(), 'Starting a fresh guest visit requires an online session')
        context.set_offline(False)
        expect(page.locator('[data-account-action="guest"]')).to_be_enabled()
        page.wait_for_function("document.documentElement.dataset.access==='required'")
        check(fresh(page), 'Reconnecting completes guest exit and cannot bring guest data back')
        enter(page)
        begin(page)
        page.locator('[data-action="save"]').first.click()
        page.locator('#account-button').click()
        page.locator('#account-dialog [data-account-action="register-tab"]').click()
        username = 'GuestTest_' + str(time.time_ns())[-12:]
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="email"]').fill(username.lower() + '@example.com')
        page.locator('input[name="password"]').fill('Synthetic-pass-42')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(fresh(page) and not page.locator('#guest-banner').is_visible(), 'Creating an account from guest mode starts a clean account')
        begin(page, 'culture', '10:05')
        account_word = page.locator('[data-action="save"]').first.get_attribute('data-word')
        page.locator('[data-action="save"]').first.click()
        wait_synced(page)
        account_progress = state(page)
        page.locator('#account-button').click()
        page.locator('[data-account-action="logout"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        enter(page)
        check(fresh(page), 'Guest visit after account logout cannot see account progress')
        begin(page, 'law', '13:00')
        page.locator('[data-action="save"]').first.click()
        page.locator('#account-button').click()
        page.locator('#account-dialog [data-account-action="login-tab"]').click()
        page.locator('input[name="identifier"]').fill(username)
        page.locator('input[name="password"]').fill('Synthetic-pass-42')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('[data-profile-owner]')).to_be_visible()
        wait_synced(page)
        check(state(page) == account_progress and state(page)['saved'] == [account_word], 'Signing in restores only the account progress and discards the guest visit')
        check(not page.locator('#guest-banner').is_visible(), 'Account mode removes temporary guest labels')
        page.locator('[data-account-action="logout"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        enter(page)
        begin(page)
        page.locator('[data-action="save"]').first.click()
        page.close()
        page = context.new_page()
        page.goto(BASE, wait_until='networkidle')
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(fresh(page), 'Closing and reopening a tab cannot restore guest progress')
        check(not errors, 'No browser JavaScript errors during guest and account transitions')
        browser.close()
    print(f'All {len(checks)} guest browser checks passed.', flush=True)


if __name__ == '__main__':
    run()
