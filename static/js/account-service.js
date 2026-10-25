import {readStore,replaceStore,switchStore,storageKey,normalizeStore,clearGuestStore} from './storage.js';

const MARKER='lexi:active-account';
const PROGRESS_VERSION=2;
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
  for (const key of ['theme','interests','updateTime','onboarded','reduceMotion','guideLanguage','guideStep']) if (!equal(base[key],local[key])) result[key]=local[key];
  return normalizeStore(result);
}

export function createAccountService() {
  let user=null, guestId=null, pendingGuestExit=null, csrf='', base=normalizeStore({}), revision=0, status='signed-out';
  let owner=null, identity='', dirty=false, muted=false, timer, inFlight=null, ready=false, authGeneration=0;
  let channel;
  try {channel=new BroadcastChannel('lexi:session');}catch{}
  const emit=()=>window.dispatchEvent(new CustomEvent('lexi:accountchange',{detail:{user,status}}));
  const metaKey=id=>`lexi:sync:${id}:v2`;
  function readMeta(id) { try{return JSON.parse(localStorage.getItem(metaKey(id))||'null');}catch{return null;} }
  function saveMeta() { if(owner)try{localStorage.setItem(metaKey(owner),JSON.stringify({base,revision,dirty,identity,progressVersion:PROGRESS_VERSION}));}catch{} }
  function marker(id) { try{if(id)localStorage.setItem(MARKER,String(id));else localStorage.removeItem(MARKER);}catch{} }
  function cachedOwner() { try{const id=Number(localStorage.getItem(MARKER));return Number.isInteger(id)&&id>0?id:null;}catch{return null;} }
  function cache(state) { muted=true;replaceStore(state,{notify:false});muted=false; }

  async function request(path,options={},retry=true) {
    const headers=new Headers(options.headers);
    if (options.method&&options.method!=='GET') headers.set('X-CSRF-Token',csrf);
    if (options.owned) headers.set('X-Account-Id',String(options.ownerId??user?.id??''));
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),['/session','/register','/login','/guest'].includes(path)?90000:30000);
    const checkingSession=path==='/session'&&(!options.method||options.method==='GET');
    try {
      for(let attempt=0;;attempt++) {
        const response=await fetch('/api/account'+path,{...options,headers,credentials:'same-origin',cache:'no-store',signal:controller.signal});
        let data;
        try {data=await response.json();}
        catch(error) {if(error.name!=='SyntaxError')throw error;}
        const valid=data&&typeof data==='object'&&!Array.isArray(data);
        const unavailable=response.status>=500||(!valid&&response.ok);
        // Only this read can be repeated safely while the host is starting.
        // Never replay registration, login, or other writes after a lost response.
        if(checkingSession&&unavailable&&attempt<2) {
          await new Promise(resolve=>setTimeout(resolve,1500*(attempt+1)));
          continue;
        }
        if(unavailable||!valid)throw Object.assign(new Error('LEXI is not responding yet. Please wait a moment and try again.'),{code:'unavailable',status:response.status});
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
    } catch(error) {
      if(controller.signal.aborted||['TimeoutError','AbortError'].includes(error.name))throw Object.assign(new Error('LEXI is taking longer than usual to respond. Please wait a moment and try again.'),{code:'timeout'});
      if(error instanceof TypeError)throw Object.assign(new Error('Could not connect to LEXI. Check your connection and try again.'),{code:'network'});
      throw error;
    } finally {
      clearTimeout(timeout);
    }
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
    const syncOwner=owner;
    inFlight=(async()=>{
      for(let attempt=0;attempt<4&&dirty&&user;attempt++) {
        const id=user.id, snapshot=readStore();
        try {
          const result=await request('/state',{method:'PUT',owned:true,ownerId:id,headers:{'Content-Type':'application/json'},body:JSON.stringify({state:snapshot,revision,progressVersion:PROGRESS_VERSION})});
          if(user?.id!==id||owner!==id)return false;
          base=result.state;revision=result.revision;
          dirty=!equal(readStore(),snapshot);saveMeta();status=dirty?'syncing':'synced';emit();
        } catch(error) {
          if(user?.id!==id||owner!==id)return false;
          if(error.status===409&&error.data?.code==='conflict') {
            const latest=normalizeStore(error.data.state);
            const merged=mergeChanges(base,readStore(),latest);
            base=latest;revision=error.data.revision;cache(merged);dirty=true;saveMeta();
            window.dispatchEvent(new Event('lexi:accountstate'));continue;
          }
          status=error.status===401||['account_changed','progress_reset'].includes(error.data?.code)?'expired':'offline';
          saveMeta();emit();throw error;
        }
      }
      return !dirty;
    })().finally(()=>{inFlight=null;if(owner!==syncOwner&&dirty&&user)scheduleSync();});
    return inFlight;
  }

  async function activate(data,{fresh=false,initialTheme}={}) {
    if(data.user&&data.progressVersion!==PROGRESS_VERSION)throw new Error('Reload LEXI after the account update.');
    clearTimeout(timer);
    const previousGuest=guestId;
    guestId=typeof data.guestId==='string'?data.guestId:null;
    if(!guestId||previousGuest!==guestId)clearGuestStore();
    user=data.user;csrf=data.csrfToken||csrf;
    if(!user) {
      owner=null;identity='';dirty=false;base=normalizeStore({});revision=0;
      status=guestId?'guest':'signed-out';switchStore();
      if(guestId&&guestId!==previousGuest&&['noir','studio','experimental'].includes(initialTheme))cache({...readStore(),theme:initialTheme});
      marker(null);ready=true;emit();
      window.dispatchEvent(new Event('lexi:accountstate'));return;
    }
    owner=user.id;identity=`${user.id}:${user.createdAt}:${user.username}`;switchStore(owner);
    const local=readStore(), meta=readMeta(owner), remote=normalizeStore(data.state);
    revision=data.revision;
    let merged=remote;
    if(!fresh&&meta?.dirty&&meta.identity===identity&&meta.progressVersion===PROGRESS_VERSION&&Number.isInteger(meta.revision)&&meta.revision<=revision&&(data.state||meta.revision===revision))merged=mergeChanges(meta.base,local,remote);
    if(!data.state&&['noir','studio','experimental'].includes(initialTheme))merged={...merged,theme:initialTheme};
    base=remote;cache(merged);dirty=!equal(merged,remote);marker(owner);saveMeta();
    status=dirty?'syncing':'synced';ready=true;emit();window.dispatchEvent(new Event('lexi:accountstate'));
    if(dirty)await flush();
  }

  async function initialize() {
    const generation=++authGeneration;
    try {
      let data=await request('/session');
      if(generation!==authGeneration)return;
      if(pendingGuestExit&&data.guestId===pendingGuestExit) {
        data=await request('/logout',{method:'POST',headers:{'X-Guest-Id':pendingGuestExit}});
        if(generation!==authGeneration)return;
      }
      pendingGuestExit=null;await activate(data);
    }
    catch(error) {
      if(generation!==authGeneration)return;
      if(!ready) {
        owner=cachedOwner();switchStore(owner);
        if(owner) {const meta=readMeta(owner);if(meta?.progressVersion===PROGRESS_VERSION&&typeof meta.identity==='string'){identity=meta.identity;base=normalizeStore(meta.base);revision=meta.revision||0;dirty=meta.dirty||false;}else{owner=null;identity='';switchStore();marker(null);}}
      }
      status=guestId?'guest':owner?'offline':'unavailable';ready=true;emit();
    }
  }

  window.addEventListener('lexi:storechange',event=>{if(ready&&event.detail?.key===storageKey())scheduleSync();});
  window.addEventListener('online',()=>initialize());
  window.addEventListener('pagehide',()=>{
    if(guestId){++authGeneration;activate({user:null});}
  });
  window.addEventListener('pageshow',event=>{if(event.persisted)initialize();});
  if(channel)channel.onmessage=event=>{
    if(event.data?.type==='guest-ended'&&guestId===event.data.id) {
      ++authGeneration;pendingGuestExit=guestId;activate({user:null});
    } else if(event.data?.type==='session-changed')initialize();
  };
  window.addEventListener('storage',event=>{
    if(event.key===MARKER)initialize();
    else if(owner&&event.key===storageKey()) {dirty=true;saveMeta();scheduleSync();}
  });
  let lastRefresh=0;
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&(owner||guestId)&&Date.now()-lastRefresh>10000){lastRefresh=Date.now();initialize();}
  });

  return {
    initialize,flush,
    get user(){return user;},get status(){return status;},get owner(){return owner;},
    get isGuest(){return !!guestId;},
    get scope(){return guestId?`guest:${guestId}`:owner;},
    get ready(){return ready;},
    get hasAccess(){return !!guestId||(!!user&&status!=='expired')||(!user&&!!owner&&status==='offline');},
    async enterGuest(initialTheme) {
      const generation=++authGeneration;
      await request('/session');
      const data=await request('/guest',{method:'POST'});
      if(generation!==authGeneration)return;
      await activate(data,{initialTheme});
      channel?.postMessage({type:'session-changed'});
    },
    async register(fields,initialTheme) {
      const generation=++authGeneration;
      await request('/session');
      let data;
      try {data=await request('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});}
      catch(error) {
        if(['timeout','network','unavailable'].includes(error.code))error.message='We could not confirm your registration. Choose Sign in and use the same email and password before registering again.';
        throw error;
      }
      if(generation!==authGeneration)return;
      await activate(data,{fresh:true,initialTheme});channel?.postMessage({type:'session-changed'});return user;
    },
    async login(fields) {
      const generation=++authGeneration;
      await request('/session');
      const data=await request('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});
      if(generation!==authGeneration)return;
      await activate(data);channel?.postMessage({type:'session-changed'});return user;
    },
    async logout() {
      ++authGeneration;
      if(guestId) {
        const id=guestId;
        pendingGuestExit=id;
        // Clear immediately, even offline. The cookie contains no learning data.
        await activate({user:null});
        channel?.postMessage({type:'guest-ended',id});
        if(navigator.onLine)await request('/logout',{method:'POST',headers:{'X-Guest-Id':id}},false).then(()=>{if(pendingGuestExit===id)pendingGuestExit=null;}).catch(()=>{});
        return;
      }
      const complete=await flush();
      if(dirty&&!complete)throw new Error('Reconnect and sync your changes before signing out.');
      await activate(await request('/logout',{method:'POST',owned:true}));
      channel?.postMessage({type:'session-changed'});
    },
    async uploadPhoto(file) {
      const id=user?.id;
      const form=new FormData();form.append('photo',file);
      const data=await request('/avatar',{method:'PUT',body:form,owned:true,ownerId:id});
      if(user?.id!==id||owner!==id)throw new Error('The signed-in account changed. Refresh and try again.');
      user=data.user;emit();return user;
    },
    async removePhoto(){
      const id=user?.id,data=await request('/avatar',{method:'DELETE',owned:true,ownerId:id});
      if(user?.id!==id||owner!==id)throw new Error('The signed-in account changed. Refresh and try again.');
      user=data.user;emit();return user;
    },
  };
}
