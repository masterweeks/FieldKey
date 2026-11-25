// Copies the FieldKey web app (the repo root) into app/www, the folder Capacitor packs into the iOS app.
// The app can't use the service worker, so libraries the web version loads from a CDN are bundled
// here instead, at the same versions, and the copied pages point at the local copies.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const app = join(dirname(fileURLToPath(import.meta.url)), "..");
const site = join(app, "..");
const www = join(app, "www");

const FILES = [
  "index.html", "sync-engine.js", "export-plan.js", "search-text.js", "flyability.html", "view3d.html",
  "manifest.webmanifest", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-rounded-512.png",
];
// sw.js stays out: service workers don't run in the iOS app (index.html skips registering it there)

const VENDOR = [   // [CDN address in the pages, file in node_modules, local path in www]
  ["https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js", "maplibre-gl/dist/maplibre-gl.js", "vendor/maplibre-gl.js"],
  ["https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css", "maplibre-gl/dist/maplibre-gl.css", "vendor/maplibre-gl.css"],
  ["https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js", "html2canvas/dist/html2canvas.min.js", "vendor/html2canvas.min.js"],
];

rmSync(www, { recursive: true, force: true });
mkdirSync(join(www, "vendor"), { recursive: true });

for (const f of FILES) {
  if (!existsSync(join(site, f))) throw new Error("Missing " + f + " in the web app");
  cpSync(join(site, f), join(www, f));
}
for (const [, from, to] of VENDOR) {
  const src = join(app, "node_modules", from);
  if (!existsSync(src)) throw new Error("Missing " + from + ": run npm install in app/ first");
  cpSync(src, join(www, to));
}

let pointed = 0;
for (const page of ["index.html", "flyability.html"]) {
  const p = join(www, page);
  let html = readFileSync(p, "utf8");
  for (const [cdn, , local] of VENDOR) {
    if (html.includes(cdn)) { html = html.split(cdn).join(local); pointed++; }
  }
  writeFileSync(p, html);
}
if (pointed !== VENDOR.length) {
  throw new Error(`Expected to point ${VENDOR.length} CDN links at local files, found ${pointed}. Did a library version change in the web app?`);
}
console.log(`Copied ${FILES.length} files and ${VENDOR.length} bundled libraries into app/www`);
