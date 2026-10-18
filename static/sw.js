// Bump this version after changing the app shell or vocabulary schema.
const CACHE = 'lexi-shell-v1';
const SHELL = [
  '/', '/manifest.webmanifest', '/static/css/style.css', '/static/js/app.js',
  '/static/js/theme-init.js', '/static/js/selection.js', '/static/js/storage.js',
  '/static/js/icons.js', '/static/fonts/Syne.ttf', '/static/fonts/DMSans.ttf',
  '/static/assets/orbit.svg', '/static/icons/icon.svg', '/static/icons/icon-192.png',
  '/static/icons/icon-512.png', '/api/catalog',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('lexi-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
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
