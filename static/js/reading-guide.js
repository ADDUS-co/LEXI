import {icon} from './icons.js';
import {createRecallDemo} from './recall-demo.js';

const steps=['definition','synonyms','examples','deep','save','saved','recall'];
const copy={
  ru:{next:'Далее',done:'Понятно',show:'Показать сохранение',return:'Вернуться к слову',saving:'Сохраняем…',
    definition:['Что значит слово?','Здесь представлено краткое значение слова. Оно помогает быстро понять основную мысль.'],
    synonyms:['Близкие по смыслу','Здесь — синонимы. Они помогают увидеть оттенки значения. Позже можно нажать на любой из них и узнать больше.'],
    examples:['Слово в контексте','Это пример использования слова в предложении. Так легче понять, как применять его в речи.'],
    save:['Понравилось слово?','Его можно сохранить этой кнопкой. Сейчас LEXI сама добавит слово в Saved и покажет, где его найти.'],
    saved:['Слово сохранено','Вот оно в Saved! Слово останется в вашем аккаунте. Теперь вернёмся к слову и потренируем его написание по памяти.'],
    deep:['Немного глубже','Ниже находится подробное значение слова: больше контекста и нюансов. Рядом — объяснение простыми словами, дальше — ещё примеры.'],
    recall:['Проверьте память','Двойное нажатие переворачивает карточку. Напишите слово по памяти: покажем ошибку, исправление и возвращение слова.'],recallDone:['Получилось!','Верное написание открывает слово. Вернуть его можно и двойным нажатием. Теперь попробуйте сами!'],skip:'Пропустить показ'},
  kk:{next:'Келесі',done:'Түсінікті',show:'Сақтауды көрсету',return:'Сөзге оралу',saving:'Сақталуда…',
    definition:['Сөз нені білдіреді?','Мұнда сөздің қысқаша мағынасы берілген. Ол негізгі ойды тез түсінуге көмектеседі.'],
    synonyms:['Мағынасы жақын сөздер','Бұлар — синонимдер. Олар мағынаның реңктерін көрсетеді. Кейін кез келгенін басып, толығырақ біле аласыз.'],
    examples:['Сөйлемдегі қолданысы','Бұл — сөздің сөйлемде қолданылу үлгісі. Ол сөзді сөйлеуде қалай қолдануға болатынын көрсетеді.'],
    save:['Сөз ұнады ма?','Осы батырмамен сақтауға болады. Қазір LEXI сөзді Saved бөліміне өзі қосып, қайдан табуға болатынын көрсетеді.'],
    saved:['Сөз сақталды','Міне, ол Saved бөлімінде! Сөз аккаунтыңызда қалады. Енді сөзге оралып, оның жазылуын есте сақтап жаттығайық.'],
    deep:['Тереңірек түсіну','Төменде сөздің толық мағынасы мен ерекшеліктері берілген. Жанында — қарапайым түсіндірме, әрі қарай — басқа мысалдар.'],
    recall:['Есте сақтап көріңіз','Екі рет басу карточканы аударады. Сөзді есте сақтап жазыңыз: қатені, түзетуді және сөздің қайта ашылуын көрсетеміз.'],recallDone:['Дұрыс шықты!','Дұрыс жазу сөзді ашады. Оны екі рет басып та ашуға болады. Енді өзіңіз көріңіз!'],skip:'Көрсетуді өткізу'},
  en:{next:'Next',done:'Got it',show:'Show me how to save',return:'Back to the word',saving:'Saving…',
    definition:['What does it mean?','Here is the short definition. It helps you quickly understand the main idea of the word.'],
    synonyms:['Close in meaning','These are synonyms. They reveal different shades of meaning. Later, tap any one to learn more about it.'],
    examples:['A word in context','Here is an example of the word in a sentence. It shows how you can use it in conversation.'],
    save:['A word worth keeping?','Use this button to save it. LEXI will now add the word to Saved and show you where to find it.'],
    saved:['A little knowledge, kept','Here it is in Saved! This word stays in your account. Now let’s return to it and practise recalling its spelling.'],
    deep:['A little deeper','Below is the full definition, with more context and nuance. Beside it is a simpler explanation, followed by more examples.'],
    recall:['Make it a memory','Double-tap to turn the card over. Type the word from memory: watch a mistake, a correction and the word coming back.'],recallDone:['You’ve got it!','The correct spelling reveals the word. Another double-tap can reveal it too. Now try it yourself!'],skip:'Skip demonstration'},
};

