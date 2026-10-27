import {icon} from './icons.js';
import {validUpdateTime} from './schedule.js';
import {createReadingGuide} from './reading-guide.js';

const copy={
  ru:{title:'Ваш ритм. Ваши интересы.',subtitle:'Два небольших шага, чтобы начать.',timeTitle:'Когда менять слово?',timeBody:'Выберите удобное время, когда слово будет меняться. Мы учитываем часовой пояс вашего устройства.',timeLegend:'Время обновления',timeNote:'Новое слово появится при следующем открытии LEXI после этого времени.',at:'НОВОЕ СЛОВО В',timezone:'ЧАСОВОЙ ПОЯС УСТРОЙСТВА',travel:'Следует за устройством, когда вы путешествуете.',collectionsTitle:'Что вам интересно?',collectionsBody:'Выберите одну или несколько коллекций. Из этих тем LEXI будет подбирать ваше ежедневное слово.',pick:'Можно выбрать несколько тем.',next:'Далее',back:'Назад',note:'Настройки можно будет изменить позже.',selected:n=>`Выбрано коллекций: ${n}.`,wordTitle:'Слово дня',wordBody:'Это слово дня. Оно меняется каждый день в выбранное вами время.',settingsTitle:'Всё можно изменить',settingsBody:'Нажмите на шестерёнку, чтобы в любой момент изменить время обновления и выбранные коллекции.',done:'Понятно'},
  kk:{title:'Өз ырғағыңыз. Өз қызығушылықтарыңыз.',subtitle:'Бастау үшін екі шағын қадам.',timeTitle:'Сөз қашан ауыссын?',timeBody:'Сөз ауысатын ыңғайлы уақытты таңдаңыз. Құрылғыңыздың уақыт белдеуі ескеріледі.',timeLegend:'Жаңару уақыты',timeNote:'Осы уақыттан кейін LEXI-ді келесі рет ашқанда жаңа сөз көрсетіледі.',at:'ЖАҢА СӨЗ УАҚЫТЫ',timezone:'ҚҰРЫЛҒЫНЫҢ УАҚЫТ БЕЛДЕУІ',travel:'Сапар кезінде құрылғыңыздың уақыт белдеуіне бейімделеді.',collectionsTitle:'Сізге не қызық?',collectionsBody:'Бір немесе бірнеше топтаманы таңдаңыз. LEXI күнделікті сөзді осы тақырыптардан ұсынады.',pick:'Бірнеше тақырып таңдауға болады.',next:'Келесі',back:'Артқа',note:'Баптауларды кейін өзгертуге болады.',selected:n=>`Таңдалған топтамалар: ${n}.`,wordTitle:'Күн сөзі',wordBody:'Бұл — күн сөзі. Ол күн сайын сіз таңдаған уақытта жаңарады.',settingsTitle:'Бәрін өзгертуге болады',settingsBody:'Жаңару уақытын және таңдалған топтамаларды кез келген уақытта өзгерту үшін тісті дөңгелек белгісін басыңыз.',done:'Түсінікті'},
  en:{title:'Your rhythm. Your interests.',subtitle:'Two small steps to make LEXI yours.',timeTitle:'When should your word change?',timeBody:'Choose a convenient time for your word to change. We use your device’s timezone.',timeLegend:'Your daily rhythm',timeNote:'Your next visit after this time applies the new word.',at:'A NEW WORD AT',timezone:'YOUR DEVICE TIMEZONE',travel:'Follows your device when you travel.',collectionsTitle:'What interests you?',collectionsBody:'Choose one or more collections. LEXI will find your daily word in these topics.',pick:'Choose one or more. Follow your curiosity.',next:'Next',back:'Back',note:'You can change these settings later.',selected:n=>`${n} collections selected.`,wordTitle:'Your word of the day',wordBody:'This is your word of the day. It changes every day at your chosen time.',settingsTitle:'Make changes anytime',settingsBody:'Use the gear button whenever you want to change your daily time or chosen collections.',done:'Got it'},
};

