"""The reading tour highlights real content, saves once and returns to a deeper definition.

Run against a disposable database; creates one synthetic account.
"""
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
    if not value:raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)

def state(page):
    return page.evaluate("async()=>(await import('/static/js/storage.js')).readStore()")

def ready(page,phase):
    expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase',phase,timeout=15000)
    expect(page.locator('#guide-settings-done')).to_be_enabled(timeout=15000)
    page.wait_for_function("()=>document.querySelector('#settings-guide-dialog').getAnimations({subtree:true}).every(a=>a.playState!=='running')")

def synced(page):
    page.wait_for_function("()=>!JSON.parse(localStorage.getItem('lexi:sync:'+localStorage.getItem('lexi:active-account')+':v2')||'{\"dirty\":true}').dirty")

def fits(page):
    return page.evaluate("""()=>{
      const p=document.querySelector('.guide-content-spotlight').getBoundingClientRect(),c=document.querySelector('.settings-guide-circle').getBoundingClientRect();
      const inside=b=>b.left>=12&&b.right<=innerWidth-12&&b.top>=12&&b.bottom<=innerHeight-12;
      const apart=p.right<=c.left||c.right<=p.left||p.bottom<=c.top||c.bottom<=p.top;
      return inside(p)&&inside(c)&&apart&&Math.abs(c.width-c.height)<1&&document.documentElement.scrollWidth<=innerWidth;
    }""")

def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        errors=[]
        for language,theme in (('ru','studio'),('kk','noir'),('en','experimental')):
            context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Bishkek')
            fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':language,'guideStep':'word','theme':theme})
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(BASE,wait_until='networkidle');ready(page,'word')
            word=page.locator('#daily-word').inner_text();word_id=page.locator('.word-tools [data-word]').get_attribute('data-word')
            page.locator('#guide-settings-done').click()
            for phase in ('definition','synonyms','examples','save','saved','deep'):
                ready(page,phase)
                check(state(page)['guideStep']==phase and page.locator('#settings-guide-dialog').get_attribute('lang')==language,f'{language}/{phase}: the step and explanation language persist')
                if phase not in ('save','saved'):
                    selector={'definition':'.short-definition','synonyms':'.synonym-pills','examples':'.hero-example','deep':'.definition-block'}[phase]
                    original=page.locator('#main-content '+selector).inner_text()
                    check(' '.join(original.split())==' '.join(page.locator('.guide-content-spotlight').inner_text().split()),f'{language}/{phase}: highlight contains the real daily-word content')
                for width,height in ((320,568),(390,844),(768,844),(1440,844),(844,390),(568,320)):
                    page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(90)
                    check(fits(page),f'{language}/{phase}: content and circle fit without overlap at {width} × {height}')
                if phase=='definition' and language=='ru':
                    synced(page);context.set_offline(True);page.reload(wait_until='networkidle');ready(page,phase)
                    check(len(state(page)['history'])==1,'An offline reload resumes the definition without duplicate history')
                    context.set_offline(False);synced(page)
                if phase=='save':
                    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(90)
                    page.locator('#guide-settings-done').click()
                    expect(page.locator('.guide-flying-bookmark')).to_be_visible()
                    check(page.locator('.guide-save-destination').evaluate('e=>{const b=e.getBoundingClientRect();return b.top>=12&&b.bottom<=innerHeight-12;}'),'The neutral Saved destination is visible during the bookmark flight')
                    page.evaluate("()=>{for(let i=0;i<5;i++)document.querySelector('#guide-settings-done').click();}")
                    ready(page,'saved')
                    check(state(page)['saved']==[word_id] and page.evaluate('location.hash')=='#saved','The demonstration saves the word exactly once and opens the real Saved route')
                    check(word.rstrip('.') in page.locator('.guide-content-spotlight').inner_text(),'The saved daily word is shown in the real wordshelf')
                    continue
                if phase=='saved':
                    synced(page);page.reload(wait_until='networkidle');ready(page,'saved')
                    check(state(page)['saved']==[word_id] and len(state(page)['history'])==1,'Reloading Saved keeps the word and resumes without replaying the save action')
                    if language=='ru':
                        second=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Bishkek');second.add_cookies(fixture.api.storage_state()['cookies'])
                        other=second.new_page();other.goto(BASE,wait_until='networkidle');ready(other,'saved')
                        check(state(other)['saved']==[word_id] and state(other)['guideLanguage']=='ru','A second device receives the saved word and the current tour step')
                        second.close()
                    page.evaluate("window.guideScroll=[];window.addEventListener('scroll',()=>window.guideScroll.push(scrollY));")
                if phase=='deep':
                    samples=page.evaluate('window.guideScroll||[]')
                    check(page.evaluate('location.hash')=='#home' and page.evaluate('scrollY')>200 and len(set(round(n) for n in samples))>4,'Returning to Home visibly scrolls down to the deeper definition')
                    page.screenshot(path=str(OUTPUT/f'reading-{language}-deep.png'))
                page.locator('#guide-settings-done').click()
            ready(page,'recall')
            check(state(page)['guideStep']=='recall' and state(page)['hiddenWords']==[],'The deep definition continues upward to recall without changing real card positions')
            page.locator('#guide-settings-done').click()
            expect(page.locator('#settings-guide-dialog')).not_to_be_visible()
            check(state(page)['guideStep']=='done' and state(page)['saved']==[word_id],'Completing the tour keeps the saved word and removes all highlights')
            synced(page);page.reload(wait_until='networkidle')
            check(not page.locator('#settings-guide-dialog').is_visible(),'A completed tour stays completed after reload')
            context.close()
        # Existing Saved words must never be toggled off by the demonstration.
        context=browser.new_context(viewport={'width':320,'height':568},reduced_motion='reduce',timezone_id='Asia/Bishkek')
        fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':'ru','guideStep':'save','saved':[word_id]})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='networkidle');ready(page,'save')
        page.locator('#guide-settings-done').click();ready(page,'saved')
        check(state(page)['saved']==[word_id] and page.locator('.guide-flying-bookmark').count()==0,'An already saved word stays saved and reduced motion skips the flight')
        page.locator('#guide-settings-done').click();ready(page,'deep')
        check(fits(page) and page.locator('.guide-content-spotlight').evaluate('e=>e.scrollHeight>e.clientHeight&&e.tabIndex===0'),'Long definitions scroll independently and are keyboard accessible on 320 × 568')
        context.clear_cookies();page.evaluate("async()=>{(await import('/static/js/storage.js')).updateStore({updateTime:'21:25'});}")
        expect(page.locator('#auth-screen')).to_be_visible()
        check(page.locator('.guide-content-spotlight').count()==0 and not page.locator('#settings-guide-dialog').is_visible(),'Session loss removes copied content and closes the tour')
        context.close()
        context=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Bishkek')
        fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':'en','guideStep':'definition','hiddenWords':[word_id]})
        page=context.new_page();page.goto(BASE,wait_until='networkidle')
        check(page.locator('#recall-form').is_visible() and page.locator('.guide-content-spotlight').count()==0,'A pending reading tour never exposes a hidden recall card')
        context.close();browser.close();fixture.dispose()
        check(not errors,'No JavaScript errors during the reading tour, saving, reloads or session loss')
    print(f'All {len(checks)} reading-guide checks passed.',flush=True)

if __name__=='__main__':run()
