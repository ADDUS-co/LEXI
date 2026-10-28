// Bump this version after changing the app shell or vocabulary schema.
const CACHE = 'lexi-shell-v29';
const SHELL = [
  '/', '/manifest.webmanifest', '/static/css/style.css', '/static/css/experience.css', '/static/css/account.css', '/static/css/entry.css', '/static/js/app.js',
  '/static/js/theme-init.js', '/static/js/selection.js', '/static/js/storage.js',
  '/static/js/icons.js', '/static/js/schedule.js', '/static/js/recall.js', '/static/fonts/Syne.ttf', '/static/fonts/DMSans.ttf',
  '/static/js/account-service.js', '/static/js/account-ui.js', '/static/js/onboarding-guide.js', '/static/js/reading-guide.js', '/static/js/recall-demo.js', '/static/css/onboarding-guide.css',
  '/static/assets/orbit.svg', '/static/icons/icon.svg', '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('lexi-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
  if(event.data?.type !== 'LEXI_CACHE_CATALOG') return;
  // The first authenticated page can load before this worker takes control.
  // Fetch with the real session; never pre-cache a protected endpoint at install.
  event.waitUntil(fetch('/api/catalog', {credentials:'same-origin', cache:'no-store'}).then(async response => {
    if(response.ok)await(await caches.open(CACHE)).put('/api/catalog',response);
  }).catch(()=>{}));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // Account responses, profile photos, and CSRF tokens are never cached.
  if (url.pathname.startsWith('/api/account') || url.pathname === '/auth/complete') return;
  if (!(event.request.mode === 'navigate' || url.pathname.startsWith('/static/') || url.pathname === '/api/catalog' || url.pathname === '/manifest.webmanifest')) return;
  // Network first: online edits are visible after refresh; offline uses last good data.
  event.respondWith(fetch(event.request).then(async response => {
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(event.request, response.clone());
    }
    return response;
  }).catch(async () => {
    const cached = await caches.match(event.request);
    if (cached) return cached;
    if (event.request.mode === 'navigate') return caches.match('/');
    return new Response('This resource is not cached. Connect once and reload LEXI.', {status: 503, headers: {'Content-Type': 'text/plain'}});
  }));
});
