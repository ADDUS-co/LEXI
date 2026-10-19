const KEY = 'lexi:v1';
const defaults = () => ({version: 2, theme: 'noir', interests: [], saved: [], history: [], hiddenWords: [], updateTime: '08:00', onboarded: false, reduceMotion: false});
let memory = defaults();
export let storageAvailable = true;

function validDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

export function readStore() {
  if (!storageAvailable) return structuredClone(memory);
  try {
    let raw;
    try { raw = JSON.parse(localStorage.getItem(KEY) || '{}'); }
    catch (error) {
      if (error instanceof SyntaxError) return memory = defaults();
      throw error;
    }
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return memory = defaults();
    memory = {
      ...defaults(),
      theme: ['noir', 'studio', 'experimental'].includes(raw.theme) ? raw.theme : 'noir',
      interests: Array.isArray(raw.interests) ? [...new Set(raw.interests.filter(x => typeof x === 'string'))] : [],
      saved: Array.isArray(raw.saved) ? [...new Set(raw.saved.filter(x => typeof x === 'string'))] : [],
      history: Array.isArray(raw.history) ? raw.history.filter(x => x && typeof x.id === 'string' && validDate(x.date)) : [],
      onboarded: raw.onboarded === true,
      reduceMotion: raw.reduceMotion === true,
      updateTime: typeof raw.updateTime === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(raw.updateTime)
        ? raw.updateTime : raw.onboarded === true ? '00:00' : '08:00',
      hiddenWords: Array.isArray(raw.hiddenWords) ? [...new Set(raw.hiddenWords.filter(x => typeof x === 'string'))] : [],
    };
  } catch { storageAvailable = false; }
  return structuredClone(memory);
}

export function updateStore(patch) {
  memory = {...readStore(), ...patch};
  try { localStorage.setItem(KEY, JSON.stringify(memory)); }
  catch { storageAvailable = false; }
  return structuredClone(memory);
}

export function resetStore() {
  memory = defaults();
  try { localStorage.removeItem(KEY); }
  catch { storageAvailable = false; }
  return structuredClone(memory);
}

