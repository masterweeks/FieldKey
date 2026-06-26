# FieldKey — Access Request Builder

A phone app (PWA) that turns a CSV **or KML** of inspection sites into an on-device
customer database and copy-ready access requests. Import a file → it finds your SAP
ID / latitude / longitude columns → reverse-geocodes each point to an address →
merges them into your database. Then select or filter the sites you want and build
batch access-request text, plus `.csv` / `.kml` export and SMS outreach.

Everything parses on-device; only the coordinates are sent out for address
lookup. The maps need an internet connection (they stream map tiles — OpenStreetMap,
CARTO, or Esri aerial imagery depending on the basemap you pick); everything
else works offline once installed.

Everything happens on one screen — your customer database. Data comes in at the
top, and you build access requests from whatever you've selected or filtered to.

Any panel that slides up — an asset's details, the map, build-request, import,
settings, and so on — has a **✕** button in its top-right corner to close it and go
back. (Opening one panel from another, like build-request from the map, returns you
to where you were.) You can also tap the dimmed area behind a panel to dismiss it.

### Bringing data in
**Import KML / CSV** takes your daily site file. It auto-detects the SAP ID,
latitude, and longitude — for a CSV it shows those columns so you can confirm or fix
them; a KML's coordinates are unambiguous, so it skips straight through — then shows
**"N assets found."** Tap **Import** and it reverse-geocodes every point to a street
address (with a progress bar) and saves the batch into the database in one step —
there's no separate "save." It **merges** into what's already there: a point that
matches an existing customer (by SAP ID, then name, then address) updates that
record and keeps the phone / access / status / text history you've collected;
brand-new points are added; anything already in the database that isn't in this file
is left untouched. The file is tagged and the view auto-filters to **Latest KML** so
you immediately see just what you loaded — which is also the set you'll usually build
requests for. (Import runs the geocode; if you pick the wrong file, **Cancel** stops
it before anything is saved, and the daily snapshot is your undo otherwise.)

This is how a fresh daily KML both gets merged with everything you've built up and —
because it geocodes — finally gets addresses.

### Building access requests
**Build request** — in the toolbar, in the selection bar once you've picked assets,
and on the map — generates copy-ready access-request text: Requestor details from
Settings plus each site's SAP ID and address. It acts on **whatever you've selected
or filtered to** — tick specific rows (or map pins) to build for just those, or leave
nothing selected and it builds for everything currently shown (e.g. the whole *Latest
KML* batch). The preview shows the count before you copy or share.

### Your database
A persistent, on-device view of every site you've collected. The header shows
how many are in the database. Tap any customer to see the full record — phones,
access with gate codes, address, coordinates, which file it came from, and any
extra fields — plus **Apple Maps / Google Maps** directions buttons when the site
has coordinates. (Backing up, restoring, rolling back to an earlier day, and
clearing the database all live in **Settings → Data** — see below.)

- **Import email return** — paste the reply you get after sending a list. It
  reads each record and merges it in by **SAP ID, then name, then address**. The
  SAP ID is matched **by its structure** — a standalone 9-digit number — so it's
  found whether the sender labels it "SAP Equipment ID", "SAP ID", "Equipment ID",
  or doesn't label it at all. Phone numbers are pulled out **wherever they appear**
  — even mid-line (e.g. `Mobile Primary  (541) 591-3438`) — and odd dash
  characters that email programs sometimes substitute (en-dashes, etc.) are handled.
  The email's address, name, and phones are taken as authoritative; coordinates you
  already have are kept. (This is for email replies only — site files go through
  **Import KML / CSV** so they pick up addresses.)
