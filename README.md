# FieldKey — Access Request Builder

A phone app (PWA) that turns a CSV **or KML** of inspection sites into an on-device
customer database and copy-ready access requests. Import a file → it finds your SAP
ID / latitude / longitude columns → reverse-geocodes each point to an address →
merges them into your database. Then select or filter the sites you want and build
batch access-request text, plus `.csv` / `.kml` export and SMS outreach.

Everything parses on-device; only the coordinates are sent out for address
lookup. The maps need an internet connection (they stream a vector basemap from
OpenFreeMap, plus Esri aerial or OpenStreetMap tiles depending on the basemap you
pick); everything
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
- **Map & export KML** — the **Map** button opens a **full-screen** map of the
  customers you're currently working with: whatever the filter/search is showing,
  or — if you've selected specific assets — just those. Close it with the **✕** in
  the top-left corner. The map is a fast vector map you can **rotate and
  tilt** (twist or drag with two fingers). Use the switcher in the top-left corner
  to pick a basemap: **Dark** (a clean low-glare vector style that matches the app),
  **Aerial** (high-resolution Esri imagery with road/place labels — often the most
  useful for spotting rooftops, access roads, and terrain on an inspection — which
  automatically switches to cached **USGS** imagery when you're offline), or
  **Streets**. Your choice is remembered. On the **Dark** basemap the map shows **terrain shading** (hillshade relief) so ridges and canyons read at a glance. For a stronger sense of the land, the **3D** button (top-left) tilts into a 3-D view — drag up with two fingers and the terrain physically rises, on any basemap (try it over **Aerial** for a draped-satellite view). 3D is on by default and remembered; tap the button to switch back to a flat map. Both are useful for sizing up access and approach in hilly country. When many sites sit close together they
  **cluster** into a single numbered circle — tap it to zoom in and split it apart.
  Individual pins are **colored by status** (grey = new, amber = texted, blue =
  replied, green = scheduled, red = access issue), with a legend along the bottom; a
  selected pin gets a bright gold ring. Pins are drawn as **3-D markers**, and under
  **Settings → Map pins** you can change their **shape** (Pin, Dot, Square, or
  Diamond) and **size** (Small, Medium, Large) — a live preview shows the look, and
  the change takes effect the next time you open the map. The location button (top-right, under the
  zoom controls) drops a live dot showing **your current location** with an accuracy
  ring and heading, and tracks it as you move — handy for seeing which site you're
  closest to. Tap it once to start; the browser will ask permission the first time.
  Location stops automatically when you close the map, to save battery. Tap a pin for
  a popup with the site name, access, and **Apple Maps / Google Maps** directions
  buttons. The action bar along the bottom is where you turn a selection into work:
  tap pins to add them one at a time, or hit **Lasso** and draw a freehand loop right
  on the map to grab every site inside it at once (drag to draw, lift to select — tap
  **Lasso** again to cancel; it adds to whatever's already selected, so **Clear**
  first if you want a fresh set). **Select visible** is the quick "grab everything on
  screen" shortcut. Lasso works even when sites are bunched into clusters, since it
  selects by location, not by visible pin. Then hit **Export KML** — of the pins you
  picked, or, if you haven't picked
  any, of everything shown on the map. Or tap **Build request email** to generate
  the access-request text (Requestor details from Settings + each site's SAP and
  address) for that same set, ready to copy or share/email. The exported KML
  carries the name, phone, access, and status in each placemark, and re-imports
  cleanly through **Import KML / CSV**.
- **Optimize route** — with sites selected (or all shown if none), tap **Optimize
  route** and FieldKey works out an efficient order to drive them, starting from your
  current GPS location. The ordering runs entirely on the device — no signal, no API
  key needed — so it works in the field the same as everything else. It shows the
  ordered stop list with per-leg distances, plus a total distance, drive-time, and
  fuel-cost estimate (set your vehicle **MPG**, **fuel price**, **average speed**, and
  **weight** under **Settings → Route & fuel**). The fuel estimate is **climb-aware**:
  FieldKey reads the elevation along the route from the same terrain tiles the map
  uses and adds the extra gas burned climbing, showing the total **feet of climb** in
  the summary. Elevation works online, or offline for any area you've saved with
  **Save offline** — outside a saved area with no signal it just notes the elevation
  isn't available and gives the flat estimate. A **Round trip** toggle re-optimizes as a loop
  back to your start. **Open route in Google Maps** hands the whole ordered run to
  Google Maps for real turn-by-turn driving (up to 10 stops per link — for a longer
  day it opens the first 10 and you build a second route for the rest). Apple Maps
  can't take a multi-stop route from a link, so on Apple Maps use the per-site
  directions on each pin instead. The optimizer measures in straight-line distance
  with a road-distance factor, which is why the mileage and fuel are estimates —
  your maps app gives the exact drive; this is for sequencing and rough planning.
- **Line of sight** — tap **Line of sight**, then tap the map to drop your
  parking/launch point. FieldKey walks the terrain between that point and each
  selected asset (or all shown) and tells you which ones you can actually **see** over
  the landscape — useful for judging whether you'll hold visual line of sight while
  flying. It draws a **green** line to each asset you can see and a **red** line to
  each one the terrain blocks, and lists them with a count. For blocked assets it
  reports the **altitude the drone clears at** ("clears above ~X ft"), so you know how
  high you'd need to fly to keep it in view. Asset height is adjustable right in the
  panel — a **Distribution** preset (~40 ft), a **Transmission** preset for taller
  lattice towers, or type any height; your own eye height is set once under
  **Settings → Route & fuel**. It accounts for earth curvature, and like the climb
  data it reads elevation online or from any area you've saved offline (outside a
  saved area with no signal it says so). Tap **Move parking point** to try another
  spot, or **Done** to clear the lines. Tap the summary (or the handle) to **collapse
  the panel to a peek** so you can see the map and sightlines, then tap again to bring
  the full results back — the **X** exits line-of-sight entirely.

  **Include tree canopy:** an opt-in toggle that folds tree height into the sightline,
  so a line crossing a tree stand reads as blocked even where the bare ground is clear.
  It tries to use the measured Meta/WRI 1-meter canopy map first, but that data is
  served from a store that (at least right now) doesn't allow a browser to read it
  directly — so in practice FieldKey falls back to a **typical tree height** you set
  (default 50 ft) and applies it along each sightline. Set it to match your territory's
  tree lines; a taller value is more conservative. This works offline and needs no
  signal. If measured 1-meter data is ever made reachable (e.g. through a small proxy),
  the toggle uses it automatically and the panel says "measured." Either way, buildings
  and structures aren't included, so treat the result as planning guidance and keep
  your own eyes on the aircraft.
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
- **Offline maps** — the map works with no signal for areas you've saved first.
  On the map, frame the area you'll be working (pan/zoom so it fills the screen),
  then tap **⤓ Save offline** (top-left, under the basemap switcher). It checks the
  size, shows roughly how many tiles and megabytes it'll store, and — once you tap
  **Save** — downloads the dark basemap for that area onto the device with a
  progress bar (tap **Stop** to halt; whatever finished is kept). After that, in a
  dead zone, opening the map still shows that area's roads and labels, your pins,
  and your live GPS location — everything but a data connection. The app shell and
  map engine are cached automatically, so the whole app launches offline once it's
  on your Home Screen; **Save offline** is only for the *map tiles* of a specific
  area. Saved tiles persist across app updates and stay until you remove them:
  **Settings → Offline maps** shows how many areas you've saved and the storage
  used, with **Clear offline maps** to free it all. Saving an area also stores the
  **terrain elevation** for it, so the hillshade relief and 3-D view keep working with
  no signal — and it's the same elevation data the upcoming parking-spot line-of-sight
  check will use. By default it **also saves aerial imagery** (USGS) for the area, so
  the **Aerial** basemap works offline too; because imagery is much larger, the save
  dialog has an **Include aerial imagery** switch you can turn off when you only want
  the lighter basemap-plus-terrain download (the tile count and size update live as you
  toggle it). So a saved area gives you the dark map with terrain, your pins, GPS, and
  aerial — all with no signal.

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
