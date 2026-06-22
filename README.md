# FieldKey — Access Request Builder

A phone app (PWA) that turns a CSV **or KML** of inspection sites into
copy-ready access requests. Pick a file → it finds your SAP ID / latitude /
longitude columns → plots every point on a map → reverse-geocodes each one to an
address → gives you one tappable, copyable request per site, plus batch
copy/share and `.txt` / `.csv` export.

Everything parses on-device; only the coordinates are sent out for address
lookup. The map needs an internet connection (it streams map tiles); everything
else works offline once installed.

The app has two tabs at the bottom:

### Requests
Import → map → confirm columns → build access requests → copy/share/export.
After building, **Save these to Customers** pushes the sites (SAP ID +
coordinates + resolved address) into the customer database for later.

### Customers
A persistent database on your phone for the contact info you collect back.

- **Import email** — paste the reply you get after sending the list. It
  reads each record (SAP Equipment ID, address, name, phone numbers, `AXS:`
  access, and any gate-code / instruction lines) and merges it into your sites,
  matching by **SAP ID first, then name, then address**. Coordinates from the
  import are kept; contact info from the email is added on top.
- **Import KML** — load any KML straight into the database (handy when a job is
  issued with access notes already on it, or to bring a brand-new daily KML into
  your history). FieldKey auto-detects the SAP / name / phone / access fields
  (adjust if needed) — including pulling phone numbers out of the **description**
  when that's where they're written — then merges: points that match a customer you already have
  **keep the phone, access, status, and text history you've collected** and just
  refresh today's location, brand-new points are added, and points you've built
  up that aren't in the new KML are left untouched. The day's batch is tagged so
  the **Latest KML** filter shows just today's assignment.
- **Text customers** — each customer has a one-tap **Text** button that opens
  Messages pre-filled with your template (the customer's first name and address
  fill in automatically). The app counts each send and marks the customer
  *Texted*. *Guided text* walks through everyone you haven't texted yet,
  one tap each (iOS doesn't allow an app to send texts silently or in bulk).
- **Track** — per-customer status (New / Texted / Replied / Scheduled / Done),
  a text counter, and your own notes. Filter chips and search across the list.
- **Map & export KML** — the **Map** button shows every customer that has
  coordinates. Tap pins to select, or pan/zoom to an area and hit *Select
  visible*, then **Export KML** of the selection — for handing off or reloading
  a reassigned area. The exported KML carries the name, phone, access, and
  status in each placemark, and re-imports into FieldKey cleanly.
- **Export** — `.csv` (opens in Excel/Numbers), `.json`, `.vcf` (imports every
  customer with a phone into Contacts), and `.kml` (all points with coordinates).

Edit the text-message template anytime in **Settings → Text message**.

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
