const CACHE_NAME = 'netlifegy-v1';
const OFFLINE_URL = '/offline';

const PRECACHE = [
  '/',
  '/offline',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  'https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://unpkg.com/feather-icons',
];

// Install: pre-cache shell assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.allSettled(PRECACHE.map(url => cache.add(url)));
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first for navigation, cache-first for assets
self.addEventListener('fetch', event => {
  const { request } = event;

  // Skip non-GET and cross-origin (except CDN assets we pre-cached)
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Cache-first for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(c => c.put(request, clone));
        return response;
      }))
    );
    return;
  }

  // Network-first for HTML navigation
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_URL).then(r => r || new Response('You are offline', { status: 503 }))
      )
    );
    return;
  }

  // Default: network with cache fallback
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
