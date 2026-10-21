import {readStore,readGuestStore,replaceStore,switchStore,storageKey,normalizeStore} from './storage.js';

const MARKER='lexi:active-account';
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const historyKey=item=>`${item.id}|${item.date}`;

function mergeSet(base,local,remote,key=value=>value) {
  const before=new Set(base.map(key));
  const current=new Map(local.map(value=>[key(value),value]));
  const result=new Map(remote.map(value=>[key(value),value]));
  for (const id of before) if (!current.has(id)) result.delete(id);
  for (const [id,value] of current) if (!before.has(id)) result.set(id,value);
  return [...result.values()];
}

export function mergeChanges(base,local,remote) {
  base=normalizeStore(base); local=normalizeStore(local); remote=normalizeStore(remote);
  const result={...remote};
  for (const key of ['saved','hiddenWords']) result[key]=mergeSet(base[key],local[key],remote[key]);
  result.history=mergeSet(base.history,local.history,remote.history,historyKey);
  for (const key of ['theme','interests','updateTime','onboarded','reduceMotion']) if (!equal(base[key],local[key])) result[key]=local[key];
  return normalizeStore(result);
}

function importGuestInto(account,guest) {
  return normalizeStore({...account,
    saved:[...new Set([...account.saved,...guest.saved])],
    hiddenWords:[...new Set([...account.hiddenWords,...guest.hiddenWords])],
    history:[...new Map([...account.history,...guest.history].map(item=>[historyKey(item),item])).values()],
    interests:account.interests.length?account.interests:guest.interests,
    onboarded:account.onboarded||guest.onboarded,
  });
}

