// Service worker (cukrowa dusza). Dwa zadania: dzialanie bez zasiegu w kuchni
// oraz pewnosc, ze push do GitHuba faktycznie dociera na telefon.
//
// Zle napisany service worker potrafi zamrozic uzytkownika na starej wersji
// na zawsze - dlatego stale-while-revalidate zamiast cache-first,
// skipWaiting + clients.claim, i czyszczenie starych cache przy aktywacji.

const VERSION = '1.2.0';
const CACHE = `cukrowa-dusza-${VERSION}`;

const SHELL = [
  './', './index.html', './app.css', './manifest.webmanifest',
  './js/app.js', './js/ui.js', './js/calc.js', './js/money.js',
  './js/store.js', './js/prices.js', './js/github.js',
  './data/catalog.json', './data/prices.json',
  './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png',
  './icons/favicon-64.png', './icons/napis.png',
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // addAll przerywa calosc przy jednym 404 - wolimy zainstalowac co sie da.
    await Promise.all(SHELL.map(url =>
      cache.add(new Request(url, { cache: 'reload' })).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if ((key.startsWith('cukrowa-dusza-') || key.startsWith('tortownik-')) && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
    for (const client of await self.clients.matchAll()) {
      client.postMessage({ version: VERSION });
    }
  })());
});

const isPrices = url => url.pathname.endsWith('/data/prices.json');

self.addEventListener('fetch', e => {
  const { request } = e;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Ceny: najpierw siec. Lepiej dzisiejsza cena niz wczorajsza,
  // ale wczorajsza z cache jest lepsza niz zadna.
  if (isPrices(url)) {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        if (fresh.ok) (await caches.open(CACHE)).put(request, fresh.clone());
        return fresh;
      } catch {
        return (await caches.match(request)) ||
               new Response('{"products":{}}', { headers: { 'Content-Type': 'application/json' } });
      }
    })());
    return;
  }

  // Nawigacja i reszta powloki: natychmiast z cache, aktualizacja w tle.
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request, { ignoreSearch: true });

    const network = fetch(request).then(res => {
      if (res && res.ok && res.type === 'basic') cache.put(request, res.clone());
      return res;
    }).catch(() => null);

    if (cached) { e.waitUntil(network); return cached; }

    const fresh = await network;
    if (fresh) return fresh;
    if (request.mode === 'navigate') {
      return (await cache.match('./index.html')) ||
             new Response('Aplikacja jest offline i nie ma jeszcze kopii w pamięci.',
                          { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
    }
    return new Response('', { status: 504 });
  })());
});

self.addEventListener('message', e => {
  if (e.data === 'skipWaiting') self.skipWaiting();
  if (e.data === 'version') e.source?.postMessage({ version: VERSION });
});