export function createOnboardingGuide({dialog,account,getState,saveState,getWord,saveWord,navigate}) {
  const $=selector=>dialog.querySelector(selector);
  const language=$('#onboarding-language'),content=$('.onboarding-content');
  const time=$('#onboarding-time'),topics=$('#onboarding-topics'),coach=$('#onboarding-coach');
  const coachSlot=$('#onboarding-coach-slot'),coachStyle=coach.style.cssText;
  const pointer=$('.guide-pointer'),pointerPath=pointer.querySelector('.guide-pointer-line'),pointerHead=pointer.querySelector('.guide-pointer-head');
  const back=$('#onboarding-back'),next=$('#onboarding-next'),begin=$('#begin-button');
  const hint=document.querySelector('#settings-guide-dialog'),hintCircle=hint.querySelector('.guide-circle');
  const reading=createReadingGuide({hint,account,getState,saveState,getWord,saveWord,navigate});
  const media=matchMedia('(prefers-reduced-motion: reduce)');
  let step=null,scope=null,motion=null,motionFrame=0,motionScrollTo=null,pointerFrame=0,pointerAnimations=[],hintScheduled=false,hintTarget=null,placeholder=null,targetStyle='',targetLabel='',hintScope=null,hintGeneration=0,hintMode=null,hintMoving=false,hintAnimations=[],wordSpotlight=null;
  const lang=()=>Object.hasOwn(copy,getState().guideLanguage)?getState().guideLanguage:'en';
  const text=()=>copy[lang()];
  const reduced=()=>media.matches||getState().reduceMotion;
  const selected=()=>[...dialog.querySelectorAll('input[name="onboarding"]:checked')].map(input=>input.value);
  const value=()=>$('#onboarding-update-time')?.value;
  function stopPointer(){pointerAnimations.forEach(animation=>animation.cancel());pointerAnimations=[];}
  function stopMotion({finish=false}={}) {
    cancelAnimationFrame(motionFrame);motionFrame=0;motion?.cancel();motion=null;
    coach.style.cssText=coachStyle;
    if(finish&&motionScrollTo!==null)dialog.scrollTop=motionScrollTo;
    motionScrollTo=null;stopPointer();pointer.style.opacity='1';
  }
  function drawPointer() {
    stopPointer();
    if(reduced()||pointer.hasAttribute('hidden')||!pointerPath.animate)return;
    pointerAnimations=[
      pointerPath.animate([{strokeDashoffset:'1'},{strokeDashoffset:'0'}],{duration:600,easing:'cubic-bezier(.42,0,.58,1)'}),
      pointerHead.animate([{opacity:0},{opacity:1}],{duration:180,delay:480,fill:'backwards',easing:'cubic-bezier(.42,0,.58,1)'}),
    ];
    pointerAnimations.forEach(animation=>animation.finished.catch(()=>{}));
  }
  function positionPointer() {
    if(!dialog.open||coach.hidden||account.isGuest||!['time','collections'].includes(step)){pointer.setAttribute('hidden','');return;}
    const bubble=coach.getBoundingClientRect(),bounds=dialog.getBoundingClientRect();
    const target=(step==='time'?$('#onboarding-update-time'):$('.onboarding-prompt')).getBoundingClientRect();
    const narrow=innerWidth<=600;
    const frame=time.getBoundingClientRect();
    let end=narrow?{x:target.left+target.width/2,y:(step==='time'?frame.top:target.top)-12}:
      {x:step==='time'?frame.left-10:target.right+12,y:target.top+target.height/2};
    const center={x:bubble.left+bubble.width/2,y:bubble.top+bubble.height/2};
    const angle=Math.atan2(end.y-center.y,end.x-center.x),radius=bubble.width/2+8;
    let start={x:center.x+Math.cos(angle)*radius,y:center.y+Math.sin(angle)*radius};
    let line,lastControl;
    if(step==='collections') {
      start={x:center.x,y:bubble.bottom+8};
      if(narrow) {
        const gap=end.y-start.y;
        // A single soft bend fits the mobile gap without a decorative loop.
        lastControl={x:end.x+6,y:end.y-gap*.35};
        line=`M ${start.x} ${start.y} C ${start.x+6} ${start.y+gap*.35}, ${lastControl.x} ${lastControl.y}, ${end.x} ${end.y}`;
      } else {
        // Stay below the circle and beside the cards, clear of both outlines.
        const floor=$('.onboarding-bottom').getBoundingClientRect().top-20;
        const room=Math.min(180,Math.max(0,floor-start.y));
        end={x:target.right+12,y:start.y+room*.66};
        lastControl={x:end.x+Math.min(36,(start.x-end.x)*.5),y:end.y};
        line=`M ${start.x} ${start.y} C ${start.x} ${start.y+room*.5}, ${lastControl.x} ${lastControl.y}, ${end.x} ${end.y}`;
      }
    } else {
      const bend=Math.max(18,Math.min(80,Math.hypot(end.x-start.x,end.y-start.y)*.55));
      const c1={x:start.x+Math.cos(angle)*bend,y:start.y+Math.sin(angle)*bend};
      lastControl=narrow?{x:end.x,y:end.y-bend}:{x:end.x-bend,y:end.y};
      line=`M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${lastControl.x} ${lastControl.y}, ${end.x} ${end.y}`;
    }
    // Keep the decorative line inside the visible dialog; it never takes a click.
    const floor=$('.onboarding-bottom').getBoundingClientRect().top;
    const outside=end.y<bounds.top+8||end.y>Math.min(bounds.bottom-8,floor-12)||end.x<bounds.left+8||end.x>bounds.right-8||start.y>floor-32;
    pointer.toggleAttribute('hidden',outside);
    if(outside)return;
    pointer.style.clipPath=`inset(${Math.max(0,bounds.top+1)}px ${Math.max(0,innerWidth-bounds.right+1)}px ${Math.max(0,innerHeight-bounds.bottom+1)}px ${Math.max(0,bounds.left+1)}px)`;
    const heading=Math.atan2(end.y-lastControl.y,end.x-lastControl.x),head=5.5,spread=.52;
    pointerPath.setAttribute('d',line);
    pointerHead.setAttribute('d',`M ${end.x-head*Math.cos(heading-spread)} ${end.y-head*Math.sin(heading-spread)} L ${end.x} ${end.y} L ${end.x-head*Math.cos(heading+spread)} ${end.y-head*Math.sin(heading+spread)}`);
  }
  function queuePointer(){if(!motion&&!pointerFrame)pointerFrame=requestAnimationFrame(()=>{pointerFrame=0;positionPointer();});}
  function moveCircle(previous,scrollFrom,scrollTo) {
    stopMotion();
    if(reduced()||!coach.animate){positionPointer();return;}
    // Scroll and travel share one clock, so the panel does not jump underneath the circle.
    const destination=coachSlot.getBoundingClientRect();
    if(previous?.width)dialog.scrollTop=scrollFrom;
    scrollFrom=dialog.scrollTop;
    const travelling=!!previous?.width;
    if(travelling)Object.assign(coach.style,{position:'fixed',left:`${destination.left}px`,top:`${destination.top}px`,width:`${destination.width}px`,height:`${destination.height}px`,transformOrigin:'top left'});
    // A fixed circle follows one continuous path, independent of sticky layout and scrolling.
    const animation=coach.animate(travelling?[
      {transform:`translate(${previous.left-destination.left}px,${previous.top-destination.top}px) scale(${previous.width/destination.width},${previous.height/destination.height})`,opacity:previous.opacity},
      {transform:'translate(0,0) scale(1)',opacity:1},
    ]:[{opacity:0,transform:'translateY(16px) scale(.96)'},{opacity:1,transform:'translateY(0) scale(1)'}],
    {duration:travelling?(step==='collections'?650:1200):800,easing:'cubic-bezier(.42,0,.58,1)'});
    motion=animation;motionScrollTo=scrollTo;
    let pointerStarted=false;
    const follow=()=>{
      if(motion!==animation)return;
      const progress=animation.effect.getComputedTiming().progress??0;
      if(scrollFrom!==scrollTo)dialog.scrollTop=scrollFrom+(scrollTo-scrollFrom)*progress;
      pointer.style.opacity=progress>.94?'1':'0';
      positionPointer();
      if(progress>.94&&!pointerStarted){pointerStarted=true;drawPointer();}
      motionFrame=requestAnimationFrame(follow);
    };
    follow();
    animation.finished.then(()=>{
      if(motion!==animation)return;
      cancelAnimationFrame(motionFrame);motionFrame=0;motion=null;motionScrollTo=null;
      dialog.scrollTop=scrollTo;coach.style.cssText=coachStyle;pointer.style.opacity='1';positionPointer();
      if(!pointerStarted)drawPointer();
    }).catch(()=>{});
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
    const previous=!coach.hidden&&changed?Object.assign(coach.getBoundingClientRect(),{opacity:Number(getComputedStyle(coach).opacity)}):null;
    const scrollFrom=dialog.scrollTop;
    if(changed)stopMotion();
    scope=account.scope;step=newStep;dialog.classList.add('is-guided');dialog.dataset.guideStep=step;
    const choosing=step==='language';language.hidden=!choosing;content.hidden=choosing;
    coachSlot.hidden=choosing;coach.hidden=choosing;back.hidden=false;next.hidden=step!=='time';begin.hidden=step!=='collections';
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
        if(animate)moveCircle(previous,scrollFrom,dialog.scrollTop);
        (step==='time'?$('#onboarding-update-time'):coach.querySelector('h2')).focus({preventScroll:true});
      }
    }
    positionPointer();
  }
  function useGuest() {
    stopMotion();pointer.setAttribute('hidden','');step=null;scope=account.scope;
    dialog.classList.remove('is-guided');delete dialog.dataset.guideStep;dialog.lang='en';
    language.hidden=true;content.hidden=false;coachSlot.hidden=true;coach.hidden=true;next.hidden=true;back.hidden=true;begin.hidden=false;
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
  function stopHintAnimations(){hintAnimations.forEach(animation=>animation.cancel());hintAnimations=[];}
  function restoreTarget() {
    stopHintAnimations();
    if(hintTarget){hintTarget.classList.remove('guide-settings-target');hintTarget.style.cssText=targetStyle;hintTarget.setAttribute('aria-label',targetLabel);if(placeholder?.isConnected)placeholder.replaceWith(hintTarget);else hintTarget.remove();}
    wordSpotlight?.remove();wordSpotlight=null;
    hintTarget=null;placeholder=null;hintScope=null;hintMode=null;hintMoving=false;
    hint.classList.remove('is-word-guide');delete hint.dataset.guidePhase;
    hint.querySelector('#guide-settings-done').disabled=false;
  }
  function wordSource(){return ['', '#home'].includes(location.hash)?document.querySelector('#main-content #daily-word'):null;}
  function glyphBounds(source){const range=document.createRange();range.selectNodeContents(source);return range.getBoundingClientRect();}
  function positionWord(ensureVisible=false) {
    const source=wordSource();if(!source||!wordSpotlight)return false;
    const width=hintCircle.getBoundingClientRect().width;
    const landscape=innerWidth>=560&&innerHeight<=560;
    let glyph=glyphBounds(source);
    if(ensureVisible){
      const top=landscape?Math.max(24,(innerHeight-glyph.height)/2):Math.max(24,Math.min(120,innerHeight-width-glyph.height-64));
      window.scrollBy({top:glyph.top-top,behavior:'instant'});glyph=glyphBounds(source);
    }
    const box=source.getBoundingClientRect(),style=getComputedStyle(source);
    wordSpotlight.textContent=source.textContent;
    Object.assign(wordSpotlight.style,{left:`${box.left}px`,top:`${box.top}px`,width:`${box.width}px`,height:`${box.height}px`});
    for(const property of ['fontFamily','fontSize','fontWeight','fontStyle','letterSpacing','lineHeight','whiteSpace','overflowWrap','wordBreak','paddingBottom'])wordSpotlight.style[property]=style[property];
    if(landscape){
      // Measure a single line, even when a long source word wraps on the page.
      const available=innerWidth-width-72;
      Object.assign(wordSpotlight.style,{left:'24px',width:`${available}px`,height:'auto',paddingBottom:'0',whiteSpace:'nowrap'});
      const scale=Math.min(1,available/Math.max(1,glyphBounds(wordSpotlight).width));
      Object.assign(wordSpotlight.style,{fontSize:`${parseFloat(style.fontSize)*scale}px`,lineHeight:`${parseFloat(style.lineHeight)*scale}px`,letterSpacing:`${(parseFloat(style.letterSpacing)||0)*scale}px`});
      wordSpotlight.style.top=`${Math.max(16,(innerHeight-wordSpotlight.getBoundingClientRect().height)/2)}px`;
      Object.assign(hintCircle.style,{left:`${innerWidth-width-24}px`,top:`${(innerHeight-width)/2}px`});
      return true;
    }
    const left=Math.max(16,Math.min(innerWidth-width-16,glyph.left+glyph.width/2-width/2));
    Object.assign(hintCircle.style,{left:`${left}px`,top:`${glyph.bottom+24}px`});
    return true;
  }
  function positionHint() {
    if(!hint.open)return;
    if(hintMode==='word'){positionWord();return;}
    if(!placeholder)return;
    const target=placeholder.getBoundingClientRect();
    Object.assign(hintTarget.style,{position:'fixed',left:`${target.left}px`,top:`${target.top}px`,width:`${target.width}px`,height:`${target.height}px`,minWidth:'0',minHeight:'0'});
    const width=hintCircle.getBoundingClientRect().width;
    const landscape=innerWidth>=560&&innerHeight<=560;
    const left=Math.max(16,Math.min(innerWidth-width-16,landscape?target.left-width-48:target.left+target.width/2-width/2));
    const top=landscape?(innerHeight-width)/2:Math.max(16,Math.min(innerHeight-width-16,target.bottom+48));
    Object.assign(hintCircle.style,{left:`${left}px`,top:`${top}px`});
    const center={x:left+width/2,y:top+width/2};
    const gear={x:target.left+target.width/2,y:target.top+target.height/2};
    const distance=Math.hypot(gear.x-center.x,gear.y-center.y);
    const direction={x:(gear.x-center.x)/distance,y:(gear.y-center.y)/distance};
    const start={x:center.x+direction.x*(width/2+8),y:center.y+direction.y*(width/2+8)};
    // Stop outside the gear's elliptical outline and its eight-pixel halo.
    const gearRadius=1/Math.hypot(direction.x/(target.width/2),direction.y/(target.height/2))+14;
    const end={x:gear.x-direction.x*gearRadius,y:gear.y-direction.y*gearRadius};
    const length=distance-width/2-8-gearRadius;
    const bend=Math.min(8,Math.max(0,length)*.18);
    const control={x:(start.x+end.x)/2-direction.y*bend,y:(start.y+end.y)/2+direction.x*bend};
    const angle=Math.atan2(end.y-control.y,end.x-control.x),head=5.5,spread=.52;
    hint.querySelector('path').setAttribute('d',length<16?'':`M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y} M ${end.x-head*Math.cos(angle-spread)} ${end.y-head*Math.sin(angle-spread)} L ${end.x} ${end.y} L ${end.x-head*Math.cos(angle+spread)} ${end.y-head*Math.sin(angle+spread)}`);
  }
  function showWordHint(owner) {
    if(owner!==account.scope||!account.hasAccess||account.isGuest||getState().guideStep!=='word'||!wordSource())return false;
    // Settle the underlying entrance/flip before measuring the highlighted word.
    for(const node of [wordSource(),wordSource().closest('.word-stage'),document.querySelector('#main-content')]){
      for(const animation of node?.getAnimations()||[])if(animation.playState==='running'&&Number.isFinite(animation.effect.getComputedTiming().endTime))animation.finish();
    }
    const t=text();hintScope=owner;hintMode='word';hint.lang=lang();hint.dataset.guidePhase='word';hint.classList.add('is-word-guide');
    hint.querySelector('.guide-number').textContent='LEXI / WORD OF THE DAY';
    hint.querySelector('#guide-settings-title').textContent=t.wordTitle;hint.querySelector('#guide-settings-copy').textContent=t.wordBody;
    hint.querySelector('#guide-settings-done').textContent=t.next;
    wordSpotlight=document.createElement('h1');wordSpotlight.id='guide-daily-word';wordSpotlight.className='guide-word-spotlight';
    hint.insertBefore(wordSpotlight,hintCircle);
    if(!hint.open)hint.showModal();
    positionWord(true);hint.querySelector('h2').focus({preventScroll:true});
    if(!reduced()){
      hintAnimations=[
        hintCircle.animate([{opacity:0,transform:'translateY(12px) scale(.97)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:520,easing:'cubic-bezier(.42,0,.58,1)'}),
        wordSpotlight.animate([{opacity:0},{opacity:1}],{duration:650,easing:'cubic-bezier(.42,0,.58,1)'}),
      ];
      hintAnimations.forEach(animation=>animation.finished.catch(()=>{}));
    }
    return true;
  }
  async function finishHint(openSettings=false) {
    if(!hint.open||hintMoving||hintScope!==account.scope||!account.hasAccess)return;
    const owner=hintScope,generation=hintGeneration,word=hintMode==='word';
    hintMoving=true;hint.querySelector('#guide-settings-done').disabled=true;
    saveState({guideStep:word?'definition':'word'});
    const fading=[hintCircle,word?wordSpotlight:hint.querySelector('.guide-settings-arrow')].filter(Boolean).map(node=>({node,opacity:getComputedStyle(node).opacity,transform:getComputedStyle(node).transform}));
    stopHintAnimations();
    if(!reduced()){
      hintAnimations=fading.map(({node,opacity,transform})=>node.animate([{opacity,transform},{opacity:0,transform}],{duration:360,easing:'cubic-bezier(.42,0,.58,1)',fill:'forwards'}));
      await Promise.all(hintAnimations.map(animation=>animation.finished.catch(()=>{})));
    }
    if(generation!==hintGeneration||owner!==account.scope||!account.hasAccess||!hint.open)return;
    restoreTarget();
    if(word){reading.resume();return;}
    if(openSettings){
      hint.close();location.hash='settings';
      return;
    }
    if(!['', '#home'].includes(location.hash))location.hash='home';
    if(!showWordHint(owner))hint.close();
  }
  function resumeSettingsHint() {
    if(hintMoving)return;
    if(reading.resume())return;
    const state=getState();
    if(hint.open||hintScheduled||account.isGuest||!account.hasAccess||!state.onboarded||!['settings','word'].includes(state.guideStep)||!state.guideLanguage)return;
    if(state.guideStep==='word'&&!wordSource())return;
    const owner=account.scope,generation=hintGeneration;hintScheduled=true;
    requestAnimationFrame(()=>{
      if(generation!==hintGeneration)return;
      hintScheduled=false;
      if(owner!==account.scope||!account.hasAccess||dialog.open)return;
      if(getState().guideStep==='word'){showWordHint(owner);return;}
      if(getState().guideStep!=='settings')return;
      hintTarget=document.querySelector('.settings-link');if(!hintTarget)return;
      const t=text();hint.lang=lang();hintScope=owner;hintMode='settings';hint.dataset.guidePhase='settings';
      targetStyle=hintTarget.style.cssText;targetLabel=hintTarget.getAttribute('aria-label')||'Settings';
      placeholder=document.createElement('span');placeholder.className='icon-button guide-settings-placeholder';placeholder.setAttribute('aria-hidden','true');
      hintTarget.replaceWith(placeholder);hint.append(hintTarget);hintTarget.classList.add('guide-settings-target');hintTarget.setAttribute('aria-label',t.settingsTitle);
      hint.querySelector('.guide-number').textContent='LEXI / SETTINGS';
      hint.querySelector('#guide-settings-title').textContent=t.settingsTitle;hint.querySelector('#guide-settings-copy').textContent=t.settingsBody;
      hint.querySelector('#guide-settings-done').textContent=t.next;
      hint.showModal();positionHint();hint.querySelector('h2').focus({preventScroll:true});
      if(!reduced()){
        hintAnimations=[hintCircle.animate([{opacity:0,transform:'translateY(16px) scale(.96)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:800,easing:'cubic-bezier(.42,0,.58,1)'})];
        hintAnimations.forEach(animation=>animation.finished.catch(()=>{}));
      }
    });
  }
  function refreshHint() {
    if(reading.active){reading.refresh();return;}
    if(hintMoving)return;
    if(reading.resume())return;
    if(hint.open&&hintMode==='word'){
      if(hintScope!==account.scope||getState().guideStep!=='word'||!wordSource()){restoreTarget();hint.close();return;}
      positionWord(true);
    } else if(getState().guideStep==='word')resumeSettingsHint();
  }
  hint.addEventListener('click',event=>{if(event.target.closest('#guide-settings-done')){if(reading.active)reading.next();else finishHint();}else if(event.target.closest('.guide-settings-target')){event.preventDefault();finishHint(true);}});
  hint.addEventListener('cancel',event=>{event.preventDefault();if(reading.active)reading.next();else finishHint();});
  hint.addEventListener('close',()=>{if(!hint.open)restoreTarget();});
  window.addEventListener('lexi:accountchange',()=>{
    if((scope&&scope!==account.scope)||(hintScope&&hintScope!==account.scope)) {
      ++hintGeneration;hintScheduled=false;stopMotion();step=null;scope=null;
      restoreTarget();if(hint.open)hint.close();
    }
  });
  dialog.addEventListener('scroll',queuePointer,{passive:true});
  dialog.addEventListener('close',()=>{if(!dialog.open){stopMotion();pointer.setAttribute('hidden','');}});
  window.addEventListener('resize',()=>{stopMotion();queuePointer();requestAnimationFrame(()=>{if(hintMode==='word')positionWord(true);else positionHint();});});
  window.addEventListener('scroll',positionHint,{passive:true});
  media.addEventListener('change',()=>{if(media.matches){stopMotion({finish:true});queuePointer();hintCircle.getAnimations().forEach(animation=>animation.cancel());stopHintAnimations();}});
  return {
    open(){if(account.isGuest){useGuest();return;}const state=getState();render(!state.guideLanguage||state.guideStep==='language'?'language':state.guideStep==='collections'?'collections':'time');},
    useGuest,resumeSettingsHint,refresh:refreshHint,
    get active(){return !account.isGuest&&dialog.classList.contains('is-guided');},
    canComplete(){return step==='collections'&&validUpdateTime(value())&&selected().length>0;},
    cancel(){reading.cancel();++hintGeneration;stopMotion();pointer.setAttribute('hidden','');step=null;scope=null;hintScheduled=false;restoreTarget();if(hint.open)hint.close();},
  };
}
