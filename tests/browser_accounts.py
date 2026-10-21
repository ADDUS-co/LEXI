"""Real browser account, photo and multi-device sync checks.

Use a separate disposable DATABASE_URL on the server. Creates three synthetic users.
Install Playwright separately; start LEXI and run python tests/browser_accounts.py.
"""
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import time

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('LEXI_TEST_URL', 'http://127.0.0.1:5000').rstrip('/')
OUTPUT = Path(__file__).resolve().parents[1] / 'test-results'
OUTPUT.mkdir(exist_ok=True)
checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)
    print('PASS', label, flush=True)


def state(page):
    return page.evaluate("JSON.parse(localStorage.getItem('lexi:account:'+localStorage.getItem('lexi:active-account')+':v2'))")


def synced(page):
    page.wait_for_function("""() => {
      const owner=localStorage.getItem('lexi:active-account');
      const meta=JSON.parse(localStorage.getItem('lexi:sync:'+owner+':v2')||'null');
      return meta && !meta.dirty;
    }""")


def go(page, route):
    page.evaluate('route=>{location.hash=route}', route)
    expect(page.locator(f'[data-nav="{route}"]')).to_have_attribute('aria-current', 'page')


def sign_in(page, identifier, password='Synthetic-pass-42'):
    expect(page.locator('#auth-screen')).to_be_visible()
    page.locator('[data-account-action="login-tab"]').click()
    page.locator('input[name="identifier"]').fill(identifier)
    page.locator('input[name="password"]').fill(password)
    page.locator('#account-auth-form button[type="submit"]').click()
    expect(page.locator('#auth-screen')).not_to_be_visible()
    page.locator('#account-button').click()
    expect(page.locator('[data-profile-owner]')).to_be_visible()


