"""V2 functional checks: real profile restart, local rollover, and memory cards.

Start LEXI first. Install Playwright separately; run python tests/browser_v2.py.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from auth_support import BrowserAccount

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lexi.schedule import daily_schedule
from lexi.selection import select_word

BASE = os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5000').rstrip('/')
OUTPUT = ROOT/'test-results'
OUTPUT.mkdir(exist_ok=True)
checks = []


def check(value,label):
    if not value: raise AssertionError(label)
    checks.append(label)
    print('PASS',label,flush=True)


def state(page):
    return page.evaluate("JSON.parse(localStorage.getItem('lexi:account:'+localStorage.getItem('lexi:active-account')+':v2'))")


def go(page,route):
    page.evaluate('route=>{location.hash=route}',route)
    expect(page.locator(f'[data-nav="{route}"]')).to_have_attribute('aria-current','page')


def no_overflow(page,label):
    page.evaluate('document.fonts.ready')
    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),label)


def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        catalog=fixture.catalog
        executable=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
        profile=tempfile.mkdtemp(prefix='lexi-recall-profile-')
        def open_profile():
            context=p.chromium.launch_persistent_context(profile,executable_path=executable,args=['--no-sandbox','--disable-dev-shm-usage'],viewport={'width':1440,'height':1000},timezone_id='America/New_York',service_workers='block')
            page=context.pages[0]
            return context,page
        context,page=open_profile()
        fixture.authenticate(context)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.clock.install(time=datetime.fromisoformat('2026-10-19T11:59:00+00:00'))
        page.goto(BASE,wait_until='networkidle')
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(page.locator('#onboarding-update-time').input_value()=='08:00','New visitors can choose their update time during onboarding')
        check('America/New York' in page.locator('#onboarding-schedule').inner_text(),'Onboarding identifies the actual device timezone')
        check(page.locator('input[name="onboarding"]').count()==len(catalog['collections']),'All collections are generated from metadata')
        for collection in ('ielts','science','psychology','culture'):
            check(page.locator(f'input[name="onboarding"][value="{collection}"]').count()==1,f'New collection available: {collection}')
        page.locator('input[name="onboarding"][value="ielts"]').check()
        page.locator('#begin-button').click()
        before=select_word(catalog['collections'],catalog['words'],['ielts'],'2026-10-18')
        after=select_word(catalog['collections'],catalog['words'],['ielts'],'2026-10-19')
        expect(page.locator('#daily-word')).to_have_text(before['word']+'.')
        check(state(page)['history'][0]['date']=='2026-10-19','History records the real viewing date before the chosen rollover')
        check(state(page)['updateTime']=='08:00','Onboarding saves the chosen local update time')
        page.clock.run_for(61000)
        expect(page.locator('#daily-word')).to_have_text(after['word']+'.')
        check(len(state(page)['history'])==2,'A new word appears at the selected local time without a reload')
        expect(page.locator('.next-word-label')).to_contain_text('tomorrow at 08:00')
        page.locator('[data-action="save"]').first.click()
        page.locator('#daily-word').dblclick()
        expect(page.locator('#recall-form')).to_be_visible()
        page.wait_for_timeout(400)
        check(after['id'] in state(page)['hiddenWords'],'Double-click flips the word and immediately persists its hidden state')
        check(after['word'].casefold() not in page.locator('#main-content').inner_text().casefold(),'The back face contains no visible answer or word examples')
        check(after['word'].casefold() not in page.title().casefold(),'Browser title does not expose the hidden word')
        check(page.locator('.ipa,[data-action="pronounce"],[data-action="share"],#beyond-word').count()==0,'Pronunciation, IPA, share, and expanded answer are absent while hidden')

        # Closing the actual browser preserves localStorage in its real profile.
        context.close()
        context,page=open_profile()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.clock.install(time=datetime.fromisoformat('2026-10-19T12:00:01+00:00'))
        page.goto(BASE,wait_until='networkidle')
        expect(page.locator('#recall-form')).to_be_visible()
        check(after['id'] in state(page)['hiddenWords'],'The card remains hidden after closing and reopening the browser')
        page.locator('#recall-answer').fill('not-the-word')
        page.locator('#recall-form button').click()
        expect(page.locator('#recall-answer')).to_have_attribute('aria-invalid','true')
        check(page.locator('#daily-word').count()==0,'An incorrect spelling does not reveal the answer')
        page.locator('#recall-answer').fill(after['word'][:2])
        page.locator('#recall-form button').click()
        check(page.locator('#daily-word').count()==0,'A partial answer is not accepted')
        page.locator('#recall-answer').fill('  '+after['word'].upper()+'  ')
        page.locator('#recall-form button').click()
        expect(page.locator('#daily-word')).to_have_text(after['word']+'.')
        page.wait_for_timeout(400)
        check(after['id'] not in state(page)['hiddenWords'],'The complete correct word reveals the card, ignoring case and outside spaces')
        page.locator('[data-action="hide-word"]').click()
        expect(page.locator('#recall-form')).to_be_visible()
        page.wait_for_timeout(400)
        go(page,'saved')
        check(after['word'].casefold() not in page.locator('#word-list').inner_text().casefold(),'Saved does not give away a hidden answer')
        page.locator('.word-card-main').click()
        expect(page.locator('#recall-form')).to_be_visible()
        check(True,'Opening a hidden word from Saved returns to its recall card')
        go(page,'history')
        check(after['word'].casefold() not in page.locator('#word-list').inner_text().casefold(),'History does not give away a hidden answer')
        go(page,'home')
        page.locator('#recall-title').dblclick()
        expect(page.locator('#daily-word')).to_have_text(after['word']+'.')
        page.wait_for_timeout(400)
        check(True,'Double-clicking the back reveals the word without typing')
        page.locator('[data-action="hide-word"]').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#recall-form')).to_be_visible()
        page.wait_for_timeout(400)
        page.locator('[data-action="reveal-twice"]').focus()
        page.keyboard.press('Enter')
        check(page.locator('#daily-word').count()==0,'One keyboard activation does not reveal the word')
        page.keyboard.press('Enter')
        expect(page.locator('#daily-word')).to_be_visible()
        page.wait_for_timeout(400)
        check(True,'Two keyboard activations provide an accessible alternative to double-tap')

        go(page,'settings')
        page.locator('#settings-update-time').fill('09:00')
        page.locator('#schedule-form button[type="submit"]').click()
        expect(page.locator('#schedule-feedback')).to_contain_text('today at 09:00')
        go(page,'home')
        expect(page.locator('#daily-word')).to_have_text(before['word']+'.')
        check(state(page)['updateTime']=='09:00','Settings can change the rollover and consistently recalculate the current word')
        page.reload(wait_until='networkidle')
        expect(page.locator('#daily-word')).to_have_text(before['word']+'.')
        check(state(page)['updateTime']=='09:00','Chosen time survives reload')
        go(page,'settings')
        page.locator('#settings-update-time').fill('08:00')
        page.locator('#schedule-form button[type="submit"]').click()
        go(page,'home')
        expect(page.locator('#daily-word')).to_have_text(after['word']+'.')
        page.wait_for_timeout(750)
        page.locator('[data-action="hide-word"]').click()
        page.wait_for_timeout(60)
        check(page.locator('.word-stage').evaluate('e=>e.getAnimations().length>0'),'The card uses an actual 3D flip animation')
        expect(page.locator('#recall-form')).to_be_visible()
        page.wait_for_timeout(400)

        for width,height in ((1440,1000),(768,1024),(390,844),(320,740)):
            page.set_viewport_size({'width':width,'height':height})
            for theme,animation in (('noir','word-in'),('studio','studio-word'),('experimental','signal-word')):
                go(page,'settings')
                page.locator(f'[data-theme-choice="{theme}"]').click()
                no_overflow(page,f'{theme} schedule settings fit {width}px')
                go(page,'home')
                expect(page.locator('#recall-form')).to_be_visible()
                no_overflow(page,f'{theme} recall card fits {width}px')
                if theme=='studio' and width in (1440,390):
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(OUTPUT/f'v2-recall-{width}.png'))
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('#recall-title').dblclick()
        expect(page.locator('#daily-word')).to_be_visible()
        for theme,animation in (('noir','word-in'),('studio','studio-word'),('experimental','signal-word')):
            go(page,'settings')
            page.locator(f'[data-theme-choice="{theme}"]').click()
            go(page,'home')
            check(page.locator('#daily-word').evaluate('e=>getComputedStyle(e).animationName')==animation,f'{theme} has its own word reveal animation')
        page.locator('[data-action="hide-word"]').click()
        expect(page.locator('#recall-form')).to_be_visible()
        page.wait_for_timeout(400)
        page.emulate_media(reduced_motion='reduce')
        page.locator('#recall-title').dblclick()
        expect(page.locator('#daily-word')).to_be_visible()
        check(page.locator('#daily-word').evaluate('e=>getComputedStyle(e).animationName')=='none','Reduced motion also applies to the new word animations')
        page.locator('[data-action="hide-word"]').click()
        expect(page.locator('#recall-form')).to_be_visible()
        check(page.locator('.word-stage').evaluate('e=>e.getAnimations().length')==0,'Reduced-motion users can flip without a 3D animation')
        check(not errors,'No uncaught JavaScript errors in the new user flows')

        instants=['2026-10-19T01:59:00Z','2026-10-19T02:00:00Z','2026-03-08T06:59:00Z','2026-03-08T07:00:00Z','2026-11-01T05:29:00Z','2026-11-01T05:30:00Z','2026-11-01T06:10:00Z','2026-11-01T06:30:00Z','2026-03-29T00:59:00Z','2026-03-29T01:01:00Z','2026-10-25T00:31:00Z','2026-10-25T01:10:00Z','2026-10-03T15:29:00Z','2026-10-03T15:30:00Z','2026-01-01T00:00:00Z']
        cases=[]
        for zone in ('UTC','Asia/Bishkek','Asia/Kathmandu','America/New_York','Europe/London','Europe/Berlin','Australia/Lord_Howe','Pacific/Chatham'):
            for update in ('00:00','01:30','02:15','02:30','08:00'):
                for instant in instants:
                    expected=daily_schedule(datetime.fromisoformat(instant.replace('Z','+00:00')),zone,update)
                    cases.append({'zone':zone,'update':update,'instant':instant,'expected':expected})
        mismatches=page.evaluate('''async cases=>{
          const {dailySchedule}=await import('/static/js/schedule.js');
          return cases.filter(c=>{const actual=dailySchedule(c.zone,c.update,new Date(c.instant));return actual.date!==c.expected.date||actual.calendarDate!==c.expected.calendarDate||Date.parse(actual.nextUpdateAt)!==Date.parse(c.expected.nextUpdateAt)}).slice(0,3);
        }''',cases)
        check(not mismatches,f'Python/browser schedules match in {len(cases)} timezone and DST cases: {mismatches}')
        context.close()

        browser=p.chromium.launch(executable_path=executable,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,timezone_id='Asia/Tokyo',service_workers='block',reduced_motion='reduce')
        page=context.new_page()
        fixture.authenticate(context,{'onboarded':True,'interests':['ielts'],'theme':'studio'})
        page.goto(BASE,wait_until='networkidle')
        word=page.locator('#daily-word').inner_text()
        box=page.locator('#daily-word').bounding_box()
        x,y=box['x']+box['width']/2,box['y']+box['height']/2
        page.touchscreen.tap(x,y)
        check(page.locator('#daily-word').count()==1,'A single touch does not flip the word')
        page.touchscreen.tap(x,y)
        expect(page.locator('#recall-form')).to_be_visible()
        box=page.locator('#recall-title').bounding_box()
        x,y=box['x']+box['width']/2,box['y']+box['height']/2
        page.touchscreen.tap(x,y)
        page.touchscreen.tap(x,y)
        expect(page.locator('#daily-word')).to_have_text(word)
        check(True,'Real touch pointer events hide and reveal the card with two taps')
        go(page,'settings')
        check('Asia/Tokyo' in page.locator('#schedule-form').inner_text(),'Timezone follows a device outside Bishkek')
        context.close()

        # Fresh onboarding remains usable with nine categories and time controls.
        context=browser.new_context(viewport={'width':320,'height':740},service_workers='block',reduced_motion='reduce')
        fixture.authenticate(context)
        page=context.new_page()
        page.goto(BASE,wait_until='networkidle')
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(page.locator('#onboarding-dialog').evaluate('e=>e.scrollWidth<=e.clientWidth'),'Onboarding has no horizontal overflow at 320px')
        page.locator('input[name="onboarding"][value="culture"]').check()
        page.locator('#begin-button').click()
        expect(page.locator('#daily-word')).to_be_visible()
        check(True,'A new category and schedule can be selected in mobile onboarding')
        context.close()
        browser.close()
        fixture.dispose()
    (OUTPUT/'v2-results.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2),encoding='utf-8')
    print(f'\n{len(checks)} V2 browser checks passed.',flush=True)


if __name__=='__main__':run()