- **Text customers** — each customer has a one-tap **Text** button that opens
  Messages pre-filled with your template (first name and address fill in
  automatically). The app counts each send and marks the customer *Texted*.
  *Guided text* walks through everyone you haven't texted yet, one tap each
  (iOS doesn't allow an app to send texts silently or in bulk).
- **Track** — per-customer status (New / Texted / Replied / Scheduled / Done),
  a text counter, and your own notes. Marking a customer **Scheduled** reveals a
  date/time picker that's saved to the database (and shown on the row), plus
  **Apple Calendar** and **Google Calendar** buttons that create a real 30-minute
  inspection event — pre-filled with the site name, address, phone, access notes,
  and a directions link. Filter chips (including **Latest KML** and **Selected**,
  which shows whatever you've picked in the list or on the map) and a search box
  that matches name, address, SAP ID, or **phone number** — phone matching ignores
  formatting, so `5303398783`, `530-339-8783`, or even just the last few digits
  all find the right customer.
- **Map & export KML** — the **Map** button plots the customers you're currently
  working with: whatever the filter/search is showing, or — if you've selected
  specific assets — just those. Use the switcher in the top-right corner to pick a
  basemap: **Dark** (a clean low-glare style that matches the app), **Satellite**
  (high-resolution aerial imagery with road/place labels — often the most useful
  for spotting rooftops, access roads, and terrain on an inspection), or
  **Streets**. Your choice is remembered. The crosshair button (under the zoom
  controls) drops a live blue dot showing **your current location**, with an
  accuracy ring, and tracks it as you move — handy for seeing which site you're
  closest to. It centers on you the first time you tap it; tap again to turn it
  off (it also stops automatically when you close the map, to save battery). The
  first time, your browser will ask permission to use your location. Tap a pin for
  a popup with the site name, access, and **Apple Maps / Google Maps** directions
  buttons. Tap pins to refine a selection, or pan/zoom to an area and hit *Select
  visible*, then **Export KML** — of the pins you tapped, or, if you haven't tapped
  any, of everything shown on the map. Or tap **Build request email** to generate
  the access-request text (Requestor details from Settings + each site's SAP and
  address) for that same set, ready to copy or share/email. The exported KML
  carries the name, phone, access, and status in each placemark, and re-imports
  cleanly through **Import KML / CSV**.
- **Select & export** — every row has a circle on the left; tap it to pick
  specific assets (a bar shows how many are selected). This is the same selection
  you build by tapping pins on the **Map**, and the **Selected** filter shows it.
  **Export** then covers exactly what you've chosen — or, if nothing is selected,
  whatever the current **filter and search** are showing. The export sheet states
  the scope ("Exporting 3 selected customers" / "Exporting 12 customers (Latest
  KML)") before you pick a format: `.csv` (opens in Excel/Numbers), `.json`, `.vcf`
  (imports every customer with a phone into Contacts), and `.kml` (the selected
  points that have coordinates). All exported text is plain and readable — any HTML
  that came in from a KML's description is stripped to clean text (on import, on
  export, and when an older database is first opened in this version).
- **Access issues** — flag any site you couldn't get into. Open a site and tap
  **Flag access issue**, then pick a reason (Locked gate / Need gate code / No
  answer / Aggressive dog / Customer refused / Can't locate / Other → free text).
  To flag several at once, select them (row circles *or* map pins) and hit **Mark
  access issue** — in the selection bar or on the map sheet — then pick one reason
  for the whole batch (or "Flag now, set reason later"). Flagged sites show a solid
  **red dot** on the map (a red dot with a bright ring when also selected), and in
  the list they get a bold **red left border**, a red **ACCESS ISSUE** badge, and
  the reason. The flag is independent of status — a site can be *Texted* or
  *Scheduled* and still flagged — so it stays red until you clear it (open the site
  → **Clear flag**, or select flagged sites → the button flips to **Clear access
  issue**). The red **Access issue** filter chip pulls up just the problem sites in
  one tap, and CSV exports include **Access Issue** and **Issue Reason** columns.
  Flagging is purely visual — it doesn't pull a site out of your Not-texted /
  Scheduled / etc. views.

### Settings → Data
- **Back up data** downloads a single `.json` file with every customer and your
  Settings — keep it somewhere safe (Files, email, cloud).
- **Restore from backup** reads that file back in, replacing the current database
  (after a confirmation).
- **Earlier versions** — FieldKey automatically snapshots the database the first
  time you open it each day (the last 14 days are kept). Restore any of them to
  roll the whole database back to how it looked that morning — useful if a day's
  import or edits went sideways.
- **Clear database** wipes everything (with a confirmation). Moved here so it's
  out of the way of day-to-day work.

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
