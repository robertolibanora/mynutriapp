const CACHE_NAME = 'nutriapp-v8';
const urlsToCache = [
  '/',
  '/login',
  '/user/dashboard',
  '/progressi/user',
  '/documenti/user/',
  '/appuntamenti/user',
  '/user/profilo',
  '/static/css/style_user.css',
  '/static/css/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png'
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
  
  // JS: Network First (evita script admin/user obsoleti dopo deploy)
  if (e.request.url.includes('/static/') && e.request.url.includes('.js')) {
    e.respondWith(
      fetch(e.request).then((fetchResponse) => {
        if (fetchResponse && fetchResponse.status === 200) {
          const responseClone = fetchResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, responseClone);
          });
        }
        return fetchResponse;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

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