// Continue in the same native modal: the background stays blurred and inert.
// Highlights are read-only copies; saving always uses the application's real action.
export function createReadingGuide({hint,account,getState,saveState,getWord,saveWord,navigate}) {
  const circle=hint.querySelector('.guide-circle'),button=hint.querySelector('#guide-settings-done');
  const arrow=hint.querySelector('.guide-settings-arrow'),media=matchMedia('(prefers-reduced-motion: reduce)');
  let owner=null,phase=null,moving=false,generation=0,animations=[],frame=0,panel=null,flight=null,destination=null;
  const language=()=>Object.hasOwn(copy,getState().guideLanguage)?getState().guideLanguage:'en';
  const text=()=>copy[language()];
  const reduced=()=>media.matches||getState().reduceMotion;
  const memory=createRecallDemo({getWord,reduced,onStatus:status=>{
    if(phase!=='recall'||!owner)return;
    const t=text(),message=t[status==='complete'?'recallDone':'recall'];
    hint.querySelector('#guide-settings-title').textContent=message[0];hint.querySelector('#guide-settings-copy').textContent=message[1];
    button.textContent=status==='complete'?t.done:t.skip;
  }});
  const valid=token=>token===generation&&owner===account.scope&&account.hasAccess&&!account.isGuest;
  const route=()=>phase==='saved'?'saved':'home';
  function source() {
    if(phase==='saved')return document.querySelector(`#main-content [data-word-card="${CSS.escape(getWord()?.id||'')}"]`)||document.querySelector('#main-content [data-word-card]');
    if(!['','#home'].includes(location.hash)||!document.querySelector('#main-content #daily-word'))return null;
    return document.querySelector({definition:'.short-definition',synonyms:'.synonym-pills',examples:'.hero-example',save:'.word-tools .button-save',deep:'.definition-block',recall:'.word-wrap'}[phase]);
  }
  function stopAnimations(){animations.forEach(a=>a.cancel());animations=[];}
  async function animate(nodes,keyframes,duration) {
    if(reduced())return;
    const running=nodes.filter(Boolean).map(node=>node.animate(keyframes,{duration,easing:'cubic-bezier(.42,0,.58,1)',fill:'both'}));
    animations.push(...running);
    await Promise.all(running.map(a=>a.finished.catch(()=>{})));
  }
  function cleanCopy(node) {
    node.removeAttribute('id');node.removeAttribute('tabindex');node.classList.remove('will-reveal','reveal','page-enter');
    node.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'));
    node.querySelectorAll('.word-card-actions').forEach(el=>el.remove());
    for(const control of [node,...node.querySelectorAll('a,button,input')]) {
      if(!control.matches('a,button,input'))continue;
      const span=document.createElement('span');span.className=control.className;
      while(control.firstChild)span.append(control.firstChild);
      if(control===node)node=span;else control.replaceWith(span);
    }
    return node;
  }
  function makePanel(target) {
    panel?.remove();panel=document.createElement('section');panel.className='guide-content-spotlight';
    panel.setAttribute('aria-labelledby','guide-settings-title');panel.dataset.guideContent=phase;
    if(phase==='recall')memory.mount(panel,language());else panel.append(cleanCopy(target.cloneNode(true)));
    hint.insertBefore(panel,circle);
  }
  function geometry(target) {
    const box=target.getBoundingClientRect(),diameter=circle.getBoundingClientRect().width;
    const landscape=innerWidth>=560&&innerHeight<=560;
    const wide=(innerWidth>=1000&&innerHeight>=620)||landscape,gap=wide?36:24;
    const width=wide?Math.min(box.width+32,innerWidth-diameter-gap-64):Math.min(box.width+32,innerWidth-32);
    panel.style.width=`${Math.max(100,width)}px`;
    panel.style.maxHeight=`${wide?innerHeight-64:Math.max(96,innerHeight-diameter-gap-48)}px`;
    if(phase==='recall')memory.fit();
    const height=panel.getBoundingClientRect().height;
    let left,top,circleLeft,circleTop;
    if(wide){
      const right=['synonyms','deep'].includes(phase);
      circleLeft=right?innerWidth-diameter-24:24;
      left=right?Math.max(24,Math.min(box.left-16,circleLeft-gap-width)):Math.min(innerWidth-width-24,Math.max(diameter+gap+24,box.left-16));
      top=Math.max(32,Math.min(box.top-16,innerHeight-height-32));
      const inset=landscape?16:24;
      circleTop=Math.max(inset,Math.min(innerHeight-diameter-inset,top+height/2-diameter/2));
    }else{
      left=Math.max(16,Math.min(innerWidth-width-16,box.left-16));
      top=Math.max(16,Math.min(box.top-16,innerHeight-height-diameter-gap-16));
      circleLeft=(innerWidth-diameter)/2;circleTop=top+height+gap;
    }
    Object.assign(panel.style,{left:`${left}px`,top:`${top}px`});
    Object.assign(circle.style,{left:`${circleLeft}px`,top:`${circleTop}px`});
    panel.tabIndex=panel.scrollHeight>panel.clientHeight+1?0:-1;
    // The small curved pointer stays in the empty gap between content and circle.
    let start,end,control;
    if(wide){const right=circleLeft>left;start={x:right?circleLeft-5:circleLeft+diameter+5,y:circleTop+diameter/2};end={x:right?left+width+6:left-6,y:top+height/2};control={x:(start.x+end.x)/2,y:start.y-16};}
    else{start={x:circleLeft+diameter/2,y:circleTop-4};end={x:Math.max(left+12,Math.min(left+width-12,start.x)),y:top+height+5};control={x:start.x+10,y:(start.y+end.y)/2};}
    const angle=Math.atan2(end.y-control.y,end.x-control.x),size=5;
    arrow.querySelector('path').setAttribute('d',`M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y} M ${end.x-size*Math.cos(angle-.55)} ${end.y-size*Math.sin(angle-.55)} L ${end.x} ${end.y} L ${end.x-size*Math.cos(angle+.55)} ${end.y-size*Math.sin(angle+.55)}`);
  }
  async function scrollToTarget(target,token,{returning=false}={}) {
    if(returning){
      window.scrollTo({top:0,behavior:'instant'});
      await animate([circle],[{opacity:0},{opacity:0}],400);
      if(!valid(token))return;
    }
    const from=scrollY,box=target.getBoundingClientRect();
    const top=innerWidth>=1000?Math.min(180,innerHeight*.22):48;
    const to=Math.max(0,Math.min(document.documentElement.scrollHeight-innerHeight,scrollY+box.top-top));
    if(reduced()||Math.abs(to-from)<2){window.scrollTo({top:to,behavior:'instant'});return;}
    await new Promise(resolve=>{
      const start=performance.now();
      function tick(now){
        if(!valid(token)){resolve();return;}
        const progress=Math.min(1,(now-start)/850),ease=(1-Math.cos(Math.PI*progress))/2;
        window.scrollTo({top:from+(to-from)*ease,behavior:'instant'});
        if(progress<1&&!reduced())frame=requestAnimationFrame(tick);
        else{window.scrollTo({top:to,behavior:'instant'});frame=0;resolve();}
      }
      frame=requestAnimationFrame(tick);
    });
  }
  async function go(page,token) {
    if(location.hash!==`#${page}`&&!(page==='home'&&!location.hash))navigate(page);
    // Wait for the real route render, not a duplicated Saved screen.
    for(let i=0;i<120;i++){
      if(!valid(token))return false;
      if(source()){
        for(const a of document.querySelector('#main-content').getAnimations())if(a.playState==='running'&&Number.isFinite(a.effect.getComputedTiming().endTime))a.finish();
        return true;
      }
      await new Promise(requestAnimationFrame);
    }
    return false;
  }
  async function show(token,{returning=false}={}) {
    if(!await go(route(),token)){
      if(valid(token)){moving=false;cancel();if(hint.open)hint.close();}
      return;
    }
    const target=source();if(!target||!valid(token))return;
    // Reveal animations are decorative; they must not affect copied text or geometry.
    target.classList.add('is-visible');
    makePanel(target);
    panel.style.opacity='0';circle.style.opacity='0';arrow.style.opacity='0';
    await scrollToTarget(target,token,{returning});if(!valid(token))return;
    const t=text();hint.lang=language();hint.dataset.guidePhase=phase;hint.classList.add('is-reading-guide');
    hint.querySelector('.guide-number').textContent=`LEXI / ${String(steps.indexOf(phase)+2).padStart(2,'0')} / 08`;
    hint.querySelector('#guide-settings-title').textContent=t[phase][0];hint.querySelector('#guide-settings-copy').textContent=t[phase][1];
    button.textContent=phase==='save'?t.show:phase==='saved'?t.return:phase==='recall'?t.skip:t.next;
    if(!hint.open)hint.showModal();geometry(target);
    stopAnimations();panel.style.opacity='';circle.style.opacity='';arrow.style.opacity='';
    const entrance=animate([panel,circle,arrow],[{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],500);
    button.disabled=false;moving=false;circle.querySelector('h2').focus({preventScroll:true});
    if(phase==='recall')memory.play();
    await entrance;
    if(valid(token)&&!moving)stopAnimations();
  }
  async function flyBookmark(token) {
    if(reduced())return;
    const target=document.querySelector('.saved-link');if(!target||!panel)return;
    const from=panel.getBoundingClientRect(),bounds=target.getBoundingClientRect();
    const to={left:Math.max(16,Math.min(innerWidth-bounds.width-16,bounds.left)),top:Math.max(16,Math.min(innerHeight-bounds.height-16,bounds.top)),width:bounds.width,height:bounds.height};
    destination=cleanCopy(target.cloneNode(true));destination.classList.add('guide-save-destination');
    Object.assign(destination.style,{left:`${to.left}px`,top:`${to.top}px`,width:`${to.width}px`,height:`${to.height}px`});hint.append(destination);
    flight=document.createElement('span');flight.className='guide-flying-bookmark';flight.setAttribute('aria-hidden','true');flight.innerHTML=icon('bookmark');hint.append(flight);
    const start={x:from.left+from.width/2-20,y:from.top+from.height/2-20},end={x:to.left+to.width/2-20,y:to.top+to.height/2-20};
    const frames=Array.from({length:21},(_,i)=>{const t=i/20;return {transform:`translate(${(1-t)**2*start.x+2*(1-t)*t*((start.x+end.x)/2)+t*t*end.x}px,${(1-t)**2*start.y+2*(1-t)*t*(Math.min(start.y,end.y)-65)+t*t*end.y}px) scale(${1-t*.25})`,opacity:t>.9?(1-t)*10:1};});
    await animate([flight],frames,800);
    flight?.remove();flight=null;destination?.remove();destination=null;
  }
  async function next() {
    if(!owner||moving||owner!==account.scope||!account.hasAccess)return;
    const token=++generation;moving=true;button.disabled=true;
    if(phase==='recall')memory.cancel();
    if(phase==='save'){
      const word=getWord();if(!word){cancel();hint.close();return;}
      saveWord(word.id);button.textContent=text().saving;
      const savedButton=source();if(savedButton){makePanel(savedButton);geometry(savedButton);}
      // Save the resumable destination immediately; repeated clicks never toggle it off.
      saveState({guideStep:'saved'});
      await flyBookmark(token);if(!valid(token))return;
    }
    const fading=[panel,circle,arrow].filter(Boolean).map(node=>({node,opacity:getComputedStyle(node).opacity,transform:getComputedStyle(node).transform}));
    stopAnimations();
    await Promise.all(fading.map(({node,opacity,transform})=>animate([node],[{opacity,transform},{opacity:0,transform}],240)));
    if(!valid(token))return;
    const previous=phase,nextStep=steps[steps.indexOf(phase)+1]||'done';
    panel?.remove();panel=null;phase=nextStep;saveState({guideStep:nextStep});
    if(nextStep==='done'){
      cancel();hint.close();
      document.querySelector('#daily-word')?.focus({preventScroll:true});return;
    }
    await show(token,{returning:previous==='saved'});
  }
  function resume() {
    const state=getState();
    if(!steps.includes(state.guideStep)||!state.guideLanguage||!state.onboarded||!account.hasAccess||account.isGuest)return false;
    if(owner)return true;
    // Respect hidden recall cards: the tour must never reveal a remembered answer.
    if(state.guideStep!=='saved'&&['','#home'].includes(location.hash)&&!document.querySelector('#main-content #daily-word'))return false;
    owner=account.scope;phase=state.guideStep;moving=true;button.disabled=true;circle.style.opacity='0';
    if(phase==='saved'&&!state.saved.length){phase='save';saveState({guideStep:phase});}
    hint.classList.add('is-reading-guide');hint.dataset.guidePhase=phase;
    if(!hint.open)hint.showModal();
    show(++generation);return true;
  }
  function cancel() {
    memory.cancel();
    ++generation;cancelAnimationFrame(frame);frame=0;stopAnimations();
    panel?.remove();flight?.remove();destination?.remove();panel=null;flight=null;destination=null;
    owner=null;phase=null;moving=false;button.disabled=false;
    circle.style.opacity='';arrow.style.opacity='';hint.classList.remove('is-reading-guide');
    delete hint.dataset.guidePhase;
  }
  function refresh(){
    if(!owner)return;
    if(owner!==account.scope||!account.hasAccess||getState().guideStep==='done'){cancel();if(hint.open)hint.close();return;}
    if(moving)return;
    if(getState().guideStep!==phase){cancel();if(hint.open)hint.close();resume();return;}
    const target=source();
    if(!target){cancel();if(hint.open)hint.close();return;}
    if(phase==='recall'){
      if(memory.wordId!==getWord()?.id){cancel();hint.close();resume();return;}
      if(reduced()&&memory.playing)memory.finish();
      geometry(target);return;
    }
    makePanel(target);geometry(target);
  }
  window.addEventListener('resize',()=>{if(owner&&!moving&&source())geometry(source());});
  window.addEventListener('scroll',()=>{if(owner&&!moving&&source())geometry(source());},{passive:true});
  window.addEventListener('lexi:accountchange',()=>{if(owner&&owner!==account.scope){cancel();if(hint.open)hint.close();}});
  media.addEventListener('change',()=>{if(media.matches){stopAnimations();if(phase==='recall')memory.finish();}});
  hint.addEventListener('close',()=>{if(!hint.open)cancel();});
  return {resume,next,refresh,cancel,get active(){return !!owner;}};
}
