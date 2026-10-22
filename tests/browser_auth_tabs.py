"""Auth tab motion, interrupted transitions and memory-only form drafts.

Start LEXI with a disposable database, then run python3 tests/browser_auth_tabs.py.
No account is created; the guest session uses the real API.
"""
import os
import shutil

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('LEXI_TEST_URL', 'http://127.0.0.1:5000').rstrip('/')
checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)
    print('PASS', label, flush=True)


def switch(page, mode):
    page.locator(f'.account-tabs [data-account-action="{mode}-tab"]').click()


def settled(page):
    page.wait_for_function("()=>!document.querySelector('.auth-switching')")


def values(page):
    return page.locator('#account-auth-form').evaluate('(form)=>Object.fromEntries(new FormData(form))')


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Bishkek')
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url) if request.method != 'GET' else None)
        page.goto(BASE, wait_until='networkidle')
        registration = {'username': 'Draft_user', 'email': 'draft@example.com', 'password': 'Draft-password-42'}
        login = {'identifier': 'different@example.com', 'password': 'Other-password-42'}
        for name, value in registration.items():
            page.locator(f'input[name="{name}"]').fill(value)
        old_height = page.locator('#auth-entry').evaluate('(e)=>e.getBoundingClientRect().height')
        switch(page, 'login')
        check(page.locator('#auth-entry').evaluate('(e)=>e.getAnimations({subtree:true}).length') >= 3, 'Tab switch animates the form, card height and active underline')
        check(page.locator('#auth-entry').evaluate("""e=>{
          const height=e.getAnimations()[0],time=height.currentTime;
          const frames=height.effect.getKeyframes(),from=parseFloat(frames[0].height),to=parseFloat(frames[1].height);
          height.currentTime=100;const middle=e.getBoundingClientRect().height;height.currentTime=time;
          return middle<Math.max(from,to)&&middle>Math.min(from,to);
        }"""), 'An intermediate frame has a real height between registration and sign-in')
        check(values(page) == {'identifier': '', 'password': ''}, 'Sign-in has its own blank fields instead of copying registration credentials')
        expect(page.locator('[data-account-action="login-tab"]')).to_be_focused()
        settled(page)
        check(page.locator('#auth-entry').evaluate('(e)=>e.getBoundingClientRect().height') < old_height, 'Card smoothly settles to the shorter sign-in form')
        for name, value in login.items():
            page.locator(f'input[name="{name}"]').fill(value)
        switch(page, 'register')
        check(values(page) == registration, 'Accidental Sign in preserves the registration draft when returning')
        settled(page)
        for theme in ('noir', 'studio', 'experimental'):
            page.locator(f'[data-entry-theme-choice="{theme}"]').click()
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                for mode, expected in (('login', login), ('register', registration)):
                    switch(page, mode)
                    check(values(page) == expected, f'{theme} / {width}px / {mode}: independent draft survives switching')
                    settled(page)
                check(page.evaluate("document.documentElement.scrollWidth<=innerWidth && (()=>{const a=document.querySelector('.account-tabs>button[aria-pressed=true]').getBoundingClientRect(),i=document.querySelector('.account-tab-indicator').getBoundingClientRect();return Math.abs(a.x-i.x)<1&&Math.abs(a.width-i.width)<1;})()"), f'{theme} / {width}px: no overflow and underline matches the active tab')
        page.evaluate("()=>{for(let i=0;i<9;i++)document.querySelector('[data-account-action=\"'+(i%2?'register':'login')+'-tab\"]').click();}")
        settled(page)
        check(values(page) == login and page.locator('#auth-entry').evaluate('(e)=>!e.style.height && e.getAnimations({subtree:true}).length===0'), 'Rapid repeated switching settles to the final tab without stuck height or animations')
        switch(page, 'login')
        check(values(page) == login and page.locator('#auth-entry').evaluate('(e)=>e.getAnimations({subtree:true}).length===0'), 'Clicking the already selected tab keeps its fields and does not restart motion')
        page.emulate_media(reduced_motion='reduce')
        switch(page, 'register')
        check(values(page) == registration and page.locator('#auth-entry').evaluate('(e)=>e.getAnimations({subtree:true}).length===0'), 'Device reduced motion changes tabs immediately and preserves the draft')
        page.emulate_media(reduced_motion='no-preference')
        page.evaluate("document.documentElement.classList.add('reduce-motion')")
        switch(page, 'login')
        check(page.locator('#auth-entry').evaluate('(e)=>e.getAnimations({subtree:true}).length===0'), 'LEXI reduced motion also disables auth transitions')
        page.evaluate("document.documentElement.classList.remove('reduce-motion')")
        switch(page, 'register')
        page.emulate_media(reduced_motion='reduce')
        page.wait_for_function("()=>matchMedia('(prefers-reduced-motion: reduce)').matches&&!document.querySelector('.auth-switching')", timeout=200)
        check(page.locator('.auth-switching').count() == 0, 'Enabling reduced motion during a transition cancels the running animation')
        page.emulate_media(reduced_motion='no-preference')
        persisted = page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
        check(all(value not in persisted for value in [*registration.values(), *login.values()]), 'No draft username, email, identifier or password is written to browser storage')
        check(not requests, 'Switching tabs never submits credentials or starts an account request')
        page.locator('[data-account-action="guest"]').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        page.locator('input[name="onboarding"][value="ielts"]').check()
        page.locator('#begin-button').click()
        page.locator('#account-button').click()
        page.locator('#account-dialog [data-account-action="register-tab"]').click()
        check(values(page) == {'username': '', 'email': '', 'password': ''}, 'Entering guest mode discards drafts from the entry screen')
        for name, value in registration.items():
            page.locator(f'input[name="{name}"]').fill(value)
        switch(page, 'login');switch(page, 'register');settled(page)
        check(values(page) == registration, 'The guest account dialog supports the same reversible tab switch')
        page.keyboard.press('Escape')
        expect(page.locator('#account-dialog')).not_to_be_visible()
        page.locator('#account-button').click()
        page.locator('#account-dialog [data-account-action="register-tab"]').click()
        check(values(page) == {'username': '', 'email': '', 'password': ''}, 'Closing the account dialog discards its credential drafts')
        page.locator('#account-dialog [data-account-action="close"]').click()
        page.locator('#guest-banner [data-account-action="guest-exit"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        settled(page)
        check(values(page) == {'identifier': '', 'password': ''}, 'Guest exit restores a blank sign-in form')
        switch(page, 'register');settled(page)
        check(values(page) == {'username': '', 'email': '', 'password': ''}, 'No registration draft leaks into the next visit')
        page.locator('input[name="username"]').fill(registration['username'])
        page.reload(wait_until='networkidle')
        check(values(page) == {'username': '', 'email': '', 'password': ''}, 'Reloading starts with a fresh form instead of persisting credentials')
        check(not errors, 'Tab transitions and account lifecycle produce no uncaught JavaScript errors')
        browser.close()
    print(f'All {len(checks)} auth tab browser checks passed.', flush=True)


if __name__ == '__main__':
    run()
