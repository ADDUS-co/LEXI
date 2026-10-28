import {answerMatches} from './recall.js';
import {icon} from './icons.js';

const copy={
  ru:{tap:'ДВОЙНОЕ НАЖАТИЕ',label:'Напишите слово по памяти',check:'Проверить',idle:'Вспомните написание слова.',wrong:'Не совсем. Попробуем ещё раз.',right:'Верно! Слово возвращается.',replay:'Повторить показ',open:'Показать, как перевернуть карточку'},
  kk:{tap:'ЕКІ РЕТ БАСЫҢЫЗ',label:'Сөзді есте сақтап жазыңыз',check:'Тексеру',idle:'Сөздің жазылуын еске түсіріңіз.',wrong:'Дұрыс емес. Қайта көрейік.',right:'Дұрыс! Сөз қайта ашылады.',replay:'Қайта көрсету',open:'Карточканы аударуды көрсету'},
  en:{tap:'DOUBLE-TAP THE WORD',label:'Type the word from memory',check:'Check',idle:'Recall the spelling of the word.',wrong:'Not quite. Let’s try again.',right:'Correct! The word is coming back.',replay:'Watch again',open:'Show how to turn the card over'},
};

// The demonstration shares recall validation, while leaving real card positions intact.
export function createRecallDemo({getWord,reduced,onStatus}) {
  let root=null,card=null,language='en',answer='',wordId=null,run=0,animations=[],timers=new Map(),events=null,playing=false,complete=false;
  const t=()=>copy[language];
  const valid=token=>token===run&&root?.isConnected;
  function stop(){
    ++run;playing=false;
    for(const [timer,resolve] of timers){clearTimeout(timer);resolve(false);}timers.clear();
    animations.forEach(a=>a.cancel());animations=[];
  }
  function wait(ms,token){
    if(!valid(token)||reduced())return Promise.resolve(valid(token));
    return new Promise(resolve=>{const timer=setTimeout(()=>{timers.delete(timer);resolve(valid(token));},ms);timers.set(timer,resolve);});
  }
  async function motion(node,frames,duration,token){
    if(!valid(token)||reduced())return;
    const animation=node.animate(frames,{duration,easing:'cubic-bezier(.42,0,.58,1)',fill:'both'});animations.push(animation);
    await animation.finished.catch(()=>{});
    animation.cancel();animations=animations.filter(a=>a!==animation);
  }
  function setStage(stage){root.dataset.recallStage=stage;}
  function front(){
    card.replaceChildren();
    const face=document.createElement('div');face.className='guide-memory-front';face.tabIndex=0;face.setAttribute('role','button');face.setAttribute('aria-label',`${answer}. ${t().open}`);
    const label=document.createElement('span');label.className='micro muted';label.textContent='WORD OF THE DAY';
    const word=document.createElement('span');word.className='guide-memory-word';word.textContent=answer+'.';
    const note=document.createElement('span');note.className='guide-memory-tap micro';note.innerHTML=icon('flip');note.append(document.createTextNode(t().tap));
    face.append(label,word,note);card.append(face);fit();
  }
  function back(){
    const form=document.createElement('form');form.className='recall-form guide-memory-back';
    form.innerHTML='<label for="guide-recall-answer"></label><div class="recall-input-row"><input id="guide-recall-answer" type="text" readonly inputmode="none" autocomplete="off" spellcheck="false" aria-describedby="guide-recall-feedback"><button type="submit" class="button button-outline" tabindex="-1"></button></div><p id="guide-recall-feedback" class="recall-feedback" role="status" aria-live="polite" aria-atomic="true"></p>';
    form.querySelector('label').textContent=t().label;form.querySelector('button').textContent=t().check;
    form.querySelector('p').textContent=t().idle;card.replaceChildren(form);
    return form.querySelector('input');
  }
  function fit(){
    const word=card?.querySelector('.guide-memory-word');if(!word)return;
    const width=Math.max(1,card.clientWidth);let size=Math.min(88,Math.max(24,width*.13));word.style.fontSize=`${size}px`;
    while(word.scrollWidth>width&&size>20){size-=1;word.style.fontSize=`${size}px`;}
    word.style.whiteSpace=word.scrollWidth>width?'normal':'nowrap';
  }
  async function flip(render,token){
    await motion(card,[{transform:'perspective(1000px) rotateX(0deg)',opacity:1},{transform:'perspective(1000px) rotateX(-85deg)',opacity:.15}],100,token);
    if(!valid(token))return;
    const hadFocus=card.contains(document.activeElement);render();
    await motion(card,[{transform:'perspective(1000px) rotateX(85deg)',opacity:.15},{transform:'perspective(1000px) rotateX(0deg)',opacity:1}],140,token);
    if(valid(token)&&hadFocus)card.querySelector('input,[tabindex="0"]')?.focus({preventScroll:true});
  }
  async function type(input,value,token){
    setStage('typing');
    for(const [index,letter] of Array.from(value).entries()){
      if(!await wait(letter===' '?130:65+(index%3)*15,token))return false;
      input.value+=letter;input.setSelectionRange(input.value.length,input.value.length);input.scrollLeft=input.scrollWidth;
    }
    return valid(token);
  }
  function finish(){
    if(!root)return;
    const hadFocus=card.contains(document.activeElement);
    stop();complete=true;front();setStage('complete');
    root.querySelector('.guide-memory-replay').hidden=false;onStatus('complete');
    if(hadFocus)card.querySelector('.guide-memory-front').focus({preventScroll:true});
  }
  async function play(){
    if(playing||!root?.isConnected)return;
    stop();const token=run;playing=true;complete=false;front();root.querySelector('.guide-memory-replay').hidden=true;onStatus('playing');
    if(reduced()){finish();return;}
    // The two tap cues take 540 ms, so the flip starts one second into the demo.
    setStage('intro');if(!await wait(460,token))return;
    setStage('tapping');
    for(let i=0;i<2;i++){
      const pulse=document.createElement('span');pulse.className='guide-memory-pulse';pulse.setAttribute('aria-hidden','true');card.append(pulse);
      motion(pulse,[{opacity:.8,transform:'translate(-50%,-50%) scale(.45)'},{opacity:0,transform:'translate(-50%,-50%) scale(1.9)'}],420,token).then(()=>pulse.remove());
      if(!await wait(i===0?200:340,token))return;
    }
    setStage('flipping-back');let input;
    await flip(()=>{input=back();},token);if(!valid(token))return;
    if(document.activeElement?.id==='guide-settings-title')input.focus({preventScroll:true});
    const letters=Array.from(answer),last=letters.pop();
    const wrong=letters.join('')+(String(last).toLowerCase()==='x'?'z':'x');
    if(!await type(input,wrong,token))return;
    await wait(250,token);if(!valid(token))return;
    // Both outcomes use the same spelling rules as the actual practice card.
    if(!answerMatches(input.value,answer)){
      input.setAttribute('aria-invalid','true');card.querySelector('.recall-feedback').textContent=t().wrong;setStage('wrong');
      await motion(input,[{transform:'translateX(0)'},{transform:'translateX(-6px)'},{transform:'translateX(5px)'},{transform:'translateX(-3px)'},{transform:'translateX(0)'}],300,token);
    }
    if(!await wait(650,token))return;
    setStage('erasing');input.removeAttribute('aria-invalid');card.querySelector('.recall-feedback').textContent=t().idle;
    while(input.value){
      if(!await wait(45,token))return;
      input.value=Array.from(input.value).slice(0,-1).join('');input.setSelectionRange(input.value.length,input.value.length);
    }
    setStage('empty');if(!await wait(220,token))return;
    if(!await type(input,answer,token))return;
    await wait(250,token);if(!valid(token))return;
    if(answerMatches(input.value,answer)){
      setStage('correct');card.querySelector('.recall-feedback').textContent=t().right;
      const check=card.querySelector('.recall-input-row button');check.innerHTML=icon('check');check.append(document.createTextNode(t().check));
      await motion(input,[{boxShadow:'0 0 0 0 transparent'},{boxShadow:'0 0 0 4px color-mix(in srgb,var(--accent-text) 18%,transparent)'},{boxShadow:'0 0 0 0 transparent'}],500,token);
    }
    if(!await wait(650,token))return;
    setStage('flipping-front');await flip(front,token);if(!valid(token))return;
    finish();
  }
  function mount(panel,code){
    cancel();root=panel;language=Object.hasOwn(copy,code)?code:'en';answer=getWord().word;wordId=getWord().id;events=new AbortController();
    card=document.createElement('div');card.className='guide-memory-card';
    const replay=document.createElement('button');replay.type='button';replay.className='text-link guide-memory-replay';replay.textContent=t().replay;replay.hidden=true;
    const footer=document.createElement('div');footer.className='guide-memory-footer';footer.append(replay);
    root.append(card,footer);front();setStage('intro');
    let lastTap=null;
    root.addEventListener('pointerup',event=>{
      if(event.pointerType==='mouse'||!event.target.closest('.guide-memory-front'))return;
      const tap={at:performance.now(),x:event.clientX,y:event.clientY};
      if(lastTap&&tap.at-lastTap.at<550&&Math.hypot(tap.x-lastTap.x,tap.y-lastTap.y)<28){lastTap=null;play();}else lastTap=tap;
    },{signal:events.signal});
    root.addEventListener('dblclick',event=>{if(event.target.closest('.guide-memory-front'))play();},{signal:events.signal});
    root.addEventListener('keydown',event=>{if(event.target.closest('.guide-memory-front')&&['Enter',' '].includes(event.key)){event.preventDefault();play();}},{signal:events.signal});
    root.addEventListener('click',event=>{if(event.target.closest('.guide-memory-replay'))play();},{signal:events.signal});
    root.addEventListener('submit',event=>event.preventDefault(),{signal:events.signal});
  }
  function cancel(){stop();events?.abort();events=null;root=null;card=null;complete=false;wordId=null;}
  return {mount,play,cancel,fit,finish,get playing(){return playing;},get complete(){return complete;},get wordId(){return wordId;}};
}
