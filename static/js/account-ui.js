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
  let mode='login', file=null, preview='', headerKey='', authBusy=false;
  let drafts={login:{},register:{}}, draftScope=account.scope, authAnimations=[], motionGeneration=0;
  const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
  function stopAuthMotion() {
    ++motionGeneration;
    authAnimations.forEach(animation=>animation.cancel());authAnimations=[];
    entry.classList.remove('auth-switching');dialog.classList.remove('auth-switching');
  }
  function clearAuthDrafts() {
    drafts={login:{},register:{}};
    for(const surface of [entry,dialog])surface.querySelector('#account-auth-form')?.reset();
  }
  function positionAuthIndicator(surface) {
    const active=surface.querySelector('.account-tabs>button[aria-pressed=true]');
    const indicator=surface.querySelector('.account-tab-indicator');
    if(active&&indicator){indicator.style.left=`${active.offsetLeft}px`;indicator.style.width=`${active.offsetWidth}px`;}
  }
  function sizeAuthCard(surface) {
    if(!surface.querySelector('#account-auth-form')||!surface.getBoundingClientRect().width)return;
    surface.classList.add('auth-card');
    // Measure the longer form at the actual width, including fonts and wrapping.
    const measure=surface.cloneNode(true);
    measure.classList.remove('auth-switching');measure.inert=true;measure.setAttribute('aria-hidden','true');
    measure.querySelector('#account-auth-form').outerHTML=authForm(true);
    measure.removeAttribute('id');measure.querySelectorAll('[id]').forEach(node=>node.removeAttribute('id'));
    Object.assign(measure.style,{position:'fixed',inset:'0 auto auto 0',display:'block',visibility:'hidden',pointerEvents:'none',margin:'0',width:`${surface.getBoundingClientRect().width}px`,height:'auto',minHeight:'0',maxHeight:'none'});
    surface.after(measure);
    const height=measure.getBoundingClientRect().height;
    measure.remove();
    const maximum=parseFloat(getComputedStyle(surface).maxHeight)||Infinity;
    surface.style.minHeight=`${Math.min(height,maximum)}px`;
  }
  function releaseAuthCard() {dialog.classList.remove('auth-card');dialog.style.minHeight='';}
  function animateAuth(surface,previous,view) {
    if(!previous||reducedMotion.matches||document.documentElement.classList.contains('reduce-motion')||!surface.animate)return;
    const options={duration:340,easing:'cubic-bezier(.22,1,.36,1)'};
    const indicator=surface.querySelector('.account-tab-indicator');
    const nextIndicator=indicator.getBoundingClientRect();
    surface.classList.add('auth-switching');
    authAnimations=[
      surface.querySelector('#account-auth-form').animate([{opacity:0,transform:`translateX(${view==='register'?18:-18}px)`},{opacity:1,transform:'translateX(0)'}],options),
    ];
    if(previous.indicator&&nextIndicator.width)authAnimations.push(indicator.animate([
      {transform:`translateX(${previous.indicator.left-nextIndicator.left}px) scaleX(${previous.indicator.width/nextIndicator.width})`},
      {transform:'translateX(0) scaleX(1)'},
    ],options));
    for(const node of surface.querySelectorAll('#account-title,.account-intro'))authAnimations.push(node.animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],options));
    const generation=motionGeneration;
    Promise.allSettled(authAnimations.map(animation=>animation.finished)).then(()=>{
      if(generation===motionGeneration)stopAuthMotion();
    });
  }
  function clearPhoto(){file=null;if(preview)URL.revokeObjectURL(preview);preview='';}
  const initials=()=>escape(account.user?.username.slice(0,2).toUpperCase()||'LX');
  const statusLabel=()=>({synced:'Your learning data is up to date.',syncing:'Saving your latest discoveries…',offline:'Saved on this device. Reconnect to sync.',expired:'Sign in again to sync your changes.'}[account.status]||'Your words, saved to your account.');

  function header() {
    const user=account.user;
    const key=JSON.stringify([user?.id,user?.username,user?.avatarUrl,account.isGuest]);
    if(key===headerKey)return;headerKey=key;
    const button=$('#account-button');
    button.setAttribute('aria-label',user?`${user.username} — Your account`:account.isGuest?'Guest visit — account options':'Sign in or create an account');
    button.innerHTML=`<span class="header-avatar">${user?.avatarUrl?`<img src="${escape(user.avatarUrl)}" alt="">`:user?initials():icon('user')}</span><span class="account-label">${user?escape(user.username):account.isGuest?'Guest':'Account'}</span>`;
  }

  function authForm(register) {
    return `<form id="account-auth-form" class="account-auth-form">${register?`<label>Username<input name="username" autocomplete="username" required minlength="3" maxlength="30" pattern="[A-Za-z0-9_]{3,30}" placeholder="Your login name" aria-describedby="username-help"></label><p id="username-help" class="account-field-help">3–30 letters, numbers, or underscores.</p><label>Email<input name="email" type="email" autocomplete="email" required maxlength="254" placeholder="you@example.com"></label>`:`<label>Email or username<input name="identifier" autocomplete="username" required maxlength="254" placeholder="Your email or login name"></label>`}<label for="account-password">Password</label><div class="account-password-row"><input id="account-password" name="password" type="password" autocomplete="${register?'new-password':'current-password'}" required ${register?'minlength="10"':''} maxlength="128" placeholder="${register?'Create a password':'Your password'}"><button type="button" class="icon-button" data-account-action="password" aria-label="Show password">${icon('eye')}</button></div>${register?`<p class="account-field-help">10–128 characters. Use a password you don’t use elsewhere.</p>`:''}<p id="account-error" class="account-error" role="alert"></p><button type="submit" class="button button-primary account-submit" ${navigator.onLine?'':'disabled'}>${register?'Create my account':'Sign in'} ${icon('arrow')}</button><p class="account-offline" ${navigator.onLine?'hidden':''}>Go online to sign in or create an account.</p><p id="entry-session-status" class="entry-session-status" role="status"></p></form>`;
  }

  function auth(view='login',{animate=false}={}) {
    const surface=account.hasAccess?dialog:entry;
    const form=surface.querySelector('#account-auth-form');
    if(form&&animate&&view===mode)return;
    if(form)drafts[mode]=Object.fromEntries(new FormData(form));
    const previous=form&&animate?{indicator:surface.querySelector('.account-tab-indicator')?.getBoundingClientRect()}:null;
    const keepFocus=!!document.activeElement?.closest('.account-tabs');
    stopAuthMotion();mode=view;clearPhoto();
    const register=view==='register';
    surface.innerHTML=`${surface===dialog?`<button class="icon-button dialog-close" data-account-action="close" aria-label="Close account">${icon('close')}</button>`:''}<span class="eyebrow">YOUR PERSONAL CORNER OF LEXI</span><h2 id="account-title" class="auth-copy"><span>${register?'A new chapter.':'Welcome back.'}</span><span class="auth-copy-measure" aria-hidden="true">${register?'Welcome back.':'A new chapter.'}</span></h2><p class="account-intro auth-copy"><span>${register?'Make your daily ritual yours.':'Your words. Your world. Right where you left them.'}</span><span class="auth-copy-measure" aria-hidden="true">${register?'Your words. Your world. Right where you left them.':'Make your daily ritual yours.'}</span></p><div class="account-tabs" role="group" aria-label="Account action"><button data-account-action="login-tab" aria-pressed="${!register}">Sign in</button><button data-account-action="register-tab" aria-pressed="${register}">Create account</button></div>${authForm(register)}<p class="account-privacy auth-copy"><span>${register?'Your email is private. Your progress follows you when you sign in on another device.':'Sign in to continue your daily ritual. Your progress is waiting for you.'}</span><span class="auth-copy-measure" aria-hidden="true">${register?'Sign in to continue your daily ritual. Your progress is waiting for you.':'Your email is private. Your progress follows you when you sign in on another device.'}</span></p>`;
    if(surface===entry) {
      const guest=document.createElement('div');guest.className='account-guest';
      guest.innerHTML=`<button type="button" class="button button-outline" data-account-action="guest" aria-describedby="guest-help">Continue as guest ${icon('arrow')}</button><p id="guest-help">No account needed. Progress disappears when you sign out, reload, or close this tab.</p>`;
      surface.querySelector('.account-privacy').before(guest);
    }
    const nextForm=surface.querySelector('#account-auth-form');
    for(const [name,value] of Object.entries(drafts[view]))if(nextForm.elements.namedItem(name))nextForm.elements.namedItem(name).value=value;
    const indicator=document.createElement('span');indicator.className='account-tab-indicator';indicator.setAttribute('aria-hidden','true');
    surface.querySelector('.account-tabs').append(indicator);sizeAuthCard(surface);positionAuthIndicator(surface);
    animateAuth(surface,previous,view);
    if(keepFocus)surface.querySelector(`.account-tabs>[data-account-action="${view}-tab"]`).focus({preventScroll:true});
    authAvailability();
    if(surface===entry)document.title=register?'Create your account — LEXI':'Sign in — LEXI';
  }

  function profile() {
    stopAuthMotion();releaseAuthCard();
    const user=account.user;
    if(!user){auth();return;}
    dialog.innerHTML=`<button class="icon-button dialog-close" data-account-action="close" aria-label="Close account">${icon('close')}</button><span class="eyebrow">YOUR PERSONAL CORNER OF LEXI</span><h2 id="account-title">Hello, ${escape(user.username)}<span class="accent">.</span></h2><p class="account-intro">A little more you. A little more knowledge.</p><div class="profile-summary" data-profile-owner="${user.id}"><div class="profile-avatar">${preview||user.avatarUrl?`<img id="profile-photo-preview" src="${escape(preview||user.avatarUrl)}" alt="Your profile photo">`:`<span>${initials()}</span>`}</div><div class="profile-identity"><strong>${escape(user.username)}</strong><span>${escape(user.email)}</span><p id="account-sync-status" class="account-sync-status" role="status">${statusLabel()}</p></div></div><form id="profile-photo-form"><label class="button button-outline photo-picker">${icon('camera')}Choose photo<input id="profile-photo-input" name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="account-field-help">JPG, PNG, or WebP · up to 5 MB · up to 16 megapixels</p><div class="photo-actions"><button type="submit" class="button button-primary" ${file?'':'disabled'}>Save photo ${icon('check')}</button>${user.avatarUrl?`<button type="button" class="text-link" data-account-action="remove-photo">Remove photo ${icon('trash')}</button>`:''}</div><p id="account-error" class="account-error" role="alert"></p></form><div class="profile-learning"><span class="micro">YOUR GROWING WORLD</span><p>Saved words, history, interests, appearance, daily time, and memory cards are linked to this account.</p></div><div class="profile-bottom"><button class="text-link" data-account-action="logout">Sign out ${icon('logout')}</button><button class="button button-outline" data-account-action="close">Keep exploring ${icon('arrow')}</button></div>`;
  }

  function guestProfile() {
    stopAuthMotion();releaseAuthCard();
    clearPhoto();
    dialog.innerHTML=`<button class="icon-button dialog-close" data-account-action="close" aria-label="Close account">${icon('close')}</button><span class="eyebrow">A LITTLE LOOK AROUND</span><h2 id="account-title">Hello, curious guest<span class="accent">.</span></h2><p class="account-intro">Your words are here for this visit.</p><div class="profile-learning"><span class="micro">TEMPORARY PROGRESS</span><p>History, saved words, interests, settings, and card positions disappear when you sign out, reload, or close this tab.</p><p>Sign in or create an account for your own lasting progress. Guest progress will not be transferred.</p></div><div class="guest-account-actions"><button class="button button-primary" data-account-action="register-tab">Create account ${icon('arrow')}</button><button class="button button-outline" data-account-action="login-tab">Sign in</button></div><p id="account-error" class="account-error" role="alert"></p><div class="profile-bottom"><button class="text-link" data-account-action="guest-exit">Exit guest mode ${icon('logout')}</button><button class="button button-outline" data-account-action="close">Keep exploring ${icon('arrow')}</button></div>`;
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
    const guest=entry.querySelector('[data-account-action="guest"]');
    if(guest)guest.disabled=authBusy||!account.ready||!navigator.onLine;
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
    $('#guest-banner').hidden=!account.isGuest;
    if(allowed) {
      if(wasGated){stopAuthMotion();clearAuthDrafts();entry.replaceChildren();window.scrollTo({top:0,behavior:'instant'});}
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
    if(account.user){profile();syncStatus();}else if(account.isGuest&&view!=='register')guestProfile();else auth(view);
    if(!dialog.open)dialog.showModal();
    sizeAuthCard(dialog);positionAuthIndicator(dialog);
  }

  document.addEventListener('click',async event=>{
    const themeButton=event.target.closest('[data-entry-theme-choice]');
    if(themeButton){chooseEntryTheme(themeButton.dataset.entryThemeChoice);return;}
    const target=event.target.closest('[data-account-action]');
    if(!target||target.disabled)return;
    const action=target.dataset.accountAction;
    if(authBusy&&['guest','login-tab','register-tab'].includes(action))return;
    if(action==='open'||action==='open-register'){open(action==='open-register'?'register':'login');return;}
    if(action==='close'){dialog.close();return;}
    if(action==='reauth'){auth('login');return;}
    if(action==='login-tab'||action==='register-tab'){auth(action==='login-tab'?'login':'register',{animate:true});return;}
    if(action==='password'){
      const input=$('#account-password');input.type=input.type==='password'?'text':'password';
      target.setAttribute('aria-label',input.type==='password'?'Show password':'Hide password');return;
    }
    if(action==='guest') {
      const form=$('#account-auth-form');authBusy=true;
      if(form)busy(form,true);
      target.disabled=true;target.setAttribute('aria-busy','true');error('');
      try {await account.enterGuest(entryTheme);toast('Welcome, guest. Your progress lasts for this visit only.');}
      catch(failure){error(failure.message||'Connect and try again.');}
      finally {authBusy=false;if(form)busy(form,false);target.removeAttribute('aria-busy');target.disabled=false;authAvailability();}
      return;
    }
    if(action==='guest-exit'&&account.isGuest) {
      target.disabled=true;
      await account.logout();clearPhoto();dialog.close();
      toast('Guest visit ended. Your guest progress has been cleared.');return;
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
      if(authBusy)return;
      const values=new FormData(form), register=mode==='register', fromEntry=entry.contains(form);
      authBusy=true;busy(form,true);error('');authAvailability();
      try {
        if(register)await account.register({username:values.get('username'),email:values.get('email'),password:values.get('password')},entryTheme);
        else await account.login({identifier:values.get('identifier'),password:values.get('password')});
        form.reset();clearAuthDrafts();stopAuthMotion();
        toast(register?'Welcome to your own little world of words.':'Welcome back. Your words are here.');
        if(!fromEntry){if(!readStore().onboarded)dialog.close();else profile();}
      } catch(failure){error(failure.message||'Your account could not be reached. Please try again.');busy(form,false);}
      finally {authBusy=false;authAvailability();}
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
  dialog.addEventListener('close',()=>{clearPhoto();clearAuthDrafts();stopAuthMotion();if(account.hasAccess&&!readStore().onboarded)openOnboarding();});
  window.addEventListener('lexi:accountchange',()=>{
    if(draftScope!==account.scope){draftScope=account.scope;clearAuthDrafts();stopAuthMotion();}
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
  function resizeAuthCards(){for(const surface of [entry,dialog]){sizeAuthCard(surface);positionAuthIndicator(surface);}}
  window.addEventListener('resize',resizeAuthCards);
  document.fonts.ready.then(resizeAuthCards);
  reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches)stopAuthMotion();});
  window.addEventListener('pagehide',()=>{clearAuthDrafts();stopAuthMotion();});
  $('#entry-motion-toggle').addEventListener('click',event=>{
    const paused=screen.classList.toggle('is-paused');
    const button=event.currentTarget;
    button.setAttribute('aria-pressed',String(paused));
    button.innerHTML=paused?'Resume background <span aria-hidden="true">▷</span>':'Pause background <span aria-hidden="true">Ⅱ</span>';
  });
  chooseEntryTheme(entryTheme,{persist:false});auth('register');syncAccess();header();
}
