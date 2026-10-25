"""Slow startup, bounded waits, and lost registration responses.

Use a disposable DATABASE_URL; creates two synthetic accounts. The network
fixture delays real requests or loses responses, without bypassing server auth.
"""
import os
from pathlib import Path
import secrets
import shutil

from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('LEXI_TEST_URL','http://127.0.0.1:5000').rstrip('/')
OUTPUT=Path(__file__).resolve().parents[1]/'test-results'
OUTPUT.mkdir(exist_ok=True)
checks=[]
PASSWORD='Synthetic-connection-password-42'

FIXTURE="""(()=>{
  const fetch=window.fetch.bind(window);
  const state=window.connectionFixture={mode:'',sessions:0,writes:0,pending:false};
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const hang=signal=>new Promise((resolve,reject)=>{
    state.pending=true;
    if(signal.aborted)reject(signal.reason);
    else signal.addEventListener('abort',()=>reject(signal.reason),{once:true});
  });
  window.fetch=async(input,options={})=>{
    const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
    if(path==='/api/account/session'){
      ++state.sessions;
      if(state.mode==='slow-session'&&state.sessions===1)await wait(9000);
      if(state.mode==='warmup'&&state.sessions<3)return new Response('<html>Starting</html>',{status:503,headers:{'Content-Type':'text/html'}});
      if(state.mode==='hang-session')return hang(options.signal);
    }
    if(path==='/api/account/register'){
      ++state.writes;
      if(state.mode==='slow-register')await wait(9000);
      if(state.mode==='hang-register')return hang(options.signal);
      if(state.mode==='html-register')return new Response('<html>Starting</html>',{headers:{'Content-Type':'text/html'}});
      if(state.mode==='lost-response'){
        const response=await fetch(input,options);
        await response.clone().json();
        throw new TypeError('Failed to fetch');
      }
    }
    return fetch(input,options);
  };
})();"""


def check(value,label):
    if not value:raise AssertionError(label)
    checks.append(label);print('PASS',label,flush=True)


def fill(page):
    username='Connection_'+secrets.token_hex(5)
    fields={'username':username,'email':username.lower()+'@example.com','password':PASSWORD}
    for name,value in fields.items():page.locator(f'input[name="{name}"]').fill(value)
    return fields


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        errors=[]

        def open_page(mode='',without_timeout=False):
            context=browser.new_context(viewport={'width':390,'height':844},service_workers='block',reduced_motion='reduce')
            script=FIXTURE+f"\nwindow.connectionFixture.mode={mode!r};"
            if without_timeout:script+="Object.defineProperty(AbortSignal,'timeout',{value:undefined,configurable:true});"
            context.add_init_script(script)
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(BASE,wait_until='domcontentloaded')
            return context,page

        context,page=open_page('slow-session')
        fields=fill(page)
        expect(page.locator('#entry-session-status')).to_contain_text('Connecting')
        expect(page.locator('.account-submit')).to_be_disabled()
        expect(page.locator('.account-submit')).to_be_enabled(timeout=15000)
        check(page.evaluate('connectionFixture.sessions')==1 and not page.locator('#entry-session-status').inner_text(),'A session taking nine seconds completes without a false timeout or duplicate request')
        check(all(page.locator(f'input[name="{name}"]').input_value()==value for name,value in fields.items()),'Fields typed while the host starts are preserved')
        page.evaluate("connectionFixture.mode='slow-register'")
        page.locator('.account-submit').click()
        expect(page.locator('#entry-session-status')).to_contain_text('Still connecting',timeout=7000)
        check(page.locator('.account-submit').is_disabled(),'A slow registration shows progress and prevents another submission')
        page.locator('#account-auth-form').evaluate("form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
        expect(page.locator('#onboarding-dialog')).to_be_visible(timeout=15000)
        check(page.evaluate('connectionFixture.writes')==1,'A registration taking nine seconds succeeds exactly once')
        check(context.request.get(BASE+'/api/account/session').json()['user']['username']==fields['username'],'The delayed registration creates the correct real account')
        context.close()

        context,page=open_page('warmup')
        fill(page)
        expect(page.locator('.account-submit')).to_be_enabled(timeout=12000)
        check(page.evaluate('connectionFixture.sessions')==3 and not page.locator('#entry-session-status').inner_text(),'Temporary HTML/503 warmup responses retry only the read-only session check')
        check(page.evaluate('connectionFixture.writes')==0,'Startup recovery never submits a registration')
        context.close()

        context,page=open_page(without_timeout=True)
        expect(page.locator('.account-submit')).to_be_enabled()
        page.locator('[data-account-action="guest"]').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(page.locator('#guest-banner').is_visible(),'Guest access works when AbortSignal.timeout is unavailable')
        context.close()

        for mode in ('hang-session','hang-register','html-register'):
            context,page=open_page()
            expect(page.locator('.account-submit')).to_be_enabled()
            fields=fill(page)
            page.clock.install()
            page.evaluate('mode=>connectionFixture.mode=mode',mode)
            page.locator('.account-submit').click()
            if mode.startswith('hang'):
                page.wait_for_function('connectionFixture.pending')
                page.clock.fast_forward(90001)
            expect(page.locator('#account-error')).not_to_be_empty()
            message=page.locator('#account-error').inner_text()
            check('signal timed out' not in message and 'Unexpected token' not in message,f'{mode}: transport failures produce a readable message')
            check(('Sign in' in message)==(mode!='hang-session'),f'{mode}: advice to check an existing account appears only after a registration was sent')
            expect(page.locator('.account-submit')).to_be_enabled()
            check(all(page.locator(f'input[name="{name}"]').input_value()==value for name,value in fields.items()),f'{mode}: failed requests keep the fields and restore the form')
            check(page.evaluate('connectionFixture.writes')==(0 if mode=='hang-session' else 1),f'{mode}: no automatic registration replay')
            context.close()

        context,page=open_page('lost-response')
        expect(page.locator('.account-submit')).to_be_enabled()
        fields=fill(page);page.locator('.account-submit').click()
        expect(page.locator('#account-error')).to_contain_text('Choose Sign in')
        check(context.request.get(BASE+'/api/account/session').json()['user']['username']==fields['username'],'A lost success response leaves the newly created account intact')
        check(page.evaluate('connectionFixture.writes')==1,'Losing the creation response never repeats the registration')
        page.screenshot(path=str(OUTPUT/'account-unconfirmed-mobile.png'),full_page=True)
        page.locator('[data-account-action="login-tab"]').click()
        page.locator('input[name="identifier"]').fill(fields['email'])
        page.locator('input[name="password"]').fill(PASSWORD)
        page.locator('.account-submit').click()
        expect(page.locator('#onboarding-dialog')).to_be_visible()
        check(context.request.get(BASE+'/api/account/session').json()['user']['username']==fields['username'],'Signing in after a lost creation response safely opens the same account')
        context.close();browser.close()
        check(not errors,'No uncaught JavaScript errors during startup, timeout, guest access, or recovery')
    print(f'All {len(checks)} account-connection checks passed.',flush=True)


if __name__=='__main__':run()
