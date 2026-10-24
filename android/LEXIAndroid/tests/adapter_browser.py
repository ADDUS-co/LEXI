"""Exercise the Android adapter with the actual LEXI storage module and site CSP.

No accounts are created and no requests are sent to the production site.
Requires Playwright and Chromium; run from any working directory.
"""
from pathlib import Path
import json
import os
import shutil
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ORIGIN = 'https://lexi-m388.onrender.com'
ADAPTER = (ROOT / 'app/src/main/assets/lexi-android.js').read_text()
HTML = '''<!doctype html><html><body><main id="main-content">
<h1 id="daily-word">Perspective<span>.</span></h1>
<p class="short-definition">A particular way of understanding something.</p>
<button class="listen-button" data-action="pronounce">Listen</button>
<button data-action="share">Share</button>
<button data-action="save" data-word="ielts-perspective">Save</button>
<button data-action="export">Export</button>
<button data-action="hide-word">Turn over</button>
</main><div id="toast" hidden></div></body></html>'''


def run():
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context()

        def route(request):
            if request.request.url.endswith('/static/js/storage.js'):
                request.fulfill(status=200, content_type='text/javascript', body=(REPO / 'static/js/storage.js').read_text())
            else:
                request.fulfill(status=200, content_type='text/html', body=HTML, headers={
                    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
                })

        context.route('**/*', route)
        context.add_init_script('''window.nativeCalls=[];window.fallbacks=[];window.LexiAndroid={
          speak:v=>window.nativeCalls.push(['speak',v]),
          share:v=>window.nativeCalls.push(['share',v]),
          exportProgress:v=>window.nativeCalls.push(['export',v]),
          stopSpeech:()=>window.nativeCalls.push(['stop'])};''')
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(ORIGIN)
        page.evaluate("document.addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(b)window.fallbacks.push(b.dataset.action);})")
        page.evaluate(ADAPTER)
        page.evaluate(ADAPTER)
        page.locator('[data-action=pronounce]').click()
        assert page.evaluate("window.nativeCalls.filter(c=>c[0]==='speak')") == [['speak', 'Perspective']]
        assert page.evaluate('window.fallbacks') == []
        checks.append('Pronunciation is intercepted once and sends the visible word without its display period')
        page.locator('[data-action=share]').click()
        share = page.evaluate("window.nativeCalls.find(c=>c[0]==='share')[1]")
        assert 'Perspective: A particular way of understanding something.' in share
        assert share.endswith(ORIGIN + '/#word/ielts-perspective')
        checks.append('Sharing uses the current word and its public word link')
        page.evaluate('''async()=>{const storage=await import('/static/js/storage.js');storage.switchStore(17);storage.updateStore({saved:['ielts-perspective'],theme:'studio',onboarded:true});}''')
        page.locator('[data-action=export]').click()
        page.wait_for_function("window.nativeCalls.some(c=>c[0]==='export')")
        export = json.loads(page.evaluate("window.nativeCalls.find(c=>c[0]==='export')[1]"))
        assert export['app'] == 'LEXI' and export['preferences']['saved'] == ['ielts-perspective']
        assert export['preferences']['theme'] == 'studio' and 'password' not in export['preferences']
        checks.append('Export reads the actual account-scoped storage and includes no password')
        page.locator('[data-action=save]').click()
        assert page.evaluate('window.fallbacks') == ['save']
        checks.append('The website still receives its ordinary Save action')
        page.evaluate("window.dispatchEvent(new CustomEvent('lexi:android-speech',{detail:{speaking:true}}))")
        assert page.locator('.listen-button').evaluate("e=>e.classList.contains('is-speaking')")
        page.evaluate("window.dispatchEvent(new CustomEvent('lexi:android-speech',{detail:{speaking:false}}))")
        assert not page.locator('.listen-button').evaluate("e=>e.classList.contains('is-speaking')")
        checks.append('Native speech completion updates the website’s listening indicator')
        page.locator('[data-action=hide-word]').click()
        assert page.evaluate("window.nativeCalls.some(c=>c[0]==='stop')")
        assert page.evaluate('window.fallbacks') == ['save', 'hide-word']
        page.evaluate("document.querySelector('#daily-word').remove();window.nativeCalls=[]")
        page.wait_for_timeout(30)
        page.locator('[data-action=pronounce]').click()
        page.locator('[data-action=share]').click()
        assert not page.evaluate("window.nativeCalls.some(c=>['speak','share'].includes(c[0]))")
        checks.append('Turning the real word over stops speech and prevents speaking or sharing a hidden answer')
        page.goto('https://untrusted.example/')
        page.evaluate(ADAPTER)
        assert not page.evaluate('Boolean(window.__lexiAndroidAdapter)')
        checks.append('The adapter refuses to activate on a different origin')
        assert not errors, errors
        checks.append('No uncaught browser errors under the site’s existing CSP')
        context.close()
        browser.close()
    for check in checks:
        print('PASS', check, flush=True)
    print(f'All {len(checks)} Android adapter checks passed.', flush=True)


if __name__ == '__main__':
    run()