export function createAccountService() {
  let user=null, csrf='', base=normalizeStore({}), revision=0, status='guest';
  let owner=null, dirty=false, muted=false, timer, inFlight=null, ready=false;
  const emit=()=>window.dispatchEvent(new CustomEvent('lexi:accountchange',{detail:{user,status}}));
  const metaKey=id=>`lexi:sync:${id}`;
  function readMeta(id) { try{return JSON.parse(localStorage.getItem(metaKey(id))||'null');}catch{return null;} }
  function saveMeta() { if(owner)try{localStorage.setItem(metaKey(owner),JSON.stringify({base,revision,dirty}));}catch{} }
  function marker(id) { try{if(id)localStorage.setItem(MARKER,String(id));else localStorage.removeItem(MARKER);}catch{} }
  function cachedOwner() { try{const id=Number(localStorage.getItem(MARKER));return Number.isInteger(id)&&id>0?id:null;}catch{return null;} }
  function cache(state) { muted=true;replaceStore(state,{notify:false});muted=false; }

  async function request(path,options={},retry=true) {
    const headers=new Headers(options.headers);
    if (options.method&&options.method!=='GET') headers.set('X-CSRF-Token',csrf);
    if (options.owned) headers.set('X-Account-Id',String(options.ownerId??user?.id??''));
    const response=await fetch('/api/account'+path,{...options,headers,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(8000)});
    const data=await response.json();
    if (!response.ok) {
      if (response.status===403&&data.code==='csrf'&&retry) {
        const session=await request('/session',{},false);csrf=session.csrfToken;
        return request(path,options,false);
      }
      const error=new Error(data.error||'Your account could not be reached.');
      error.status=response.status;error.data=data;throw error;
    }
    if(data.csrfToken)csrf=data.csrfToken;
    return data;
  }

  function scheduleSync() {
    if(!owner||muted)return;
    dirty=true;saveMeta();status=navigator.onLine&&user?'syncing':'offline';emit();
    clearTimeout(timer);timer=setTimeout(()=>flush().catch(()=>{}),400);
  }

  async function flush() {
    clearTimeout(timer);
    if(inFlight)return inFlight;
    if(!user||!dirty||!navigator.onLine)return false;
    inFlight=(async()=>{
      for(let attempt=0;attempt<4&&dirty&&user;attempt++) {
        const id=user.id, snapshot=readStore();
        try {
          const result=await request('/state',{method:'PUT',owned:true,ownerId:id,headers:{'Content-Type':'application/json'},body:JSON.stringify({state:snapshot,revision})});
          if(user?.id!==id||owner!==id)return false;
          base=result.state;revision=result.revision;
          dirty=!equal(readStore(),snapshot);saveMeta();status=dirty?'syncing':'synced';emit();
        } catch(error) {
          if(error.status===409&&error.data.code==='conflict') {
            const latest=normalizeStore(error.data.state);
            const merged=mergeChanges(base,readStore(),latest);
            base=latest;revision=error.data.revision;cache(merged);dirty=true;saveMeta();
            window.dispatchEvent(new Event('lexi:accountstate'));continue;
          }
          status=error.status===401||error.data?.code==='account_changed'?'expired':'offline';
          saveMeta();emit();throw error;
        }
      }
      return !dirty;
    })().finally(()=>{inFlight=null;});
    return inFlight;
  }

  async function activate(data,{importLocal=false}={}) {
    user=data.user;csrf=data.csrfToken||csrf;
    if(!user) {
      owner=null;dirty=false;status='guest';switchStore();marker(null);ready=true;emit();
      window.dispatchEvent(new Event('lexi:accountstate'));return;
    }
    owner=user.id;switchStore(owner);
    const local=readStore(), meta=readMeta(owner), remote=normalizeStore(data.state);
    revision=data.revision;
    let merged=remote;
    if(meta?.dirty)merged=mergeChanges(meta.base,local,remote);
    if(importLocal) merged=data.state?importGuestInto(merged,readGuestStore()):readGuestStore();
    base=remote;cache(merged);dirty=!equal(merged,remote);marker(owner);saveMeta();
    status=dirty?'syncing':'synced';ready=true;emit();window.dispatchEvent(new Event('lexi:accountstate'));
    if(dirty)await flush();
  }

  async function initialize() {
    try { await activate(await request('/session')); }
    catch(error) {
      if(!ready) {
        owner=cachedOwner();switchStore(owner);
        if(owner) {const meta=readMeta(owner);base=normalizeStore(meta?.base);revision=meta?.revision||0;dirty=meta?.dirty||false;}
      }
      status=owner?'offline':'unavailable';ready=true;emit();
    }
  }

  window.addEventListener('lexi:storechange',()=>{if(ready)scheduleSync();});
  window.addEventListener('online',()=>initialize());
  window.addEventListener('storage',event=>{
    if(event.key===MARKER)initialize();
    else if(owner&&event.key===storageKey()) {dirty=true;saveMeta();scheduleSync();}
  });
  let lastRefresh=0;
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&owner&&Date.now()-lastRefresh>10000){lastRefresh=Date.now();initialize();}
  });

  return {
    initialize,flush,
    get user(){return user;},get status(){return status;},get owner(){return owner;},
    async register(fields,importLocal) {
      await request('/session');
      const data=await request('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});
      await activate(data,{importLocal});return user;
    },
    async login(fields) {
      await request('/session');
      await activate(await request('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)}));return user;
    },
    async logout() {
      const complete=await flush();
      if(dirty&&!complete)throw new Error('Reconnect and sync your changes before signing out.');
      await activate(await request('/logout',{method:'POST',owned:true}));
    },
    async uploadPhoto(file) {
      const form=new FormData();form.append('photo',file);
      const data=await request('/avatar',{method:'PUT',body:form,owned:true});user=data.user;emit();return user;
    },
    async removePhoto(){const data=await request('/avatar',{method:'DELETE',owned:true});user=data.user;emit();return user;},
    async importGuest(){if(!user)return;cache(importGuestInto(readStore(),readGuestStore()));dirty=true;saveMeta();window.dispatchEvent(new Event('lexi:accountstate'));await flush();},
  };
}
