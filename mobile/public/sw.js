// Minimal app-shell service worker. It only caches same-origin GET requests
// (the static site itself) — never the backend API, which lives on a
// different origin (whatever the surveyor set as their server address) and
// must always hit the network so auth and survey data stay current. Without
// this, "Add to Home Screen" opens a browser error page the moment there's
// no signal, which defeats the point of an offline-first field app.
// v2: rewritten after a real, reproduced bug — the v1 strategy cached every
// same-origin GET indiscriminately. Each rebuild emits a uniquely-hashed JS
// bundle (e.g. /_expo/static/js/web/AppEntry-<hash>.js); once a client had an
// old index.html referencing a hash that no longer exists on the server,
// nginx's SPA fallback (`try_files ... /index.html`) served index.html's
// *HTML* content for that JS request instead of a 404 — and v1 happily
// cached that wrong response under the .js URL, making the corruption
// permanent regardless of future deploys. Confirmed live via
// "Failed to load module script: ... non-JavaScript MIME type of text/html".
//
// Fix: split the strategy. Hashed build assets are content-addressed and
// therefore safe to cache-first forever — a given hash's content never
// changes, so a cache hit is always correct. Everything else (the entry
// HTML, manifest.json) is mutable and must be revalidated against the
// network on every load, bypassing HTTP cache too (`cache: 'reload'`), since
// that's the thing that tells the browser which hash to load next.
const CACHE_NAME = 'geoplan-survey-shell-v2';
const APP_SHELL = ['/', '/manifest.json'];
const HASHED_ASSET = /\/_expo\/static\//;

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL).catch(() => {}))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // let API calls pass straight through

  if (HASHED_ASSET.test(url.pathname)) {
    // Content-addressed: a cache hit is always correct, never stale.
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return res;
      }))
    );
    return;
  }

  // Mutable entrypoint: always try the network fresh first (bypassing HTTP
  // cache, not just the SW cache), only falling back to a cached copy if
  // genuinely offline.
  event.respondWith(
    fetch(request, { cache: 'reload' })
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
  );
});
