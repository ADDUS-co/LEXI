import {icon} from './icons.js';
import {readStore} from './storage.js';

const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=selector=>document.querySelector(selector);

export function installAccountUI(account,{toast,openOnboarding}) {
  const dialog=$('#account-dialog');
  const entry=$('#auth-entry'), screen=$('#auth-screen'), shell=$('#learning-app');
  let gated=true;
  let entryTheme=document.documentElement.dataset.entryTheme||'studio';
  const entryColors={noir:'#101312',studio:'#eeeee8',experimental:'#0a0d23'};
  function chooseEntryTheme(theme,{persist=true}={}) {
    if(!Object.hasOwn(entryColors,theme))return;
    entryTheme=theme;document.documentElement.dataset.entryTheme=theme;
    screen.querySelectorAll('[data-entry-theme-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.entryThemeChoice===theme)));
    if(persist)try{localStorage.setItem('lexi:entry-theme',theme);}catch{}
    if(gated)document.querySelector('meta[name=theme-color]').setAttribute('content',entryColors[theme]);
  }
  let mode='login', file=null, preview='', headerKey='';
  function clearPhoto(){file=null;if(preview)URL.revokeObjectURL(preview);preview='';}
  const initials=()=>escape(account.user?.username.slice(0,2).toUpperCase()||'LX');
  const statusLabel=()=>({synced:'Your learning data is up to date.',syncing:'Saving your latest discoveries…',offline:'Saved on this device. Reconnect to sync.',expired:'Sign in again to sync your changes.'}[account.status]||'Your words, saved to your account.');

  function header() {
    const user=account.user;
    const key=JSON.stringify([user?.id,user?.username,user?.avatarUrl]);
    if(key===headerKey)return;headerKey=key;
    const button=$('#account-button');
    button.setAttribute('aria-label',user?`${user.username} — Your account`:'Sign in or create an account');
    button.innerHTML=`<span class="header-avatar">${user?.avatarUrl?`<img src="${escape(user.avatarUrl)}" alt="">`:user?initials():icon('user')}</span><span class="account-label">${user?escape(user.username):'Account'}</span>`;
  }

  function auth(view='login') {
    mode=view;clearPhoto();
    const register=view==='register';
    const surface=account.hasAccess?dialog:entry;
    surface.innerHTML=`${surface===dialog?`<button class="icon-button dialog-close" data-account-action="close" aria-label="Close account">${icon('close')}</button>`:''}<span class="eyebrow">YOUR PERSONAL CORNER OF LEXI</span><h2 id="account-title">${register?'A new chapter.':'Welcome back.'}</h2><p class="account-intro">${register?'Make your daily ritual yours.':'Your words. Your world. Right where you left them.'}</p><div class="account-tabs" role="group" aria-label="Account action"><button data-account-action="login-tab" aria-pressed="${!register}">Sign in</button><button data-account-action="register-tab" aria-pressed="${register}">Create account</button></div><form id="account-auth-form">${register?`<label>Username<input name="username" autocomplete="username" required minlength="3" maxlength="30" pattern="[A-Za-z0-9_]{3,30}" placeholder="Your login name" aria-describedby="username-help"></label><p id="username-help" class="account-field-help">3–30 letters, numbers, or underscores.</p><label>Email<input name="email" type="email" autocomplete="email" required maxlength="254" placeholder="you@example.com"></label>`:`<label>Email or username<input name="identifier" autocomplete="username" required maxlength="254" placeholder="Your email or login name"></label>`}<label for="account-password">Password</label><div class="account-password-row"><input id="account-password" name="password" type="password" autocomplete="${register?'new-password':'current-password'}" required ${register?'minlength="10"':''} maxlength="128" placeholder="${register?'Create a password':'Your password'}"><button type="button" class="icon-button" data-account-action="password" aria-label="Show password">${icon('eye')}</button></div>${register?`<p class="account-field-help">10–128 characters. Use a password you don’t use elsewhere.</p>`:''}<p id="account-error" class="account-error" role="alert"></p><button type="submit" class="button button-primary account-submit" ${navigator.onLine?'':'disabled'}>${register?'Create my account':'Sign in'} ${icon('arrow')}</button><p class="account-offline" ${navigator.onLine?'hidden':''}>Go online to sign in or create an account.</p><p id="entry-session-status" class="entry-session-status" role="status"></p></form><p class="account-privacy">${register?'Your email is private. Your progress follows you when you sign in on another device.':'Sign in to continue your daily ritual. Your progress is waiting for you.'}</p>`;
    authAvailability();
    if(surface===entry)document.title=register?'Create your account — LEXI':'Sign in — LEXI';
  }

  function profile() {
    const user=account.user;
    if(!user){auth();return;}
    dialog.innerHTML=`<button class="icon-button dialog-close" data-account-action="close" aria-label="Close account">${icon('close')}</button><span class="eyebrow">YOUR PERSONAL CORNER OF LEXI</span><h2 id="account-title">Hello, ${escape(user.username)}<span class="accent">.</span></h2><p class="account-intro">A little more you. A little more knowledge.</p><div class="profile-summary" data-profile-owner="${user.id}"><div class="profile-avatar">${preview||user.avatarUrl?`<img id="profile-photo-preview" src="${escape(preview||user.avatarUrl)}" alt="Your profile photo">`:`<span>${initials()}</span>`}</div><div class="profile-identity"><strong>${escape(user.username)}</strong><span>${escape(user.email)}</span><p id="account-sync-status" class="account-sync-status" role="status">${statusLabel()}</p></div></div><form id="profile-photo-form"><label class="button button-outline photo-picker">${icon('camera')}Choose photo<input id="profile-photo-input" name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="account-field-help">JPG, PNG, or WebP · up to 5 MB · up to 16 megapixels</p><div class="photo-actions"><button type="submit" class="button button-primary" ${file?'':'disabled'}>Save photo ${icon('check')}</button>${user.avatarUrl?`<button type="button" class="text-link" data-account-action="remove-photo">Remove photo ${icon('trash')}</button>`:''}</div><p id="account-error" class="account-error" role="alert"></p></form><div class="profile-learning"><span class="micro">YOUR GROWING WORLD</span><p>Saved words, history, interests, appearance, daily time, and memory cards are linked to this account.</p></div><div class="profile-bottom"><button class="text-link" data-account-action="logout">Sign out ${icon('logout')}</button><button class="button button-outline" data-account-action="close">Keep exploring ${icon('arrow')}</button></div>`;
  }

  function error(message){const node=$('#account-error');if(node)node.textContent=message;}
  function syncStatus() {
    const node=$('#account-sync-status');
    if(!node)return;
    node.textContent=statusLabel();
    if(account.status==='expired') {
      const button=document.createElement('button');
      button.className='text-link';button.dataset.accountAction='reauth';
      button.textContent='Sign in again';node.append(' ',button);
    }
  }
  function authAvailability() {
    const form=$('#account-auth-form');
    if(!form||form.getAttribute('aria-busy')==='true')return;
    form.querySelector('[type=submit]').disabled=!account.ready||!navigator.onLine;
    const offline=form.querySelector('.account-offline');if(offline)offline.hidden=navigator.onLine;
    const status=form.querySelector('#entry-session-status');
    if(status)status.textContent=!account.ready?'Checking your session…':account.status==='expired'?'Your session ended. Sign in again to continue.':'';
  }
  function syncAccess() {
    const allowed=account.hasAccess;
    const wasGated=gated;gated=!allowed;
    document.documentElement.dataset.access=allowed?'granted':account.ready?'required':'pending';
    screen.hidden=allowed;shell.hidden=!allowed;shell.inert=!allowed;
    if(allowed) {
      if(wasGated){entry.replaceChildren();window.scrollTo({top:0,behavior:'instant'});}
    } else {
      if(dialog.open)dialog.close();
      dialog.replaceChildren();
      for(const id of ['onboarding-dialog','detail-dialog'])if($('#'+id).open)$('#'+id).close();
      if('speechSynthesis' in window)speechSynthesis.cancel();
      if(!wasGated)auth('login');
      chooseEntryTheme(entryTheme,{persist:false});
    }
    if(wasGated!==gated)window.dispatchEvent(new Event('lexi:accesschange'));
  }
  function busy(form,value){form.querySelectorAll('button,input').forEach(node=>node.disabled=value);form.setAttribute('aria-busy',String(value));}
  function open(view='login') {
    if(!account.hasAccess){auth(view);return;}
    if($('#onboarding-dialog').open)$('#onboarding-dialog').close();
    if(account.user){profile();syncStatus();}else auth(view);
    if(!dialog.open)dialog.showModal();
  }

  document.addEventListener('click',async event=>{
    const themeButton=event.target.closest('[data-entry-theme-choice]');
    if(themeButton){chooseEntryTheme(themeButton.dataset.entryThemeChoice);return;}
    const target=event.target.closest('[data-account-action]');
    if(!target||target.disabled)return;
    const action=target.dataset.accountAction;
    if(action==='open'||action==='open-register'){open(action==='open-register'?'register':'login');return;}
    if(action==='close'){dialog.close();return;}
    if(action==='reauth'){auth('login');return;}
    if(action==='login-tab'||action==='register-tab'){auth(action==='login-tab'?'login':'register');return;}
    if(action==='password'){
      const input=$('#account-password');input.type=input.type==='password'?'text':'password';
      target.setAttribute('aria-label',input.type==='password'?'Show password':'Hide password');return;
    }
    if(!account.user)return;
    target.disabled=true;error('');
    try {
      if(action==='logout'){await account.logout();clearPhoto();dialog.close();toast('Signed out. Your account words are safely stored.');}
      else if(action==='remove-photo'){await account.removePhoto();clearPhoto();profile();toast('Profile photo removed.');}
    } catch(failure){error(failure.message||'Reconnect and try again.');}
    finally {target.disabled=false;}
  });

  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(!['account-auth-form','profile-photo-form'].includes(form.id))return;
    event.preventDefault();
    if(form.id==='account-auth-form') {
      const values=new FormData(form), register=mode==='register', fromEntry=entry.contains(form);
      busy(form,true);error('');
      try {
        if(register)await account.register({username:values.get('username'),email:values.get('email'),password:values.get('password')},entryTheme);
        else await account.login({identifier:values.get('identifier'),password:values.get('password')});
        form.reset();
        toast(register?'Welcome to your own little world of words.':'Welcome back. Your words are here.');
        if(!fromEntry){if(!readStore().onboarded)dialog.close();else profile();}
      } catch(failure){error(failure.message||'Your account could not be reached. Please try again.');busy(form,false);authAvailability();}
    } else if(form.id==='profile-photo-form'&&file) {
      busy(form,true);error('');
      try {await account.uploadPhoto(file);clearPhoto();profile();toast('Your profile photo is ready.');}
      catch(failure){error(failure.message||'The photo could not be uploaded.');busy(form,false);}
    }
  });

  document.addEventListener('change',event=>{
    if(event.target.id!=='profile-photo-input')return;
    const chosen=event.target.files[0];
    if(!chosen)return;
    if(chosen.size>5*1024*1024||!['image/jpeg','image/png','image/webp'].includes(chosen.type)){error('Choose a JPG, PNG, or WebP image up to 5 MB.');return;}
    clearPhoto();file=chosen;preview=URL.createObjectURL(chosen);profile();
    $('#profile-photo-form button[type="submit"]').focus();
  });
  dialog.addEventListener('close',()=>{clearPhoto();if(account.hasAccess&&!readStore().onboarded)openOnboarding();});
  window.addEventListener('lexi:accountchange',()=>{
    syncAccess();header();authAvailability();
    if(dialog.open){
      const owner=$('[data-profile-owner]')?.dataset.profileOwner;
      if(account.user&&owner&&owner!==String(account.user.id))profile();
      else if(!account.user&&owner)auth();
      else syncStatus();
    }
  });
  window.addEventListener('online',authAvailability);
  window.addEventListener('offline',authAvailability);
  $('#entry-motion-toggle').addEventListener('click',event=>{
    const paused=screen.classList.toggle('is-paused');
    const button=event.currentTarget;
    button.setAttribute('aria-pressed',String(paused));
    button.innerHTML=paused?'Resume background <span aria-hidden="true">▷</span>':'Pause background <span aria-hidden="true">Ⅱ</span>';
  });
  chooseEntryTheme(entryTheme,{persist:false});auth('register');syncAccess();header();
}
