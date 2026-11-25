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
- **Apple Calendar** on a site opens Apple's own New Event screen, filled in. That's FieldKey's
  own plugin in `app/ios/App/App/FieldKeyPlugins.swift`, registered by `FieldKeyViewController`
  (which `SceneDelegate.swift` creates) and called with `Capacitor.nativePromise`. A plugin
  registered this way isn't in `Capacitor.Plugins`.

| Folder | What it is |
|---|---|
| `app/package.json` | Capacitor, its Filesystem and Share plugins, and the bundled libraries; `npm run sync` copies the web app in |
| `app/capacitor.config.json` | App id `io.github.masterweeks.fieldkey`, name, colours |
| `app/ios/` | The Xcode project (Swift Package Manager, no CocoaPods) |
| `app/www/`, `app/ios/App/App/public/` | Generated copies of the web app, not in git |

## Plan

1. **Wrapper** (done): FieldKey runs as an app, online.
2. **Make everything work in the app** (in progress).
   - Done, tested in the simulator: offline maps, exports and backups through the share sheet,
     FieldKey's app icon and launch screen.
   - Done, to test on a phone: voice search and location use the web view's own speech and
     location, with the permission texts in `app/ios/App/App/Info.plist` (location, microphone,
     speech, and saving images to Photos). iOS closes an app that asks without them. If voice
     search doesn't work on the phone, switch it to a native speech plugin.
   - Left: the Google key (see below).
3. **AI email import** with Apple's on-device Foundation Models (iOS 26, iPhone 15 Pro or newer).
   Other phones keep the rules-based parser.
4. **CarPlay without Apple approval** (iOS 26): a "Today's sites" widget and a Live Activity
   ("Next site: SAP …, gate code …") on the CarPlay dashboard.
5. **A full CarPlay app**: request Apple's "driving task" entitlement.

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

Offline (turn on Airplane Mode after saving):
- **Save offline** an area and a mission, turn on Airplane Mode, quit and reopen the app, and
  open the map there. Try Dark, Aerial and Topo, and property lines if you saved them.

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

Raise **Version** or **Build** under the target's **General** tab for each new upload.
