# FieldKey iOS app

The iOS app wraps the FieldKey web app (the repo root) with [Capacitor](https://capacitorjs.com) 8.
The web app stays the source: `app/scripts/copy-web.mjs` copies it into the app and bundles MapLibre and html2canvas, which
the web version loads from a CDN. Cesium (the 3D view) still loads from cesium.com; the 3D view
needs a connection for Google's 3D tiles anyway. Inside the app, `window.Capacitor` is set, and
`index.html` switches on `IS_NATIVE`:

- **No service worker.** Updates come through TestFlight or the App Store.
- **Offline maps** go through MapLibre's `fkc://` protocol (`mapGet()` in `index.html`) instead of
  `sw.js`: the saved copy first, otherwise the network (keeping a copy), otherwise a soft
  enlargement of a saved lower-zoom USGS tile. It uses the same Cache Storage and keys as the web
  version, so **Save offline** and the saved-maps list need no changes. Keep its host list in step
  with `isMapResource()` in `sw.js`.
- **Files** (exports, backups, calendar events, mission packages) are written to the app's cache
  folder and handed to the share sheet (`window.FieldKeyNative`, using the Filesystem and Share
  plugins), which offers Save to Files, Mail and AirDrop.
- **Native features** are FieldKey's own Capacitor plugins in `app/ios/App/App/`, registered in
  `FieldKeyViewController` (`FieldKeyPlugins.swift`, created by `SceneDelegate.swift`) and called
  from `index.html` with `Capacitor.nativePromise("<name>", "<method>", {...})`. Plugins
  registered this way aren't in `Capacitor.Plugins`.

| Plugin (file) | What it does in the app |
|---|---|
| `FieldKeyCalendar` (`FieldKeyPlugins.swift`) | **Apple Calendar** on a site opens Apple's New Event screen, filled in |
| `FieldKeyTexting` (`FieldKeyTexting.swift`) | Texts open Apple's message composer over FieldKey; iOS reports sent or cancelled |
| `FieldKeyLiveActivity` (`FieldKeyLiveActivity.swift`, `FieldKeyActivity.swift`) | Live Activities: guided texting progress and today's sites |
| `FieldKeyIntents` (`FieldKeyIntents.swift`) | Siri and Shortcuts: "Text the next site in FieldKey" |
| `FieldKeyCarPlay` (`FieldKeyCarPlay.swift`) | The CarPlay app's list of today's sites (built; waits for Apple, step 6) |
| `FieldKeyFiles` (`FieldKeyFiles.swift`) | "Open in FieldKey" for KML, KMZ and CSV files from Files, Mail, Safari or the share sheet |
| `FieldKeyAI` (`FieldKeyAI.swift`) | Email import with Apple's on-device model |

`app/ios/App/FieldKeyWidgets/` is a widget extension (its own target, iOS 18 or later) that draws
the Live Activities on the Lock Screen, in the Dynamic Island, and on the CarPlay dashboard.
Follow-up reminders use the official `@capacitor/local-notifications` plugin.

| Folder | What it is |
|---|---|
| `app/package.json` | Capacitor, its Filesystem, Share and Local Notifications plugins, and the bundled libraries; `npm run sync` copies the web app in |
| `app/capacitor.config.json` | App id `io.github.masterweeks.fieldkey`, name, colours |
| `app/ios/` | The Xcode project (Swift Package Manager, no CocoaPods): targets **App** and **FieldKeyWidgets** |
| `app/www/`, `app/ios/App/App/public/` | Generated copies of the web app, not in git |

## Plan

1. **Wrapper** (done): FieldKey runs as an app, online.
2. **Make everything work in the app** (done, except the Google key).
   - Offline maps, exports and backups through the share sheet, Apple Calendar, app icon and
     launch screen.
   - Voice search and location use the web view's own speech and location, with the permission
     texts in `app/ios/App/App/Info.plist` (location, microphone, speech, calendars, saving
     images to Photos). iOS closes an app that asks without them. If voice search doesn't work on
     the phone, switch it to a native speech plugin.
   - Left: the Google key (see Known gaps).
3. **Guided texting in the app** (done).
   - **Texts without leaving FieldKey:** Apple's composer slides up with the number and message
     filled in. A site is marked texted only when iOS says it was sent; a cancelled text stays on
     the same site. With **Settings → Guided texting: Open the next**, the next site's text opens
     by itself after each send. A **Skip** button moves past a site (also on the website).
   - **Follow-up reminders:** after a text, a notification such as "No reply from SAP 12345 ·
     Texted 24 hours ago. Text again?" (Settings: off, 4, 24 or 48 hours). Tapping it opens that
     site in the guided flow. Marking the site replied, scheduled or done cancels it. No server.
   - **Progress on the Lock Screen:** a Live Activity, "Texting · 7 of 23 sent / Next: SAP 12345",
     also in the Dynamic Island.
   - **Siri and Shortcuts:** "Text the next site in FieldKey" opens the list and the next
     un-texted site's text. Add it to the Action button or the home screen from the Shortcuts app.
4. **AI email import** (done): on iOS 26 with Apple Intelligence (iPhone 15 Pro or newer), Email
   return also reads the email with Apple's on-device model. The rules-based parser still runs;
   the model only fills empty fields and adds sites the rules missed, and what it returns must
   check out against the email (SAP ID and phone digits present; names, addresses and notes word
   for word). Nothing leaves the phone. Other phones keep the rules.
5. **CarPlay without Apple approval** (Live Activity done; widget waiting).
   - **Today's sites** Live Activity: "Next: SAP 12345 · 10:30 / Gate code 2211 · 412 Oak Ridge
     Rd", with done-of-total. It shows on the Lock Screen, in the Dynamic Island and, on iOS 26,
     on the CarPlay dashboard. It updates as sites change and ends when nothing is left today
     (Settings can turn it off). Sites count when their status is **Scheduled** for today.
   - **"Today's sites" home-screen and CarPlay widget:** waiting for the Developer Program. A
     widget runs outside the app, so it needs an **App Group** to read the app's data, and App
     Groups need a paid team.
6. **A full CarPlay app** (built; waiting for Apple): today's scheduled sites as a list on the
   car's screen, each with its time, access notes and address, and **Directions** (Apple Maps)
   and **Call** buttons. It shows the last list FieldKey saved today, even if the app was started
   from the car. It only appears in a car once Apple grants the entitlement; see "CarPlay
   entitlement" below.

## First run on your Mac

You need:
- **Xcode 26** (Mac App Store).
- **Node.js 22 or later** (nodejs.org).
- **Git**.
- An **Apple ID**.

To install on your own iPhone, a free Apple ID is enough; builds expire after 7 days. TestFlight
and the App Store need the Apple Developer Program ($99 a year).

1. Get the code and build the app's copy of the web app:

   ```sh
   git clone https://github.com/masterweeks/FieldKey.git
   cd FieldKey/app
   npm ci
   npm run sync
   npm run open
   ```

   Use `npm ci`, not `npm install`: it installs the exact versions in `package-lock.json`
   (Capacitor is listed as `^8.5.0`, so `npm install` can pull a newer 8.x).

   `npm run open` opens the project in Xcode. The first time, Xcode downloads Capacitor's Swift
   packages, which takes a minute.

2. Choose your signing team in Xcode:
   - Click **App** at the top of the left sidebar, then the **App** target.
   - Open **Signing & Capabilities**.
   - Tick **Automatically manage signing** and choose your **Team** (your Apple ID).
   - If Xcode says the bundle id is taken, change `io.github.masterweeks.fieldkey` here and in
     `app/capacitor.config.json` to something unique. Settle on it before your first TestFlight
     upload: App Store Connect ties the app to that id.

3. Plug in your iPhone and allow the Mac:
   - Connect the phone to the Mac by cable and tap **Trust** on the phone.
   - Turn on **Settings → Privacy & Security → Developer Mode** on the phone (it restarts). The
     switch only appears after the phone has been connected to Xcode once; if it's missing, pick
     the phone in Xcode's device menu, wait for Xcode to prepare it, then look again.
   - Pick the iPhone in Xcode's device menu at the top, then press **Run** (▶).
   - On a free Apple ID, the first launch needs **Settings → General → VPN & Device Management →**
     your Apple ID **→ Trust**.

## After changing the web app

```sh
cd app
npm run sync
```

Then press **Run** in Xcode. `sync` copies the web app in and updates the Swift packages.

## What to check on the phone

Online:
- The map, basemaps and every layer.
- Sites, site details, Text and Call.
- Sign-in and sync.
- Flyability and hospitals.
- **Voice search:** tap the mic, allow the microphone and speech recognition, say a site or
  address.
- **Location:** the locate button on the map, and Flyability's "use my location". iOS may ask
  twice (once for the app, once for the page).
- **Exports and backups:** each one opens the share sheet; **Save to Files** should keep the file.
  Also try **Restore** with a saved backup and a mission package download.
- **Apple Calendar** on a scheduled site: Apple's New Event screen opens filled in; tap **Add**.

Texting (needs a SIM or iMessage; the simulator can't text):
- **Text guide** on the list: Apple's composer opens over FieldKey. Send one: the site is marked
  texted and the next text opens by itself. Cancel one: the bar stays on that site.
- After the first sent text, iOS asks to allow notifications. Allow, then set **Settings →
  Remind me when there's no reply after → 4 h** to test sooner. Tap the reminder.
- While working a list, lock the phone: the Lock Screen shows "Texting · n of N sent".
- Say "Text the next site in FieldKey" to Siri.

Today's sites:
- Set two sites to **Scheduled** for today, lock the phone: the Lock Screen shows the next one.
  Mark it done: the next one takes its place. In a car with CarPlay on iOS 26, it's on the
  dashboard.

Opening files:
- In Files, Mail or Safari, tap a KML or KMZ, then the share button: FieldKey is in the list of
  apps. Choosing it opens FieldKey's import sheet with the sites found.

Email return:
- On an iPhone 15 Pro or newer with Apple Intelligence on, paste an email that doesn't follow the
  usual layout. The sheet says "On-device AI reads the email too", and the result line says how
  many records it filled in.

Offline (turn on Airplane Mode after saving):
- **Save offline** an area and a mission, turn on Airplane Mode, quit and reopen the app, and
  open the map there. Try Dark, Aerial and Topo, and property lines if you saved them.
- For sharp aerial past zoom 16, save from street level (zoom 15 or closer) with **Sharp
  close-ups** ticked, or save a mission (close-ups around each site).

Known gaps:
- **Google address lookup and 3D view:** they fail if the Google key only allows
  masterweeks.github.io. In Google Cloud → **APIs & Services → Credentials**, try adding
  `capacitor://localhost/*` to the key's website restrictions (not tested yet). If Google
  refuses that address or the lookups still fail, make a second key for the app with
  restrictions by API only, and enter it in the app's Settings.
- **Check for update** says updates come through TestFlight.

Note anything else that behaves differently from the web app.

## TestFlight (Developer Program)

1. In App Store Connect, create the app with the same bundle id.
2. In Xcode, choose **Any iOS Device** as the destination, then **Product → Archive**.
3. In the Organizer, choose **Distribute App → App Store Connect → Upload**.
4. In App Store Connect → **TestFlight**, add yourself or your team as testers.

Raise **Version** or **Build** under the target's **General** tab for each new upload. Change
them on **both** targets, **App** and **FieldKeyWidgets**: App Store Connect rejects an upload
whose extension version doesn't match the app's. If you change the app's bundle id, change the
extension's to match: it must be the app's id followed by `.widgets`.

## CarPlay entitlement (step 6)

A full CarPlay app (a list of today's sites with Call and Directions on the car's screen) needs
Apple to grant the **CarPlay driving task** entitlement. This needs the Developer Program.

**A map with the site pins in CarPlay** is a different category. Apple only lets **navigation**
apps draw a map in CarPlay, and a navigation app must give turn-by-turn directions with upcoming
maneuvers. Driving-task apps can't show a map; they show lists and cards and hand directions to
Apple Maps or Google Maps. An app gets one category, so asking for navigation means FieldKey would
first need its own turn-by-turn guidance (routes from Apple's MapKit, maneuver banners and spoken
instructions), and Apple may still decide a field-work app isn't a navigation app. The list built
here is what the driving-task category allows.

1. Join the Apple Developer Program.
2. Go to developer.apple.com/contact/carplay, sign in with the Developer Program account, accept
   the CarPlay Entitlement Addendum, and choose **Driving task**.
3. Describe the app, for example: "FieldKey helps utility inspectors work through a day of site
   visits. In the car, the driver needs the next site, its access notes (gate codes, dogs) and
   one-tap Call or Directions. The CarPlay app shows today's scheduled sites as a list with those
   actions and no other content."
4. Apple replies by email, which can take weeks. Once granted, the entitlement appears in your
   App ID's capabilities.
5. Switch it on for phone builds: in Xcode, select the **App** target → **Build Settings**, search
   for **Code Signing Entitlements**, and set it to `App/FieldKeySimulator.entitlements` for
   **Any SDK**, not only the simulator (or add the CarPlay capability under **Signing &
   Capabilities**). Then Run on the phone and connect to CarPlay.

The CarPlay app is already built (`FieldKeyCarPlay.swift`, and the CarPlay scene in
`Info.plist`). Until the entitlement is granted it's only switched on in simulator builds, so phone
builds keep signing with a free Apple ID. To try it: Run in the iOS Simulator, then in Simulator
choose **I/O → External Displays → CarPlay** and open FieldKey in the CarPlay window. Set a few
sites to **Scheduled** for today first.