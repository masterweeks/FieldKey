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

### Requests — bring data in
Load a CSV or KML → map → confirm the SAP / latitude / longitude columns →
**Build** (reverse-geocodes every point to an address) → copy/share/export the
access requests.

After building, **Save these to Customers** is the single way data enters the
database. It runs every check on the file — detecting the customer name, phone
(including numbers buried in a KML's **description**), and access columns — then
saves each point with its SAP ID, coordinates, **geocoded address**, name,
phone, and access. It **merges** into what's already there: a point that matches
an existing customer (by SAP ID, then name, then address) updates that record
and keeps the phone / access / status / text history you've collected; brand-new
points are added; points already in the database that aren't in this file are
left untouched. The file is tagged so the **Latest KML** filter in Customers
shows just that batch.

This is also how a fresh daily KML gets merged with everything you've built up,
and — because it geocodes — how those points finally get addresses.

### Customers — your database
A persistent, on-device view of every site you've collected. The header shows
how many are in the database, and **Clear database** wipes it (with a
confirmation). Tap any customer to see the full record — phones, access with
gate codes, address, coordinates, which file it came from, and any extra fields —
plus **Apple Maps / Google Maps** directions buttons when the site has
coordinates.

- **Import email return** — paste the reply you get after sending a list. It
  reads each record (SAP Equipment ID, address, name, phone numbers, `AXS:`
  access, and any gate-code / instruction lines) and merges it in by **SAP ID,
  then name, then address**. The email's address, name, and phones are taken as
  authoritative; coordinates you already have are kept. (KML files don't get
  imported here — they go through **Requests** so they pick up addresses.)
- **Text customers** — each customer has a one-tap **Text** button that opens
  Messages pre-filled with your template (first name and address fill in
  automatically). The app counts each send and marks the customer *Texted*.
  *Guided text* walks through everyone you haven't texted yet, one tap each
  (iOS doesn't allow an app to send texts silently or in bulk).
- **Track** — per-customer status (New / Texted / Replied / Scheduled / Done),
  a text counter, and your own notes. Filter chips (including **Latest KML**)
  and search across the list.
- **Map & export KML** — the **Map** button shows every customer that has
  coordinates. Tap a pin for a popup with the site name, access, and **Apple
  Maps / Google Maps** buttons that open turn-by-turn driving directions to that
  point. Tap pins to select, or pan/zoom to an area and hit *Select visible*,
  then **Export KML** of the selection — for handing off or reloading a
  reassigned area. The exported KML carries the name, phone, access, and status
  in each placemark, and re-imports cleanly (through Requests).
- **Select & export** — every row has a circle on the left; tap it to pick
  specific assets (a bar shows how many are selected). **Export** then covers
  exactly what you've chosen — or, if nothing is selected, whatever the current
  **filter and search** are showing. The export sheet states the scope ("Exporting
  3 selected customers" / "Exporting 12 customers (Latest KML)") before you pick a
  format: `.csv` (opens in Excel/Numbers), `.json`, `.vcf` (imports every
  customer with a phone into Contacts), and `.kml` (the selected points that have
  coordinates). All exported text is plain and readable — any HTML that came in
  from a KML's description is stripped to clean text (on import, on export, and
  when an older database is first opened in this version).

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
