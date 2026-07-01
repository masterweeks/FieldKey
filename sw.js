/* FieldKey offline shell. Bump CACHE when app files change. */
const CACHE = "fieldkey-v40";          /* app shell + map engine (rebuilt on bump) */
const MAPCACHE = "fieldkey-maps";       /* basemap style/fonts/sprite/tiles (persists across bumps) */
const SHELL = [
  "./", "./index.html", "./manifest.webmanifest",
  "./icon-192.png", "./icon-512.png", "./icon-rounded-512.png", "./apple-touch-icon.png"
];
/* MapLibre engine — best-effort precache so the map code loads with no signal */
const ENGINE = [
  "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js",
  "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css"
];

/* Hosts whose responses are map basemap data we want available offline. */
function isMapResource(url) {
  const h = url.hostname;
  return h === "tiles.openfreemap.org"
      || h === "server.arcgisonline.com" || h.endsWith(".arcgisonline.com")
      || h === "tile.openstreetmap.org" || h.endsWith(".tile.openstreetmap.org")
      || h === "s3.amazonaws.com"          /* terrain DEM tiles (added in 3b) */
      || h === "basemap.nationalmap.gov"   /* USGS aerial (added in 3b) */
      || (h === "unpkg.com" && url.pathname.includes("maplibre-gl"));
}

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL).then(() =>
        Promise.allSettled(ENGINE.map(u =>
          fetch(u, { mode: "cors" }).then(r => { if (r.ok) return c.put(u, r); })
        ))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE && k !== MAPCACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Geocoding must always hit the network.
  if (url.hostname.includes("nominatim") || url.hostname.includes("googleapis")) return;

  // Map basemap data: cache-first, fill the persistent maps cache on miss.
  if (isMapResource(url)) {
    e.respondWith(
      caches.match(e.request).then(hit =>
        hit || fetch(e.request).then(res => {
          if (res && (res.ok || res.type === "opaque")) {
            const copy = res.clone();
            caches.open(MAPCACHE).then(c => c.put(e.request, copy)).catch(() => {});
          }
          return res;
        }).catch(() => hit)
      )
    );
    return;
  }

  // App shell: cache-first, network fallback, fill same-origin.
  e.respondWith(
    caches.match(e.request).then(hit =>
      hit || fetch(e.request).then(res => {
        if (res.ok && url.origin === location.origin) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => hit)
    )
  );
});
