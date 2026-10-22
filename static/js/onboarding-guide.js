import {icon} from './icons.js';
import {validUpdateTime} from './schedule.js';

const copy={
  ru:{title:'Ваш ритм. Ваши интересы.',subtitle:'Два небольших шага, чтобы начать.',timeTitle:'Когда менять слово?',timeBody:'Выберите удобное время, когда слово будет меняться. Мы учитываем часовой пояс вашего устройства.',timeLegend:'Время обновления',timeNote:'Новое слово появится при следующем открытии LEXI после этого времени.',at:'НОВОЕ СЛОВО В',timezone:'ЧАСОВОЙ ПОЯС УСТРОЙСТВА',travel:'Следует за устройством, когда вы путешествуете.',collectionsTitle:'Что вам интересно?',collectionsBody:'Выберите одну или несколько коллекций. Из этих тем LEXI будет подбирать ваше ежедневное слово.',pick:'Можно выбрать несколько тем.',next:'Далее',back:'Назад',note:'Настройки можно будет изменить позже.',selected:n=>`Выбрано коллекций: ${n}.`,settingsTitle:'Всё можно изменить',settingsBody:'Нажмите на шестерёнку, чтобы в любой момент изменить время обновления и выбранные коллекции.',done:'Понятно'},
  kk:{title:'Өз ырғағыңыз. Өз қызығушылықтарыңыз.',subtitle:'Бастау үшін екі шағын қадам.',timeTitle:'Сөз қашан ауыссын?',timeBody:'Сөз ауысатын ыңғайлы уақытты таңдаңыз. Құрылғыңыздың уақыт белдеуі ескеріледі.',timeLegend:'Жаңару уақыты',timeNote:'Осы уақыттан кейін LEXI-ді келесі рет ашқанда жаңа сөз көрсетіледі.',at:'ЖАҢА СӨЗ УАҚЫТЫ',timezone:'ҚҰРЫЛҒЫНЫҢ УАҚЫТ БЕЛДЕУІ',travel:'Сапар кезінде құрылғыңыздың уақыт белдеуіне бейімделеді.',collectionsTitle:'Сізге не қызық?',collectionsBody:'Бір немесе бірнеше топтаманы таңдаңыз. LEXI күнделікті сөзді осы тақырыптардан ұсынады.',pick:'Бірнеше тақырып таңдауға болады.',next:'Келесі',back:'Артқа',note:'Баптауларды кейін өзгертуге болады.',selected:n=>`Таңдалған топтамалар: ${n}.`,settingsTitle:'Бәрін өзгертуге болады',settingsBody:'Жаңару уақытын және таңдалған топтамаларды кез келген уақытта өзгерту үшін тісті дөңгелек белгісін басыңыз.',done:'Түсінікті'},
  en:{title:'Your rhythm. Your interests.',subtitle:'Two small steps to make LEXI yours.',timeTitle:'When should your word change?',timeBody:'Choose a convenient time for your word to change. We use your device’s timezone.',timeLegend:'Your daily rhythm',timeNote:'Your next visit after this time applies the new word.',at:'A NEW WORD AT',timezone:'YOUR DEVICE TIMEZONE',travel:'Follows your device when you travel.',collectionsTitle:'What interests you?',collectionsBody:'Choose one or more collections. LEXI will find your daily word in these topics.',pick:'Choose one or more. Follow your curiosity.',next:'Next',back:'Back',note:'You can change these settings later.',selected:n=>`${n} collections selected.`,settingsTitle:'Make changes anytime',settingsBody:'Use the gear button whenever you want to change your daily time or chosen collections.',done:'Got it'},
};

