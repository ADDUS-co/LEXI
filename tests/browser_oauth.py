"""OAuth entry/link UI; outbound provider navigation is intercepted, never completed.

Run against a disposable server with both providers configured with test keys.
Creates one synthetic password account. No real provider account is used.
"""
import os
from pathlib import Path
import shutil
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright, expect
from auth_support import BrowserAccount

BASE=os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5010').rstrip('/')
OUTPUT=Path(__file__).resolve().parents[1]/'test-results'
OUTPUT.mkdir(exist_ok=True)
checks=[]


def check(value,label):
    if not value:raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)


def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        errors=[];posts=[]
        context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce',service_workers='block')
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:posts.append(r) if '/api/account/oauth/' in r.url else None)
        page.goto(BASE,wait_until='networkidle')
        expect(page.get_by_role('button',name='Continue with Google',exact=True)).to_be_enabled()
        for theme in ('studio','noir','experimental'):
            page.locator(f'[data-entry-theme-choice="{theme}"]').click()
            for width,height in ((320,568),(390,844),(768,1024),(1440,1000),(844,390)):
                page.set_viewport_size({'width':width,'height':height})
                positions=[]
                for view in ('register','login'):
                    page.locator(f'[data-account-action="{view}-tab"]').click()
                    page.wait_for_timeout(40)
                    positions.append(page.locator('.account-tabs').bounding_box()['y'])
                    valid=page.evaluate('''()=>{
                      const card=document.querySelector('#auth-entry').getBoundingClientRect();
                      return document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('.oauth-button')].every(e=>{const r=e.getBoundingClientRect();return r.height>=44&&r.left>=card.left&&r.right<=card.right;});
                    }''')
                    check(valid,f'{theme}/{width}x{height}/{view}: provider buttons fit and remain touch-sized')
                check(abs(positions[0]-positions[1])<1,f'{theme}/{width}px: Sign in/Create account tabs keep their height')
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('[data-entry-theme-choice="studio"]').click()
        page.locator('[data-account-action="register-tab"]').click()
        page.screenshot(path=str(OUTPUT/'oauth-entry-desktop.png'))
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUTPUT/'oauth-entry-mobile.png'),full_page=True)
        fields={'username':'Draft_oauth','email':'invalid-email','password':'Draft-password-42'}
        for name,value in fields.items():page.locator(f'input[name="{name}"]').fill(value)
        page.route('**/api/account/oauth/google/start',lambda route:route.fulfill(status=503,json={'error':'Google could not be reached. Please try again.'}))
        page.get_by_role('button',name='Continue with Google',exact=True).click()
        expect(page.locator('#account-error')).to_contain_text('not responding yet')
        check(all(page.locator(f'input[name="{name}"]').input_value()==value for name,value in fields.items()),'A provider failure preserves every field and restores the form')
        check(posts[-1].post_data_json=={'intent':'signin'} and bool(posts[-1].headers.get('x-csrf-token')),'OAuth starts without sending the draft email/password and includes CSRF protection')
        context.set_offline(True)
        expect(page.get_by_role('button',name='Continue with GitHub',exact=True)).to_be_disabled()
        check(True,'Provider login is unavailable while offline')
        context.set_offline(False)
        expect(page.get_by_role('button',name='Continue with GitHub',exact=True)).to_be_enabled()
        page.route('https://github.com/login/oauth/authorize**',lambda route:route.fulfill(content_type='text/html',body='Provider navigation intercepted for this test.'))
        page.get_by_role('button',name='Continue with GitHub',exact=True).click()
        page.wait_for_url('https://github.com/login/oauth/authorize**')
        query=parse_qs(urlsplit(page.url).query)
        check(query['code_challenge_method']==['S256'] and 'client_secret' not in query,'GitHub navigation uses the real backend state/PKCE URL without exposing a client secret')
        check(posts[-1].post_data_json=={'intent':'signin'},'Incomplete email fields do not block provider registration or submit the password form')
        page.go_back(wait_until='networkidle')
        expect(page.get_by_role('button',name='Continue with GitHub',exact=True)).to_be_enabled()
        check(page.locator('input[name="password"]').input_value()=='','Back from a provider restores usable controls without a password draft')
        context.close()

        context=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce',service_workers='block')
        word=fixture.catalog['words'][0]['id']
        fixture.authenticate(context,{'onboarded':True,'guideStep':'done','interests':['ielts'],'saved':[word],'theme':'studio'})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:posts.append(r) if '/api/account/oauth/' in r.url else None)
        page.goto(BASE,wait_until='networkidle');page.locator('#account-button').click()
        expect(page.get_by_role('button',name='Connect GitHub',exact=True)).to_be_visible()
        check(page.get_by_role('button',name='Connect Google',exact=True).is_visible(),'Existing profiles offer explicit connection of both providers')
        page.route('https://github.com/login/oauth/authorize**',lambda route:route.fulfill(content_type='text/html',body='Provider navigation intercepted for this test.'))
        page.get_by_role('button',name='Connect GitHub',exact=True).click()
        page.wait_for_url('https://github.com/login/oauth/authorize**')
        data=context.request.get(BASE+'/api/account/session').json()
        check(posts[-1].post_data_json=={'intent':'link'} and posts[-1].headers.get('x-account-id')==str(data['user']['id']),'Connecting a provider is bound to the signed-in account')
        check(data['state']['saved']==[word] and data['state']['theme']=='studio','Starting a connection keeps the existing account progress')
        context.close()

        context=browser.new_context(viewport={'width':390,'height':844},service_workers='block',reduced_motion='reduce')
        page=context.new_page()
        def notice(route):
            response=route.fetch();data=response.json()
            data['oauthNotice']={'message':'Sign in with your password, then connect Google in your profile.','signin':True}
            route.fulfill(response=response,json=data)
        page.route('**/api/account/session',notice)
        page.goto(BASE,wait_until='networkidle')
        expect(page.locator('[data-account-action="login-tab"]')).to_have_attribute('aria-pressed','true')
        expect(page.locator('#account-error')).to_contain_text('connect Google')
        check(True,'An existing-email return explains linking and opens Sign in')
        context.close();browser.close();fixture.dispose()
        check(not errors,'No uncaught browser errors during OAuth entry, failure, or connection')
    print(f'All {len(checks)} OAuth browser checks passed.',flush=True)


if __name__=='__main__':run()
