"""Daily-word guide resumes across devices and respects recall/account boundaries.

Run against a disposable database; creates one synthetic account.
"""
import os
import shutil
from playwright.sync_api import sync_playwright, expect
from auth_support import BrowserAccount

BASE=os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5000').rstrip('/')
checks=[]

def check(value,label):
    if not value:raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)

def state(page):
    return page.evaluate("async()=>(await import('/static/js/storage.js')).readStore()")

def synced(page):
    page.wait_for_function("()=>!JSON.parse(localStorage.getItem('lexi:sync:'+localStorage.getItem('lexi:active-account')+':v2')||'{\"dirty\":true}').dirty")

def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        first=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Bishkek')
        fixture.authenticate(first,{'onboarded':True,'interests':['ielts'],'guideLanguage':'ru','guideStep':'word'})
        page=first.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE,wait_until='networkidle');expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
        check(not page.locator('#onboarding-dialog').is_visible(),'A saved word step resumes directly without repeating the setup panel')
        word_id=page.locator('#main-content [data-action="save"]').first.get_attribute('data-word')
        word_text=page.locator('#main-content #daily-word').inner_text()
        synced(page)
        second=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Bishkek')
        second.add_cookies(fixture.api.storage_state()['cookies'])
        other=second.new_page();other.goto(BASE,wait_until='networkidle')
        expect(other.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
        check(state(other)['guideLanguage']=='ru' and other.locator('#guide-daily-word').inner_text()==word_text,'Another device resumes the same guide language and daily word')
        other.locator('#guide-settings-done').click();expect(other.locator('#settings-guide-dialog')).not_to_be_visible();synced(other)
        page.reload(wait_until='networkidle')
        check(state(page)['guideStep']=='done' and not page.locator('#settings-guide-dialog').is_visible(),'Completion on another device prevents the word step from reopening after reload')
        first.close();second.close()
        fast=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Bishkek')
        fixture.authenticate(fast,{'onboarded':True,'interests':['ielts'],'guideLanguage':'ru','guideStep':'settings'})
        page=fast.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='domcontentloaded')
        expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','settings')
        continuity=page.evaluate("""()=>{const c=document.querySelector('.settings-guide-circle'),b=c.getBoundingClientRect(),opacity=parseFloat(getComputedStyle(c).opacity);document.querySelector('#guide-settings-done').click();const a=c.getBoundingClientRect();return Math.hypot(a.x-b.x,a.y-b.y)<1&&Math.abs(a.width-b.width)<1&&Math.abs(parseFloat(getComputedStyle(c).opacity)-opacity)<.02;}""")
        check(continuity,'Next during the settings entrance fades from the current position and opacity without a jump')
        expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
        check(page.locator('#guide-daily-word').count()==1 and page.locator('.settings-guide-circle').count()==1,'Interrupting the entrance creates one word highlight and one explanation circle')
        fast.close()
        hidden=browser.new_context(viewport={'width':320,'height':568},timezone_id='Asia/Bishkek')
        fixture.authenticate(hidden,{'onboarded':True,'interests':['ielts'],'guideLanguage':'ru','guideStep':'word','hiddenWords':[word_id]})
        page=hidden.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='networkidle')
        expect(page.locator('#recall-form')).to_be_visible()
        check(page.locator('#guide-daily-word').count()==0 and not page.locator('#settings-guide-dialog').is_visible() and state(page)['guideStep']=='word','A hidden recall card keeps the answer hidden and leaves the explanation pending')
        check(word_text.rstrip('.') not in page.locator('#learning-app').inner_text() and 'Recall practice' in page.title(),'The hidden answer is absent from the page and its title')
        page.locator('.recall-double-button').click();page.locator('.recall-double-button').click()
        expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase','word')
        page.wait_for_function("()=>document.querySelector('#settings-guide-dialog').getAnimations({subtree:true}).every(a=>a.playState!=='running')")
        check(page.locator('#guide-daily-word').inner_text()==word_text and state(page)['hiddenWords']==[],'Revealing the card explicitly resumes the word explanation with the correct answer')
        check(page.locator('.settings-guide-circle').evaluate('e=>e.getBoundingClientRect().bottom<=innerHeight-12'),'The word explanation fits a 320 × 568 screen')
        hidden.clear_cookies()
        page.evaluate("async()=>{const s=await import('/static/js/storage.js');s.updateStore({updateTime:'21:25'});}")
        expect(page.locator('#auth-screen')).to_be_visible()
        check(page.locator('#guide-daily-word').count()==0 and not page.locator('#settings-guide-dialog').is_visible(),'An expired session immediately removes the highlighted word and closes the guide')
        check(not errors,'No JavaScript errors during resume, recall reveal or session loss')
        hidden.close();browser.close();fixture.dispose()
    print(f'All {len(checks)} daily-word guide checks passed.',flush=True)

if __name__=='__main__':run()
