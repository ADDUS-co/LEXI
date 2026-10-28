"""Replay the complete guide on an existing account without resetting learning data."""
import os
import shutil

from playwright.sync_api import sync_playwright, expect
from auth_support import BrowserAccount, finish_reading_guide

BASE=os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5000').rstrip('/')
checks=[]


def check(value,label):
    if not value:raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)


def state(page):
    return page.evaluate("async()=>(await import('/static/js/storage.js')).readStore()")


def synced(page):
    page.wait_for_function("""()=>{
      const id=localStorage.getItem('lexi:active-account');
      return !JSON.parse(localStorage.getItem('lexi:sync:'+id+':v2')||'{"dirty":true}').dirty;
    }""")


def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        daily=fixture.api.get('/api/daily',params={'collections':'ielts,science','timezone':'Asia/Bishkek','update_time':'09:25'}).json()['word']['id']
        other=[word['id'] for word in fixture.catalog['words'] if word['id']!=daily]
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        for language,theme,width in (('ru','studio',1440),('kk','noir',390),('en','experimental',320)):
            context=browser.new_context(viewport={'width':width,'height':1000 if width==1440 else 844},timezone_id='Asia/Bishkek',reduced_motion='reduce')
            fixture.authenticate(context,{'onboarded':True,'guideLanguage':language,'guideStep':'done','theme':theme,
                                         'interests':['ielts','science'],'updateTime':'09:25','saved':other[:2],
                                         'hiddenWords':[other[2]],'history':[{'id':other[0],'date':'2026-01-01'}]})
            page=context.new_page();errors=[];registrations=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:registrations.append(request.url) if request.method=='POST' and request.url.endswith('/api/account/register') else None)
            page.goto(BASE,wait_until='networkidle');expect(page.locator('#daily-word')).to_be_visible();synced(page)
            initial=state(page);owner=context.request.get(BASE+'/api/account/session').json()['user']['id']
            page.locator('.site-header .settings-link').click()
            replay=page.get_by_role('button',name='Explain again',exact=True)
            expect(replay).to_be_visible()
            check(replay.evaluate("button=>button.classList.contains('button-outline')") and page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'{language}: neutral replay button is available in Settings without overflow at {width}px')
            replay.click();expect(page.locator('#onboarding-language')).to_be_visible()
            check(all(state(page)[key]==initial[key] for key in ('saved','history','hiddenWords','interests','updateTime','theme','reduceMotion')),f'{language}: restarting changes only guide progress and keeps learning data and settings')
            page.locator(f'[data-guide-language="{language}"]').click()
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
            check(page.locator('#onboarding-update-time').input_value()=='09:25',f'{language}: the time explanation starts with the current saved time')
            synced(page);page.reload(wait_until='networkidle')
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
            check(page.locator('#onboarding-update-time').input_value()=='09:25' and state(page)['saved']==initial['saved'],f'{language}: reload resumes the replay without creating a new profile')
            if language=='ru':
                second=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Bishkek',reduced_motion='reduce')
                second.add_cookies(context.cookies());other_page=second.new_page();other_page.goto(BASE,wait_until='networkidle')
                expect(other_page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
                check(state(other_page)['saved']==initial['saved'] and other_page.locator('#onboarding-update-time').input_value()=='09:25','Replay and existing data also resume in a fresh browser context')
                second.close()
            page.locator('#onboarding-next').click()
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','collections')
            selected=page.locator('input[name="onboarding"]:checked').evaluate_all('inputs=>inputs.map(input=>input.value)')
            check(set(selected)==set(initial['interests']),f'{language}: the collections explanation keeps the previous selections checked')
            page.locator('#begin-button').click()
            expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','settings')
            page.locator('#guide-settings-done').click()
            expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
            page.locator('#guide-settings-done').click();finish_reading_guide(page);synced(page)
            final=state(page);remote=context.request.get(BASE+'/api/account/session').json()
            check(final['onboarded'] and final['guideStep']=='done' and remote['user']['id']==owner,f'{language}: the entire setup and word walkthrough finishes on the same account')
            check(all(final[key]==initial[key] for key in ('history','hiddenWords','interests','updateTime','theme','reduceMotion')) and set(initial['saved']).issubset(final['saved']) and daily in final['saved'],f'{language}: the complete replay preserves progress and adds the demonstration word only once')
            check(remote['state']['guideStep']=='done' and remote['state']['hiddenWords']==initial['hiddenWords'],f'{language}: guide completion and preserved data are synchronized to the server')
            page.locator('.site-header .settings-link').click();page.get_by_role('button',name='Explain again',exact=True).click()
            expect(page.locator('#onboarding-language')).to_be_visible()
            check(not registrations and not errors,f'{language}: the same profile can replay again without registration or browser errors')
            synced(page);context.close()
        browser.close();fixture.dispose()
    print(f'All {len(checks)} guide-replay checks passed.',flush=True)


if __name__=='__main__':run()
