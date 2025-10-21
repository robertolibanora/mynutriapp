const CACHE_NAME = 'nutriapp-v1';
const urlsToCache = [
  '/',
  '/login',
  '/user/dashboard',
  '/user/progressi',
  '/user/documenti',
  '/user/appuntamenti',
  '/user/profilo',
  '/user/listino',
  '/static/css/style_user.css',
  '/static/css/style.css',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/logo.png',
  '/static/manifest.json'
];

self.addEventListener('install', (e) => {
  console.log('🔧 Service Worker: Install');
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('📦 Service Worker: Caching files');
      return cache.addAll(urlsToCache);
    })
  );
});

self.addEventListener('activate', (e) => {
  console.log('🚀 Service Worker: Activate');
  e.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('🗑️ Service Worker: Deleting old cache');
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

self.addEventListener('fetch', (e) => {
  console.log('🌐 Service Worker: Fetch', e.request.url);
  
  // Strategia: Cache First per risorse statiche, Network First per pagine
  if (e.request.url.includes('/static/')) {
    // Cache First per risorse statiche
    e.respondWith(
      caches.match(e.request).then((response) => {
        return response || fetch(e.request).then((fetchResponse) => {
          // Cache la risposta per il futuro
          return caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, fetchResponse.clone());
            return fetchResponse;
          });
        });
      })
    );
  } else {
    // Network First per pagine HTML
    e.respondWith(
      fetch(e.request).then((response) => {
        // Se la richiesta è riuscita, cache la risposta
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, responseClone);
          });
        }
        return response;
      }).catch(() => {
        // Se la rete fallisce, prova la cache
        return caches.match(e.request);
      })
    );
  }
});