"""Language-first account setup, spotlight steps and the real Settings target.

Run against a disposable database. Creates one synthetic account.
"""
import json
import os
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect
from auth_support import BrowserAccount

BASE=os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5000').rstrip('/')
OUTPUT=Path(__file__).resolve().parents[1]/'test-results'
OUTPUT.mkdir(exist_ok=True)
checks=[]


def check(value,label):
    if not value: raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)


def state(page):
    return page.evaluate("async()=>(await import('/static/js/storage.js')).readStore()")


def synced(page):
    page.wait_for_function("""()=>{
      const owner=localStorage.getItem('lexi:active-account');
      return !JSON.parse(localStorage.getItem('lexi:sync:'+owner+':v2')||'{"dirty":true}').dirty;
    }""")


def circle(page,selector):
    box=page.locator(selector).bounding_box()
    return box and abs(box['width']-box['height'])<2


def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        for language,theme,width in [('ru','studio',1440),('kk','noir',390),('en','experimental',320)]:
            context=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Asia/Bishkek',reduced_motion='reduce' if language=='en' else 'no-preference')
            fixture.authenticate(context,{'theme':theme})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(BASE,wait_until='networkidle')
            expect(page.locator('#onboarding-language')).to_be_visible()
            check(page.locator('[data-guide-language]').count()==3,f'{language}: Russian, Kazakh and English are offered first')
            check(not page.locator('#onboarding-update-time').is_visible() and not page.locator('#onboarding-collections').is_visible(),f'{language}: no setup controls precede the language choice')
            page.keyboard.press('Escape')
            check(page.locator('#onboarding-language').is_visible() and state(page)['history']==[],f'{language}: the first setup cannot be dismissed and records no preview history')
            page.screenshot(path=str(OUTPUT/f'guide-{language}-language.png'))
            page.locator(f'[data-guide-language="{language}"]').click()
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
            check(page.locator('#onboarding-dialog').get_attribute('lang')==language and state(page)['guideLanguage']==language,f'{language}: explanation language is applied and saved to the correct profile')
            check(page.locator('#onboarding-topics').evaluate('e=>e.inert&&getComputedStyle(e).filter.includes("blur")') and not page.locator('#onboarding-time').evaluate('e=>e.inert'),f'{language}: time is usable while collections are blurred and inert')
            page.locator('#onboarding-update-time').fill('')
            check(page.locator('#onboarding-next').is_disabled(),f'{language}: an empty time cannot advance')
            page.locator('#onboarding-update-time').fill('09:25')
            synced(page)
            page.reload(wait_until='networkidle')
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
            check(page.locator('#onboarding-update-time').input_value()=='09:25' and not page.locator('#onboarding-language').is_visible(),f'{language}: reload resumes the saved time step and language')
            page.wait_for_timeout(520)
            check(circle(page,'#onboarding-coach'),f'{language}: time explanation is a real circle')
            time_box=page.locator('#onboarding-update-time').bounding_box();zone_box=page.locator('#onboarding-schedule .schedule-timezone').bounding_box()
            check(zone_box['y']>=time_box['y']+time_box['height'] or zone_box['x']>=time_box['x']+time_box['width']+6,f'{language}: time and timezone never overlap')
            if language=='en':check(page.locator('#onboarding-coach').evaluate('e=>e.getAnimations().length===0'),'Reduced motion keeps the coach static')
            first=page.locator('#onboarding-coach').bounding_box()
            page.screenshot(path=str(OUTPUT/f'guide-{language}-time.png'))
            if language=='ru':
                page.evaluate('navigator.serviceWorker.ready')
                page.wait_for_function("async()=>!!await caches.match('/api/catalog')")
                context.set_offline(True)
            page.locator('#onboarding-next').click()
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','collections')
            check(page.locator('#onboarding-time').evaluate('e=>e.inert&&getComputedStyle(e).filter.includes("blur")') and not page.locator('#onboarding-topics').evaluate('e=>e.inert'),f'{language}: spotlight moves from time to the collections')
            check(page.locator('#begin-button').is_disabled(),f'{language}: one or more collections are required')
            page.wait_for_timeout(520)
            second=page.locator('#onboarding-coach').bounding_box()
            check(second['y']>=0 and second['y']+second['height']<=1000,f'{language}: the collections explanation is visible before selecting topics')
            if width==1440:check(second['x']>first['x']+200,'The same coach moves from the left to the right of the panel')
            page.locator('input[name="onboarding"][value="ielts"]').check()
            page.locator('input[name="onboarding"][value="science"]').check()
            check(not state(page)['onboarded'] and not state(page)['history'],f'{language}: choosing collections does not finish the guide or record a word early')
            if language=='ru':
                page.reload(wait_until='networkidle')
                expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','collections')
                check(state(page)['interests']==['science','ielts'] or set(state(page)['interests'])=={'science','ielts'},'Offline reload keeps language, step, time and selected collections')
                context.set_offline(False);synced(page)
            page.locator('#onboarding-back').click()
            expect(page.locator('#onboarding-dialog')).to_have_attribute('data-guide-step','time')
            check(page.locator('#onboarding-update-time').input_value()=='09:25' and state(page)['interests'],f'{language}: Back preserves the chosen time and collections')
            page.locator('#onboarding-next').click()
            for viewport in (320,390,768,1440):
                page.set_viewport_size({'width':viewport,'height':1000});page.wait_for_timeout(80)
                check(page.locator('#onboarding-dialog').evaluate('e=>e.scrollWidth<=e.clientWidth+1') and page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'{language}: setup has no horizontal overflow at {viewport}px')
            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(520)
            page.screenshot(path=str(OUTPUT/f'guide-{language}-collections.png'))
            page.locator('#begin-button').click()
            expect(page.locator('#settings-guide-dialog')).to_be_visible();page.wait_for_timeout(520)
            check(not page.locator('#onboarding-dialog').is_visible() and state(page)['onboarded'] and len(state(page)['history'])==1,f'{language}: completing collections closes the panel and starts real learning')
            check(page.locator('.settings-link').evaluate('e=>e.closest("#settings-guide-dialog")!==null') and page.locator('.guide-settings-placeholder').count()==1,f'{language}: the hint highlights the real gear instead of a disconnected copy')
            check(page.locator('#settings-guide-dialog').get_attribute('lang')==language and state(page)['guideStep']=='settings',f'{language}: the final hint uses the chosen language and remains unfinished until acknowledged')
            for viewport in (320,390,768,1440):
                page.set_viewport_size({'width':viewport,'height':844});page.wait_for_timeout(80)
                box=page.locator('.settings-guide-circle').bounding_box();gear=page.locator('.guide-settings-target').bounding_box()
                check(circle(page,'.settings-guide-circle') and box['x']>=0 and box['x']+box['width']<=viewport+1 and box['y']+box['height']<=844 and gear['x']>=0,f'{language}: circular hint and gear remain on screen at {viewport}px')
            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(100)
            page.screenshot(path=str(OUTPUT/f'guide-{language}-settings.png'))
            if language=='en':page.locator('.guide-settings-target').click()
            elif language=='kk':page.keyboard.press('Escape')
            else:page.locator('#guide-settings-done').click()
            expect(page.locator('#settings-guide-dialog')).not_to_be_visible()
            check(state(page)['guideStep']=='done' and page.locator('.site-header .settings-link').count()==1,f'{language}: acknowledging the hint saves completion and restores the gear')
            if language=='en':check(page.evaluate('location.hash')=='#settings','The highlighted gear opens the real Settings page')
            synced(page);page.reload(wait_until='networkidle')
            check(not page.locator('#onboarding-dialog').is_visible() and not page.locator('#settings-guide-dialog').is_visible(),f'{language}: returning users are not shown the first guide again')
            remote=fixture.api.get('/api/account/session').json()['state']
            check(remote['guideLanguage']==language and remote['guideStep']=='done',f'{language}: server state retains the chosen guide language and completion')
            check(not errors,f'{language}: no browser JavaScript errors')
            context.close()
        browser.close();fixture.dispose()
    print(f'All {len(checks)} onboarding guide checks passed.',flush=True)


if __name__=='__main__':run()
