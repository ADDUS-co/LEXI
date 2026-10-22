"""Return upward, demonstrate typing and hand the real card back to the learner.

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

def ready(page,phase):
    expect(page.locator('#settings-guide-dialog')).to_have_attribute('data-guide-phase',phase,timeout=15000)
    expect(page.locator('#guide-settings-done')).to_be_enabled(timeout=15000)
    page.wait_for_function("()=>document.querySelector('#settings-guide-dialog').getAnimations({subtree:true}).every(a=>a.playState!=='running')")

def record(page):
    page.evaluate("""()=>{window.recallFrames=[];window.recordRecall=true;function sample(){
      const panel=document.querySelector('[data-guide-content=recall]'),input=document.querySelector('#guide-recall-answer');
      window.recallFrames.push({y:scrollY,stage:panel?.dataset.recallStage,value:input?.value,invalid:input?.getAttribute('aria-invalid'),transform:input?getComputedStyle(input).transform:null,pulses:document.querySelectorAll('.guide-memory-pulse').length});
      if(window.recordRecall)requestAnimationFrame(sample);
    }sample();}""")

def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        errors=[]
        for language,theme,width in (('ru','studio',1440),('kk','noir',390),('en','experimental',768)):
            context=browser.new_context(viewport={'width':width,'height':1000 if width==1440 else 844},timezone_id='Asia/Bishkek')
            fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':language,'guideStep':'deep','theme':theme})
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='networkidle');ready(page,'deep')
            initial=state(page);word=page.locator('#daily-word').inner_text().rstrip('.');record(page)
            page.locator('#guide-settings-done').click();ready(page,'recall')
            page.wait_for_function("()=>document.querySelector('[data-guide-content=recall]')?.dataset.recallStage==='complete'",timeout=20000)
            page.evaluate('window.recordRecall=false');frames=page.evaluate('window.recallFrames')
            stages={f.get('stage') for f in frames}
            check({'tapping','flipping-back','wrong','erasing','empty','correct','flipping-front'}.issubset(stages),f'{language}: the complete demonstration shows both flips, error, deletion and success')
            check(max(f['pulses'] for f in frames)==2,f'{language}: two visible tap rings demonstrate the double-tap')
            scroll=[f['y'] for f in frames if f.get('stage') in (None,'intro')]
            check(len(set(round(y) for y in scroll))>6 and scroll[0]>scroll[-1]+200,f'{language}: the page travels smoothly upward from the deeper definition')
            wrong=[f for f in frames if f.get('stage')=='wrong']
            check(any(f['invalid']=='true' and f['transform'] not in (None,'none','matrix(1, 0, 0, 1, 0, 0)') for f in wrong),f'{language}: the invalid answer visibly shakes')
            erased=[f['value'] for f in frames if f.get('stage')=='erasing']
            lengths=list(dict.fromkeys(len(v) for v in erased))
            check(len(lengths)>3 and all(a-b==1 for a,b in zip(lengths,lengths[1:])) and any(f.get('stage')=='empty' and f['value']=='' for f in frames),f'{language}: backspace removes one character at a time and reaches an empty field')
            correct=[f for f in frames if f.get('stage')=='correct']
            check(correct and all(f['value']==word and f['invalid'] is None for f in correct),f'{language}: only the exact current word receives success feedback')
            check(state(page)['hiddenWords']==initial['hiddenWords'] and state(page)['history']==initial['history'] and state(page)['saved']==initial['saved'],f'{language}: watching the demonstration leaves the learner’s real card and progress intact')
            check(page.locator('#settings-guide-dialog').get_attribute('lang')==language and state(page)['guideStep']=='recall',f'{language}: the final explanation uses the chosen language and waits for acknowledgement')
            for viewport in (320,390,768,1440):
                page.set_viewport_size({'width':viewport,'height':568 if viewport==320 else 844});page.wait_for_timeout(90)
                fit=page.evaluate("""()=>{const a=document.querySelector('.guide-content-spotlight').getBoundingClientRect(),b=document.querySelector('.settings-guide-circle').getBoundingClientRect();return [a,b].every(r=>r.left>=12&&r.right<=innerWidth-12&&r.top>=12&&r.bottom<=innerHeight-12)&&(a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top)&&document.documentElement.scrollWidth<=innerWidth;}""")
                check(fit,f'{language}: the final card and circle fit at {viewport}px')
            if language=='ru':
                page.locator('.guide-memory-replay').click()
                page.wait_for_function("()=>!!document.querySelector('#guide-recall-answer')")
                page.locator('#guide-settings-done').click()
                expect(page.locator('#settings-guide-dialog')).not_to_be_visible()
                page.wait_for_timeout(350)
                check(page.locator('#guide-recall-answer').count()==0 and page.locator('.guide-memory-pulse').count()==0 and state(page)['guideStep']=='done','Skipping during typing cancels callbacks and removes all demo layers')
                page.locator('#daily-word').dblclick();expect(page.locator('#recall-form')).to_be_visible()
                page.locator('#recall-answer').fill(word+'x');page.locator('#recall-answer').press('Enter')
                expect(page.locator('#recall-answer')).to_have_attribute('aria-invalid','true')
                page.locator('#recall-answer').fill(word);page.locator('#recall-answer').press('Enter');expect(page.locator('#daily-word')).to_be_visible()
                check(state(page)['hiddenWords']==[],'After the tour, real double-tap, invalid input and correct spelling still work')
            else:
                page.locator('#guide-settings-done').click();expect(page.locator('#settings-guide-dialog')).not_to_be_visible()
                check(page.locator('#daily-word').evaluate('e=>e===document.activeElement'),'Finishing returns focus to the real daily word')
            context.close()
        for system,setting in (('reduce',False),('no-preference',True)):
            context=browser.new_context(viewport={'width':320,'height':568},reduced_motion=system)
            fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':'ru','guideStep':'recall','reduceMotion':setting})
            page=context.new_page();page.goto(BASE,wait_until='networkidle')
            page.wait_for_function("()=>document.querySelector('[data-guide-content=recall]')?.dataset.recallStage==='complete'")
            check(page.locator('.guide-memory-pulse').count()==0 and page.locator('#guide-recall-answer').count()==0,'Reduced motion shows the completed explanation without typing or shaking')
            page.locator('#guide-settings-done').click();expect(page.locator('#settings-guide-dialog')).not_to_be_visible();context.close()
        context=browser.new_context(viewport={'width':390,'height':844})
        fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':'en','guideStep':'recall'})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='networkidle')
        page.wait_for_function("()=>!!document.querySelector('#guide-recall-answer')")
        page.reload(wait_until='networkidle');ready(page,'recall')
        check(state(page)['hiddenWords']==[] and page.locator('#daily-word').count()==1,'Reloading during typing restarts a clean explanation without leaving the real card hidden')
        page.wait_for_function("()=>!!document.querySelector('#guide-recall-answer')")
        context.clear_cookies();page.evaluate("async()=>{(await import('/static/js/storage.js')).updateStore({updateTime:'21:25'});}")
        expect(page.locator('#auth-screen')).to_be_visible();page.wait_for_timeout(350)
        check(page.locator('.guide-content-spotlight').count()==0 and not page.locator('#settings-guide-dialog').is_visible(),'Session loss stops the demo immediately and clears its word and input')
        context.close()
        context=browser.new_context(viewport={'width':390,'height':844})
        word_id=next(item['id'] for item in fixture.catalog['words'] if item['word']==word)
        fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'guideLanguage':'en','guideStep':'recall','hiddenWords':[word_id]})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE,wait_until='networkidle')
        check(page.locator('#recall-form').is_visible() and page.locator('.guide-content-spotlight').count()==0,'A saved hidden card keeps its answer hidden while the final guide waits')
        page.locator('.recall-double-button').click();page.locator('.recall-double-button').click();ready(page,'recall')
        check(state(page)['hiddenWords']==[],'Explicitly revealing the real word resumes the final explanation')
        page.wait_for_function("()=>!!document.querySelector('#guide-recall-answer')")
        page.emulate_media(reduced_motion='reduce')
        page.wait_for_function("()=>document.querySelector('[data-guide-content=recall]')?.dataset.recallStage==='complete'")
        page.wait_for_timeout(300)
        check(page.locator('#guide-recall-answer').count()==0 and page.locator('.guide-memory-pulse').count()==0,'Turning on reduced motion during typing cancels typing and finishes cleanly')
        context.close();browser.close();fixture.dispose()
        check(not errors,'No JavaScript errors during playback, interruption, reload or logout')
    print(f'All {len(checks)} recall-guide checks passed.',flush=True)

if __name__=='__main__':run()