def run():
    words = json.loads((Path(__file__).resolve().parents[1] / 'data/words.json').read_text())
    word_id = next(word['id'] for word in words if word['collectionId'] == 'law')
    legacy = {'version': 2, 'interests': ['law'], 'saved': [word_id], 'hiddenWords': [word_id],
              'history': [{'id': word_id, 'date': '2026-10-21'}], 'theme': 'studio',
              'updateTime': '09:15', 'onboarded': True, 'reduceMotion': False}
    stamp = str(time.time_ns())[-12:]
    username = 'Test_' + stamp
    email = username.lower() + '@example.com'
    with sync_playwright() as p:
        executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
        browser = p.chromium.launch(executable_path=executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        first = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Bishkek')
        second = browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='America/New_York')
        page = first.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script("""(() => {
          if(localStorage.getItem('lexi:isolation-fixture'))return;
          const legacy=""" + json.dumps(legacy) + """;
          localStorage.setItem('lexi:v1',JSON.stringify(legacy));
          for(let id=1;id<=8;id++) {
            for(const version of ['v1','v2']) localStorage.setItem('lexi:account:'+id+':'+version,JSON.stringify(legacy));
            localStorage.setItem('lexi:sync:'+id,JSON.stringify({base:{},dirty:true,revision:0}));
            localStorage.setItem('lexi:sync:'+id+':v2',JSON.stringify({base:{},dirty:true,revision:0,identity:'previous-test-account',progressVersion:2}));
          }
          localStorage.setItem('lexi:isolation-fixture','1');
        })();""")
        requests=[]
        page.on('request', lambda request: requests.append(request.url))
        page.goto(BASE + '/#settings', wait_until='networkidle')
        expect(page.locator('input[name="username"]')).to_be_visible()
        check(not page.locator('#learning-app').is_visible() and page.locator('#learning-app').get_attribute('inert') is not None, 'First visit shows registration and keeps learning hidden and inert')
        check(not any('/api/catalog' in url or '/api/daily' in url for url in requests), 'No vocabulary is requested before signing in')
        for endpoint in ('/api/catalog', '/api/daily'):
            check(first.request.get(BASE+endpoint).status == 401, f'Anonymous requests are blocked by the server: {endpoint}')
        page.keyboard.press('Escape')
        page.evaluate("location.hash='word/" + word_id + "'")
        check(page.locator('#auth-screen').is_visible() and not page.locator('#learning-app').is_visible(), 'Escape and word deep links cannot dismiss registration')
        page.evaluate("location.hash='settings'")
        a=page.locator('.word-track>.word-batch:first-child').evaluate_all('es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y};})')
        page.wait_for_timeout(700)
        b=page.locator('.word-track>.word-batch:first-child').evaluate_all('es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y};})')
        from math import atan2, degrees
        check(all(end['x']<start['x'] and end['y']>start['y'] and abs(degrees(atan2(end['y']-start['y'],end['x']-start['x']))-120)<1 for start,end in zip(a,b)), 'Every stream flows in parallel from upper right to lower left, 60 degrees below horizontal')
        check(page.locator('.word-batch:first-child').evaluate_all('es=>es.every(e=>{const words=[...e.children].map(w=>w.textContent);return words.length>=12&&new Set(words).size===words.length&&words.every(w=>/^[a-z]+$/.test(w));})'), 'Each complete repeating stream contains varied English words')
        check(float(page.locator('.word-stream').first.evaluate('e=>getComputedStyle(e).opacity'))>=0.4 and float(page.locator('.word-stream').first.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'))>=48, 'Background words are large and clearly visible')
        page.locator('input[name="username"]').fill('Draft_name')
        colors=[]
        for theme in ('noir','studio','experimental'):
            page.locator(f'[data-entry-theme-choice="{theme}"]').click()
            expect(page.locator('html')).to_have_attribute('data-entry-theme',theme)
            expect(page.locator(f'[data-entry-theme-choice="{theme}"]')).to_have_attribute('aria-pressed','true')
            check(page.locator('input[name="username"]').input_value()=='Draft_name',f'{theme}: switching entry themes preserves typed registration fields')
            colors.append(page.locator('.auth-drift').evaluate('e=>getComputedStyle(e).backgroundColor'))
            box=page.locator('#auth-entry').bounding_box()
            check(abs(box['x']+box['width']/2-720)<1 and abs(box['y']+box['height']/2-500)<12,f'{theme}: the registration form is centered horizontally and vertically')
        check(len(set(colors))==3,'Noir, Studio and Experimental have distinct entry palettes')
        page.reload(wait_until='networkidle')
        check(page.locator('html').get_attribute('data-entry-theme')=='experimental','Entry appearance survives a reload')
        page.locator('[data-entry-theme-choice="studio"]').click()
        page.locator('#entry-motion-toggle').click()
        before=page.locator('.word-track').first.evaluate('e=>getComputedStyle(e).transform')
        page.wait_for_timeout(300)
        check(before==page.locator('.word-track').first.evaluate('e=>getComputedStyle(e).transform'), 'Background animation can be paused')
        page.evaluate('''()=>{for(const e of document.querySelectorAll('.word-track')){
          const a=e.getAnimations()[0];e._resumeTime=a.currentTime;
          const t=a.effect.getTiming();a.currentTime=t.delay+t.duration-0.5;
        }}''')
        last=Image.open(BytesIO(page.screenshot(caret='hide'))).convert('RGB')
        page.evaluate("()=>{for(const e of document.querySelectorAll('.word-track')){const a=e.getAnimations()[0];a.currentTime=a.effect.getTiming().delay;}}")
        first_frame=Image.open(BytesIO(page.screenshot(caret='hide'))).convert('RGB')
        difference=ImageChops.difference(last,first_frame)
        red,green,blue=difference.split()
        histogram=ImageChops.lighter(ImageChops.lighter(red,green),blue).histogram()
        pixels=last.width*last.height
        # Adjacent phases retain fractional-pixel text antialiasing. A shifted
        # or missing sequence changes many pixels, rather than a few edge pixels.
        check(sum(level*count for level,count in enumerate(histogram))/pixels<0.1 and sum(histogram[33:])<pixels/10000, 'The last and first loop frames join without a visible jump')
        page.evaluate("()=>{for(const e of document.querySelectorAll('.word-track')){e.getAnimations()[0].currentTime=e._resumeTime;delete e._resumeTime;}}")
        page.locator('#entry-motion-toggle').click()
        page.emulate_media(reduced_motion='reduce')
        check(page.locator('.word-track').first.evaluate('e=>getComputedStyle(e).animationName')=='none', 'Reduced-motion devices receive a static background')
        page.emulate_media(reduced_motion='no-preference')
        for width in (320,390,768,1440):
            page.set_viewport_size({'width':width,'height':1000})
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Registration has no horizontal overflow at {width}px')
            box=page.locator('#auth-entry').bounding_box()
            check(abs(box['x']+box['width']/2-width/2)<1,f'Registration remains horizontally centered at {width}px')
        page.screenshot(path=str(OUTPUT/'entry-registration-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUTPUT/'entry-registration-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.evaluate('navigator.serviceWorker.ready')
        page.wait_for_function('navigator.serviceWorker.controller!==null')
        cache_urls=page.evaluate("async()=>{const out=[];for(const key of await caches.keys())for(const r of await(await caches.open(key)).keys())out.push(r.url);return out;}")
        check(not any('/api/catalog' in url for url in cache_urls), 'Offline shell installs without fetching the protected catalog')
        for field, value in {'username': username, 'email': email, 'password': 'Synthetic-pass-42'}.items():
            page.locator(f'input[name="{field}"]').fill(value)
        check(page.locator('input[name="importLocal"]').count()==0,'Registration never offers to import old browser history')
        page.locator('[data-account-action="password"]').click()
        expect(page.locator('input[name="password"]')).to_have_attribute('type', 'text')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(state(page)['history']==[] and state(page)['saved']==[] and state(page)['hiddenWords']==[], 'A new account ignores old guest history and dirty caches from previous accounts')
        check(state(page)['interests']==[] and not state(page)['onboarded'], 'A new account must choose its own interests')
        check(state(page)['updateTime']=='08:00', 'A new account starts with a fresh daily schedule')
        page.locator('input[name="onboarding"][value="ielts"]').check()
        page.locator('#onboarding-update-time').fill('09:15')
        page.evaluate("location.hash='home'")
        page.locator('#begin-button').click()
        expect(page.locator('#daily-word')).to_be_visible()
        word_id=state(page)['history'][0]['id']
        page.locator('[data-action="save"]').first.click()
        page.locator('#daily-word').dblclick()
        expect(page.locator('#recall-form')).to_be_visible()
        page.locator('#account-button').click()
        expect(page.locator('[data-profile-owner]')).to_be_visible()
        catalog=first.request.get(BASE+'/api/catalog').json()
        synced(page)
        check(state(page)['saved']==[word_id] and state(page)['hiddenWords']==[word_id], 'Only this account’s own saved word and memory card are stored')
        check(state(page)['theme']=='studio' and state(page)['updateTime']=='09:15', 'This account saves its own appearance and schedule')
        check(page.locator('[data-account-action="import"]').count()==0,'The profile has no action that copies another browser profile')
        account_id = page.locator('[data-profile-owner]').get_attribute('data-profile-owner')
        check(page.evaluate("!Object.entries(localStorage).some(([k,v])=>v.includes('Synthetic-pass-42')||v.includes('csrfToken'))"), 'Passwords and CSRF tokens never enter localStorage')

        image = BytesIO()
        Image.new('RGB', (800, 600), '#a8bc7c').save(image, format='PNG')
        page.locator('#profile-photo-input').set_input_files({'name': 'portrait.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})
        expect(page.locator('#profile-photo-preview')).to_have_attribute('src', re.compile('^blob:'))
        page.locator('#profile-photo-form button[type="submit"]').click()
        expect(page.locator('#profile-photo-preview')).to_have_attribute('src', '/api/account/avatar?v=1')
        check(page.locator('#profile-photo-preview').evaluate('img=>img.complete&&img.naturalWidth===384'), 'Photo upload is resized and displayed from the private database endpoint')
        page.screenshot(path=str(OUTPUT / 'account-studio-desktop.png'), full_page=True)
        page.locator('[data-account-action="close"]').first.click()
        page.reload(wait_until='networkidle')
        check(page.locator('#account-button img').count() == 1, 'Session and profile photo survive a reload')
        synced(page)

        mobile = second.new_page()
        mobile.on('pageerror', lambda error: errors.append(str(error)))
        mobile.goto(BASE, wait_until='networkidle')
        sign_in(mobile, email.upper())
        expect(mobile.locator('[data-profile-owner]')).to_have_attribute('data-profile-owner', account_id)
        check(state(mobile)['saved'] == [word_id], 'A second device receives saved words after email login')
        check(state(mobile)['hiddenWords'] == state(page)['hiddenWords'], 'Hidden cards sync to a second device')
        check(state(mobile)['theme'] == 'studio' and state(mobile)['updateTime'] == '09:15', 'Appearance and local update time sync across device timezones')
        check(mobile.locator('#account-button img').count() == 1, 'A second device receives the account photo')
        for width in (320, 390, 768, 1440):
            mobile.set_viewport_size({'width': width, 'height': 900})
            check(mobile.evaluate('document.documentElement.scrollWidth<=innerWidth') and mobile.locator('#account-dialog').evaluate('e=>e.scrollWidth<=e.clientWidth'), f'Profile has no page or dialog overflow at {width}px')
        mobile.set_viewport_size({'width': 390, 'height': 844})
        mobile.screenshot(path=str(OUTPUT / 'account-studio-mobile.png'), full_page=True)
        mobile.locator('[data-account-action="close"]').first.click()
        go(mobile, 'settings')
        mobile.locator('[data-theme-choice="experimental"]').click()
        synced(mobile)
        page.reload(wait_until='networkidle')
        check(state(page)['theme'] == 'experimental', 'A setting changed on the second device arrives on the first')

        # Concurrent edits, including removals, must preserve independent changes.
        next_id = next(word['id'] for word in catalog['words'] if word['id'] != word_id)
        first.set_offline(True)
        second.set_offline(True)
        page.evaluate("async id=>{const s=await import('/static/js/storage.js');s.updateStore({saved:[],reduceMotion:true});}", word_id)
        mobile.evaluate("async id=>{const s=await import('/static/js/storage.js');s.updateStore({saved:[...s.readStore().saved,id],updateTime:'10:30'});}", next_id)
        check(page.evaluate("JSON.parse(localStorage.getItem('lexi:sync:'+localStorage.getItem('lexi:active-account')+':v2')).dirty"), 'Offline changes remain queued in persistent account storage')
        first.set_offline(False)
        synced(page)
        second.set_offline(False)
        synced(mobile)
        page.reload(wait_until='networkidle')
        check(state(page)['saved'] == [next_id], 'Concurrent sync preserves a removal and an independent addition')
        check(state(page)['reduceMotion'] and state(page)['updateTime'] == '10:30', 'Concurrent sync merges independent settings from two devices')

        # An expired cookie must have a way back into the account, keeping pending edits.
        first.clear_cookies()
        page.evaluate("async()=>{const s=await import('/static/js/storage.js');s.updateStore({updateTime:'11:45'});}")
        expect(page.locator('#auth-screen')).to_be_visible()
        expect(page.locator('#entry-session-status')).to_contain_text('session ended')
        page.locator('input[name="identifier"]').fill(username)
        page.locator('input[name="password"]').fill('Synthetic-pass-42')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#auth-screen')).not_to_be_visible()
        page.locator('#account-button').click()
        expect(page.locator('[data-profile-owner]')).to_be_visible()
        synced(page)
        check(state(page)['updateTime'] == '11:45', 'Expired sessions can sign in again without losing pending changes')
        page.locator('[data-account-action="close"]').first.click()

        # Offline reload loads the account cache without putting credentials in the SW.
        page.evaluate('navigator.serviceWorker.ready')
        page.reload(wait_until='networkidle')
        first.set_offline(True)
        page.reload(wait_until='networkidle')
        check(state(page)['saved'] == [next_id], 'Account progress is available after an offline reload')
        cache_urls = page.evaluate("async()=>{const out=[];for(const key of await caches.keys())for(const r of await(await caches.open(key)).keys())out.push(r.url);return out;}")
        check(not any('/api/account' in url for url in cache_urls), 'Service Worker caches no account response, photo, or CSRF token')
        first.set_offline(False)
        page.reload(wait_until='networkidle')
        page.locator('#account-button').click()
        page.locator('[data-account-action="remove-photo"]').click()
        expect(page.locator('#account-button img')).to_have_count(0)
        check(True, 'Removing a photo updates the account header')
        page.locator('[data-account-action="logout"]').click()
        expect(page.locator('#account-dialog')).not_to_be_visible()
        check(page.evaluate("localStorage.getItem('lexi:active-account')===null"), 'Signing out removes access and returns to the entry screen')
        check(page.evaluate("JSON.parse(localStorage.getItem('lexi:v1'))")==legacy,'Legacy browser data stays separate and is never copied into accounts')

        expect(page.locator('#auth-screen')).to_be_visible()
        check(first.request.get(BASE+'/api/catalog').status==401,'Signing out locks the catalog on the server again')
        page.reload(wait_until='networkidle')
        expect(page.locator('#auth-screen')).to_be_visible()
        first.set_offline(True)
        page.reload(wait_until='networkidle')
        check(page.locator('#auth-screen').is_visible() and page.locator('#account-auth-form button[type=submit]').is_disabled(),'A signed-out offline reload stays locked')
        first.set_offline(False)
        page.reload(wait_until='networkidle')
        page.locator('[data-account-action="login-tab"]').click()
        page.locator('input[name="identifier"]').fill(username)
        page.locator('input[name="password"]').fill('wrong-password')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#account-error')).to_contain_text('incorrect')
        check(page.locator('#account-auth-form button[type="submit"]').is_enabled(), 'Incorrect login shows feedback and leaves the form usable')
        page.locator('input[name="password"]').fill('Synthetic-pass-42')
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#auth-screen')).not_to_be_visible()
        page.locator('#account-button').click()
        expect(page.locator('[data-profile-owner]')).to_be_visible()
        check(state(page)['saved'] == [next_id], 'Signing in again by username restores the synchronized account')
        page.locator('[data-account-action="logout"]').click()
        expect(page.locator('#auth-screen')).to_be_visible()
        page.locator('[data-account-action="register-tab"]').click()
        for field, value in {'username': 'Other_' + stamp, 'email': 'other_' + stamp + '@example.com', 'password': 'Synthetic-pass-42'}.items():
            page.locator(f'input[name="{field}"]').fill(value)
        page.locator('[data-entry-theme-choice="experimental"]').click()
        page.locator('#account-auth-form button[type="submit"]').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(state(page)['saved'] == [] and state(page)['hiddenWords'] == [], 'Another account starts without the previous account or guest words')
        check(state(page)['theme']=='experimental' and page.locator('html').get_attribute('data-theme')=='experimental','The selected entry theme carries into a newly registered account')

        page.locator('input[name="onboarding"][value="culture"]').check()
        page.locator('#onboarding-update-time').fill('10:05')
        page.locator('#begin-button').click()
        expect(page.locator('#daily-word')).to_be_visible()
        b_word=state(page)['history'][0]['id']
        page.locator('[data-action="save"]').first.click()
        synced(page)
        page.locator('#account-button').click()
        page.locator('[data-account-action="logout"]').click()
        sign_in(page,username)
        check(state(page)['saved']==[next_id] and state(page)['interests']==['ielts'] and state(page)['updateTime']=='11:45','Returning to the first account restores its own words, interests and schedule')
        page.locator('[data-account-action="close"]').first.click()

        # A second tab can change the shared cookie while the first has a pending
        # response. A late conflict belonging to A must never merge into B.
        pending=[]
        page.route('**/api/account/state',lambda route:pending.append(route) if not pending else route.continue_())
        with page.expect_request(BASE+'/api/account/state'):
            page.evaluate("async()=>{const s=await import('/static/js/storage.js');s.updateStore({reduceMotion:!s.readStore().reduceMotion});}")
        a_state=state(page)
        tab=first.new_page()
        tab.on('pageerror',lambda error:errors.append(str(error)))
        tab.goto(BASE,wait_until='networkidle')
        synced(tab)
        tab.locator('#account-button').click()
        tab.locator('[data-account-action="logout"]').click()
        sign_in(tab,'Other_'+stamp)
        page.wait_for_function("name=>document.querySelector('#account-button').textContent.includes(name)",arg='Other_'+stamp)
        page.evaluate("""()=>{
          window.accountSnapshots=[];
          window.addEventListener('lexi:accountstate',()=>{
            const id=localStorage.getItem('lexi:active-account');
            window.accountSnapshots.push(JSON.parse(localStorage.getItem('lexi:account:'+id+':v2')));
          });
        }""")
        pending[0].fulfill(status=409,json={'error':'Newer changes are available.','code':'conflict','state':a_state,'revision':99})
        page.wait_for_timeout(500)
        check(state(page)['saved']==[b_word] and state(page)['interests']==['culture'] and state(page)['updateTime']=='10:05','A delayed response from the first account cannot contaminate the second account')
        check(all(snapshot['saved']==[b_word] and snapshot['interests']==['culture'] for snapshot in page.evaluate('window.accountSnapshots')),'No intermediate render exposes another account’s progress during a late response')
        page.unroute('**/api/account/state')
        tab.close()
        page.locator('#account-button').click()
        page.locator('[data-account-action="logout"]').click()
        sign_in(page,username)
        check(state(page)['saved']==[next_id] and all(item['id']!=b_word for item in state(page)['history']),'The first account keeps its own history after the second account signs out')
        page.locator('[data-account-action="logout"]').click()
        sign_in(page,'Other_'+stamp)
        check(state(page)['saved']==[b_word] and state(page)['interests']==['culture'] and all(item['id']==b_word for item in state(page)['history']),'Repeated sign-in restores only the second account’s own history and choices')

        # A fresh Noir account has not uploaded any preferences yet. Its first
        # offline onboarding must still sync when the server state is null.
        third=browser.new_context(service_workers='block')
        fresh=third.new_page()
        fresh.on('pageerror',lambda error:errors.append(str(error)))
        fresh.goto(BASE,wait_until='networkidle')
        fresh.locator('[data-entry-theme-choice="noir"]').click()
        for field,value in {'username':'Offline_'+stamp,'email':'offline_'+stamp+'@example.com','password':'Synthetic-pass-42'}.items():
            fresh.locator(f'input[name="{field}"]').fill(value)
        fresh.locator('#account-auth-form button[type="submit"]').click()
        expect(fresh.locator('#onboarding-dialog')).to_be_visible()
        check(third.request.get(BASE+'/api/account/session').json()['state'] is None,'A brand-new account has no inherited learning data on the server')
        third.set_offline(True)
        fresh.locator('input[name="onboarding"][value="science"]').check()
        fresh.locator('#begin-button').click()
        fresh.locator('[data-action="save"]').first.click()
        offline_saved=state(fresh)['saved']
        third.set_offline(False)
        synced(fresh)
        check(state(fresh)['saved']==offline_saved and state(fresh)['interests']==['science'],'First offline choices sync without being replaced by the empty server profile')
        fresh.locator('#account-button').click()
        fresh.locator('[data-account-action="logout"]').click()
        sign_in(fresh,'Offline_'+stamp)
        check(state(fresh)['saved']==offline_saved and state(fresh)['interests']==['science'],'First offline progress is preserved after signing out and back in')
        third.close()
        check(not errors, 'Account flows produce no uncaught JavaScript errors')
        first.close()
        second.close()
        browser.close()
    print(f'\n{len(checks)} account browser checks passed.', flush=True)


if __name__ == '__main__':
    run()
