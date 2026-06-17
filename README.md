# FieldKey — Access Request Builder

A phone app (PWA) that turns a CSV of inspection sites into copy-ready access
requests. Pick a CSV → it finds your SAP ID / latitude / longitude columns →
reverse-geocodes each point to an address → gives you one tappable, copyable
request per site, plus batch copy/share and `.txt` / `.csv` export.

Everything parses on-device; only the coordinates are sent out for address lookup.

## Files
- `index.html` — the whole app
- `manifest.webmanifest`, `sw.js` — make it installable + work offline
- `icon-*.png`, `apple-touch-icon.png` — home-screen icons

## Install on iPhone (no Mac, no App Store)
1. Put these files on any HTTPS host. Easiest free option: a GitHub repo with
   **Pages** turned on (Settings → Pages → deploy from branch). You'll get a
   `https://…github.io/…/` link.
2. Open that link in **Safari** on your iPhone.
3. Tap **Share** → **Add to Home Screen**.
4. Launch it from the icon — full screen, works offline after first open.

## Notes
- Default address lookup is **OpenStreetMap** (free, no key). Keep the lookup
  delay at ~1100 ms to respect its 1-request-per-second policy.
- For higher volume/precision, switch to **Google** in Settings and paste your
  own Maps JavaScript API key.
- Requestor name / LanID / phone / descriptions live in **Settings** and are
  saved on the device.
