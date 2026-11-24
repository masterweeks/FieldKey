/* FieldKey offline shell. Bump CACHE when app files change. */
const CACHE = "fieldkey-v82";          /* app shell + map engine (rebuilt on bump) */
const MAPCACHE = "fieldkey-maps";       /* basemap style/fonts/sprite/tiles (persists across bumps) */
const SHELL = [
  "./", "./index.html", "./flyability.html", "./view3d.html", "./sync-engine.js", "./export-plan.js", "./search-text.js", "./manifest.webmanifest",
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
      || h === "imagery.nationalmap.gov"   /* USDA NAIP close-ups (v76) */
      || h === "tiles.arcgis.com"          /* Regrid free parcel-boundary tiles */
      || (h === "unpkg.com" && url.pathname.includes("maplibre-gl"));
}

/* Offline, a USGS imagery/topo tile that wasn't saved is drawn from the nearest saved lower-zoom
   tile (cropped and enlarged), so the map looks soft instead of blank. Only these photo/map tiles:
   terrain tiles encode heights in their colours and can't be resampled. */
const USGS_RASTER = /^(https:\/\/basemap\.nationalmap\.gov\/arcgis\/rest\/services\/(?:USGSImageryOnly|USGSTopo)\/MapServer\/tile\/)(\d+)\/(\d+)\/(\d+)$/;
async function parentTile(url) {
  const m = USGS_RASTER.exec(url);
  if (!m || typeof OffscreenCanvas === "undefined" || typeof createImageBitmap === "undefined") return null;
  const base = m[1], z = +m[2], y = +m[3], x = +m[4];
  for (let d = 1; d <= 8 && z - d >= 0; d++) {
    const hit = await caches.match(base + (z - d) + "/" + (y >> d) + "/" + (x >> d));
    if (!hit || hit.type === "opaque") continue;       // an opaque tile can't be read back
    try {
      const img = await createImageBitmap(await hit.blob());
      const part = img.width / (1 << d);               // size of our piece inside the parent
      const sx = (x - ((x >> d) << d)) * part, sy = (y - ((y >> d) << d)) * part;
      const c = new OffscreenCanvas(256, 256), g = c.getContext("2d");
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
      g.drawImage(img, sx, sy, part, part, 0, 0, 256, 256);
      const blob = await c.convertToBlob({ type: "image/jpeg", quality: 0.85 });
      return new Response(blob, { headers: { "Content-Type": "image/jpeg", "X-FieldKey-From-Zoom": String(z - d) } });
    } catch (err) { return null; }
  }
  return null;
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

self.addEventListener("message", e => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
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
        }).catch(() => parentTile(e.request.url).then(r => r || Response.error()))
      )
    );
    return;
  }

  // App shell: NETWORK-FIRST so a fresh deploy shows up the moment you're online,
  // with a fast fall-back to cache when the network is slow or unavailable (field use).
  // no-store bypasses the browser's HTTP cache so we always see the newest commit.
  e.respondWith((async () => {
    const fromCache = () => caches.match(e.request);
    try {
      const netP = fetch(e.request, { cache: "no-store" }).then(res => {
        if (res && res.ok && url.origin === location.origin) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
        }
        return res;
      });
      // Race the network against a 3.5s timeout; if it wins with a cache hit, use it.
      const timeout = new Promise(r => setTimeout(() => r("__timeout__"), 3500));
      const winner = await Promise.race([netP.catch(() => "__neterr__"), timeout]);
      if (winner && winner !== "__timeout__" && winner !== "__neterr__") return winner;
      const hit = await fromCache();
      if (hit) return hit;
      return await netP; // no cache: wait for the network (may still succeed/last-error)
    } catch (err) {
      const hit = await fromCache();
      if (hit) return hit;
      throw err;
    }
  })());
});
