const CACHE = "rugged-ai-shell-v2";
const APP = ["./", "./index.html", "./manifest.json", "./sw.js"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(APP)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  event.respondWith(caches.match(event.request).then(cached => {
    if (cached) return cached;
    return fetch(event.request).then(response => {
      if (response.ok) {
        const url = new URL(event.request.url);
        if (url.origin === self.location.origin || url.hostname === "esm.run") {
          const copy = response.clone();
          caches.open(CACHE).then(c => c.put(event.request, copy)).catch(() => {});
        }
      }
      return response;
    }).catch(() => cached);
  }));
});