export function createOnboardingGuide({dialog,account,getState,saveState}) {
  const $=selector=>dialog.querySelector(selector);
  const language=$('#onboarding-language'),content=$('.onboarding-content');
  const time=$('#onboarding-time'),topics=$('#onboarding-topics'),coach=$('#onboarding-coach');
  const back=$('#onboarding-back'),next=$('#onboarding-next'),begin=$('#begin-button');
  const hint=document.querySelector('#settings-guide-dialog'),hintCircle=hint.querySelector('.guide-circle');
  const media=matchMedia('(prefers-reduced-motion: reduce)');
  let step=null,scope=null,motion=null,hintScheduled=false,hintTarget=null,placeholder=null,targetStyle='',targetLabel='',hintScope=null,hintGeneration=0;
  const lang=()=>Object.hasOwn(copy,getState().guideLanguage)?getState().guideLanguage:'en';
  const text=()=>copy[lang()];
  const reduced=()=>media.matches||getState().reduceMotion;
  const selected=()=>[...dialog.querySelectorAll('input[name="onboarding"]:checked')].map(input=>input.value);
  const value=()=>$('#onboarding-update-time')?.value;
  function stopMotion(){motion?.cancel();motion=null;}
  function moveCircle(previous) {
    stopMotion();
    if(reduced()||!coach.animate)return;
    const current=coach.getBoundingClientRect();
    motion=coach.animate([
      {opacity:previous?.width ? .7 : 0,transform:previous?.width?`translate(${previous.left-current.left}px,${previous.top-current.top}px) scale(.96)`:'translateY(22px) scale(.86)'},
      {opacity:1,transform:'translate(0,0) scale(1)'},
    ],{duration:480,easing:'cubic-bezier(.22,1,.36,1)'});
    motion.finished.catch(()=>{});
  }
  function mute(node,value){node.classList.toggle('guide-muted',value);node.inert=value;if(value)node.setAttribute('aria-hidden','true');else node.removeAttribute('aria-hidden');}
  function syncControls() {
    const valid=validUpdateTime(value());
    next.disabled=!valid;
    begin.disabled=!valid||!selected().length;
    if(step==='collections')$('#onboarding-data-note').textContent=text().selected(selected().length);
  }
  function translate(t) {
    dialog.lang=lang();
    $('#onboarding-title').textContent=t.title;$('.onboarding-subtitle').textContent=t.subtitle;
    time.querySelector('legend').textContent=t.timeLegend;time.querySelector(':scope>p').textContent=t.timeNote;
    $('#onboarding-collections-title').textContent=t.collectionsTitle;$('.onboarding-prompt>span').textContent=t.pick;
    $('#onboarding-schedule label>.micro').textContent=t.at;
    $('#onboarding-schedule .schedule-timezone .micro').textContent=t.timezone;
    $('#onboarding-schedule .schedule-timezone>div>span:last-child').textContent=t.travel;
    back.textContent=t.back;next.innerHTML=`${t.next} ${icon('arrow')}`;begin.innerHTML=`${t.next} ${icon('arrow')}`;
    $('#onboarding-data-note').textContent=t.note;
  }
  function render(newStep,{animate=true}={}) {
    const changed=step!==newStep||scope!==account.scope;
    const previous=!coach.hidden&&changed?coach.getBoundingClientRect():null;
    scope=account.scope;step=newStep;dialog.classList.add('is-guided');dialog.dataset.guideStep=step;
    const choosing=step==='language';language.hidden=!choosing;content.hidden=choosing;
    coach.hidden=choosing;back.hidden=false;next.hidden=step!=='time';begin.hidden=step!=='collections';
    $('#onboarding-guest-exit').hidden=true;
    if(choosing){dialog.lang='en';dialog.setAttribute('aria-labelledby','guide-language-title');}
    else {
      const t=text();translate(t);
      mute(time,step!=='time');mute(topics,step!=='collections');mute($('.guide-chrome'),true);
      coach.innerHTML=`<span class="guide-number">${step==='time'?'01':'02'} / 02</span><span class="guide-orbit" aria-hidden="true">${icon(step==='time'?'clock':'grid')}</span><h2 id="guide-step-title" tabindex="-1"></h2><p></p>`;
      coach.querySelector('h2').textContent=step==='time'?t.timeTitle:t.collectionsTitle;
      coach.querySelector('p').textContent=step==='time'?t.timeBody:t.collectionsBody;
      dialog.setAttribute('aria-labelledby','guide-step-title');syncControls();
    }
    if(!dialog.open)dialog.showModal();
    if(changed) {
      if(step==='collections')(innerWidth<=600?coach:topics).scrollIntoView({block:'start',behavior:'instant'});
      else dialog.scrollTo({top:0,behavior:'instant'});
      if(choosing)$('#guide-language-title').focus({preventScroll:true});
      else {
        if(animate)moveCircle(previous);
        (step==='time'?$('#onboarding-update-time'):coach.querySelector('h2')).focus({preventScroll:true});
      }
    }
  }
  function useGuest() {
    stopMotion();step=null;scope=account.scope;
    dialog.classList.remove('is-guided');delete dialog.dataset.guideStep;dialog.lang='en';
    language.hidden=true;content.hidden=false;coach.hidden=true;next.hidden=true;back.hidden=true;begin.hidden=false;
    for(const node of [time,topics,$('.guide-chrome')])mute(node,false);
    translate(copy.en);$('#onboarding-title').textContent='Welcome to LEXI.';$('.onboarding-subtitle').textContent='Words that match your world.';
    begin.innerHTML=`Discover my word ${icon('arrow')}`;
    dialog.setAttribute('aria-labelledby','onboarding-title');
  }
  dialog.addEventListener('click',event=>{
    if(account.isGuest)return;
    const languageButton=event.target.closest('[data-guide-language]');
    if(languageButton) {
      const code=languageButton.dataset.guideLanguage;if(!Object.hasOwn(copy,code))return;
      saveState({guideLanguage:code,guideStep:'time'});render('time');
    } else if(event.target.closest('#onboarding-next')&&step==='time'&&validUpdateTime(value())) {
      saveState({updateTime:value(),guideStep:'collections'});render('collections');
    } else if(event.target.closest('#onboarding-back')) {
      const previous=step==='collections'?'time':'language';
      saveState({guideStep:previous});render(previous);
    }
  });
  dialog.addEventListener('input',event=>{
    if(account.isGuest||!dialog.classList.contains('is-guided'))return;
    if(event.target.id==='onboarding-update-time'){if(validUpdateTime(value()))saveState({updateTime:value()});syncControls();}
  });
  dialog.addEventListener('change',event=>{
    if(account.isGuest||!dialog.classList.contains('is-guided'))return;
    if(event.target.name==='onboarding'){saveState({interests:selected()});syncControls();}
  });
  function restoreTarget() {
    if(hintTarget){hintTarget.classList.remove('guide-settings-target');hintTarget.style.cssText=targetStyle;hintTarget.setAttribute('aria-label',targetLabel);if(placeholder?.isConnected)placeholder.replaceWith(hintTarget);else hintTarget.remove();}
    hintTarget=null;placeholder=null;hintScope=null;
  }
  function positionHint() {
    if(!hint.open||!placeholder)return;
    const target=placeholder.getBoundingClientRect();
    Object.assign(hintTarget.style,{position:'fixed',left:`${target.left}px`,top:`${target.top}px`,width:`${target.width}px`,height:`${target.height}px`,minWidth:'0',minHeight:'0'});
    const width=hintCircle.getBoundingClientRect().width;
    const left=Math.max(16,Math.min(innerWidth-width-16,target.left+target.width/2-width/2));
    const top=Math.max(16,Math.min(innerHeight-width-16,target.bottom+34));
    Object.assign(hintCircle.style,{left:`${left}px`,top:`${top}px`});
    const endX=target.left+target.width/2,endY=target.bottom+7,startX=left+width/2,startY=top+7;
    hint.querySelector('path').setAttribute('d',`M ${startX} ${startY} Q ${startX} ${(startY+endY)/2} ${endX} ${endY} M ${endX-5} ${endY+8} L ${endX} ${endY} L ${endX+5} ${endY+8}`);
  }
  function finishHint(openSettings=false) {
    if(!hint.open)return;
    const target=hintTarget,owned=hintScope===account.scope&&account.hasAccess;
    if(owned)saveState({guideStep:'done'});
    restoreTarget();hint.close();
    if(owned){if(openSettings)location.hash='settings';else target?.focus({preventScroll:true});}
  }
  function resumeSettingsHint() {
    const state=getState();
    if(hint.open||hintScheduled||account.isGuest||!account.hasAccess||!state.onboarded||state.guideStep!=='settings'||!state.guideLanguage)return;
    const owner=account.scope,generation=hintGeneration;hintScheduled=true;
    requestAnimationFrame(()=>{
      if(generation!==hintGeneration)return;
      hintScheduled=false;
      if(owner!==account.scope||!account.hasAccess||getState().guideStep!=='settings'||dialog.open)return;
      hintTarget=document.querySelector('.settings-link');if(!hintTarget)return;
      const t=text();hint.lang=lang();hintScope=owner;
      targetStyle=hintTarget.style.cssText;targetLabel=hintTarget.getAttribute('aria-label')||'Settings';
      placeholder=document.createElement('span');placeholder.className='icon-button guide-settings-placeholder';placeholder.setAttribute('aria-hidden','true');
      hintTarget.replaceWith(placeholder);hint.append(hintTarget);hintTarget.classList.add('guide-settings-target');hintTarget.setAttribute('aria-label',t.settingsTitle);
      hint.querySelector('#guide-settings-title').textContent=t.settingsTitle;hint.querySelector('#guide-settings-copy').textContent=t.settingsBody;
      hint.querySelector('#guide-settings-done').textContent=t.done;
      hint.showModal();positionHint();hint.querySelector('h2').focus({preventScroll:true});
      if(!reduced())hintCircle.animate([{opacity:0,transform:'translateY(18px) scale(.88)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:480,easing:'cubic-bezier(.22,1,.36,1)'});
    });
  }
  hint.addEventListener('click',event=>{if(event.target.closest('#guide-settings-done'))finishHint();else if(event.target.closest('.guide-settings-target')){event.preventDefault();finishHint(true);}});
  hint.addEventListener('cancel',event=>{event.preventDefault();finishHint();});
  hint.addEventListener('close',()=>{if(!hint.open)restoreTarget();});
  window.addEventListener('lexi:accountchange',()=>{
    if((scope&&scope!==account.scope)||(hintScope&&hintScope!==account.scope)) {
      ++hintGeneration;hintScheduled=false;stopMotion();step=null;scope=null;
      restoreTarget();if(hint.open)hint.close();
    }
  });
  window.addEventListener('resize',positionHint);
  media.addEventListener('change',()=>{if(media.matches){stopMotion();hintCircle.getAnimations().forEach(animation=>animation.cancel());}});
  return {
    open(){if(account.isGuest){useGuest();return;}const state=getState();render(!state.guideLanguage||state.guideStep==='language'?'language':state.guideStep==='collections'?'collections':'time');},
    useGuest,resumeSettingsHint,
    get active(){return !account.isGuest&&dialog.classList.contains('is-guided');},
    canComplete(){return step==='collections'&&validUpdateTime(value())&&selected().length>0;},
    cancel(){++hintGeneration;stopMotion();step=null;scope=null;hintScheduled=false;restoreTarget();if(hint.open)hint.close();},
  };
}
