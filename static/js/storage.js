// Account caches persist; guest progress exists only in this tab's memory.
const GUEST_KEY = 'lexi:guest:memory';
let activeKey = GUEST_KEY;
const memories = new Map();
export let storageAvailable = true;
const defaults = () => ({version:2, theme:'noir', interests:[], saved:[], history:[], hiddenWords:[], updateTime:'08:00', onboarded:false, reduceMotion:false, guideLanguage:null, guideStep:'language'});

function validDate(value) {
  return typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

export function normalizeStore(raw) {
  if (!raw || typeof raw!=='object' || Array.isArray(raw)) return defaults();
  const list = key => Array.isArray(raw[key]) ? [...new Set(raw[key].filter(value=>typeof value==='string'))] : [];
  return {...defaults(),
    theme:['noir','studio','experimental'].includes(raw.theme)?raw.theme:'noir',
    interests:list('interests'), saved:list('saved'), hiddenWords:list('hiddenWords'),
    history:Array.isArray(raw.history)?raw.history.filter(item=>item&&typeof item.id==='string'&&validDate(item.date)):[],
    onboarded:raw.onboarded===true, reduceMotion:raw.reduceMotion===true,
    guideLanguage:['ru','kk','en'].includes(raw.guideLanguage)?raw.guideLanguage:null,
    guideStep:['language','time','collections','settings','word','done'].includes(raw.guideStep)?raw.guideStep:raw.onboarded===true?'done':'language',
    updateTime:typeof raw.updateTime==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(raw.updateTime)?raw.updateTime:raw.onboarded===true?'00:00':'08:00',
  };
}

function readKey(key) {
  if (key!==GUEST_KEY && storageAvailable) {
    try {
      const content=localStorage.getItem(key);
      let parsed;
      try { parsed=JSON.parse(content||'{}'); } catch { parsed={}; }
      memories.set(key,normalizeStore(parsed));
    } catch { storageAvailable=false; }
  }
  if (!memories.has(key)) memories.set(key,defaults());
  return structuredClone(memories.get(key));
}

export function readStore() { return readKey(activeKey); }
export function storageKey() { return activeKey; }
export function clearGuestStore() { memories.delete(GUEST_KEY); }

export function switchStore(userId=null) {
  activeKey=Number.isInteger(userId)&&userId>0?`lexi:account:${userId}:v2`:GUEST_KEY;
  return readStore();
}

export function replaceStore(value,{notify=true}={}) {
  const previous=readStore();
  const next=normalizeStore(value);
  memories.set(activeKey,next);
  if(activeKey!==GUEST_KEY) {
    try { localStorage.setItem(activeKey,JSON.stringify(next)); }
    catch { storageAvailable=false; }
  }
  if (notify&&JSON.stringify(previous)!==JSON.stringify(next)) {
    window.dispatchEvent(new CustomEvent('lexi:storechange',{detail:{key:activeKey,state:structuredClone(next)}}));
  }
  return structuredClone(next);
}

export function updateStore(patch) { return replaceStore({...readStore(),...patch}); }
export function resetStore() { return replaceStore(defaults()); }
