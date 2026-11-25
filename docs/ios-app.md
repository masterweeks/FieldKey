# FieldKey iOS app

The iOS app wraps the FieldKey web app (the repo root) with [Capacitor](https://capacitorjs.com) 8.
The web app stays the source: `app/scripts/copy-web.mjs` copies it into the app and bundles MapLibre and html2canvas, which
the web version loads from a CDN. Cesium (the 3D view) still loads from cesium.com. Inside the app,
`window.Capacitor` is set, and `index.html` switches on `IS_NATIVE`: no service worker, and
updates come through TestFlight or the App Store.

| Folder | What it is |
|---|---|
| `app/package.json` | Capacitor and the bundled libraries; `npm run sync` copies the web app in |
| `app/capacitor.config.json` | App id `io.github.masterweeks.fieldkey`, name, colours |
| `app/ios/` | The Xcode project (Swift Package Manager, no CocoaPods) |
| `app/www/`, `app/ios/App/App/public/` | Generated copies of the web app, not in git |

## Plan

1. **Wrapper** (this step): FieldKey runs as an app, online.
2. **Make everything work in the app.**
   - Offline maps without a service worker: a tile store on the phone, read through MapLibre's
     protocol hook as the property lines already are.
   - Bundle Cesium so the 3D view loads without a connection.
   - Native plugins: voice search (Apple Speech), exports and backups (Files / Share sheet),
     location. Each permission needs its usage text in `app/ios/App/App/Info.plist`
     (for example `NSLocationWhenInUseUsageDescription`, `NSSpeechRecognitionUsageDescription`,
     `NSMicrophoneUsageDescription`), or iOS refuses the request without asking.
   - FieldKey's own app icon and launch screen (the project still has Capacitor's defaults).
   - An iOS key for Google address lookup and the 3D view.
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

## What to check on the phone (step 1)

These are expected to work online:
- The map, basemaps and every layer.
- Sites, site details, Text and Call.
- Sign-in and sync.
- Flyability and hospitals.

These are known gaps until step 2:
- **Offline maps** and saved areas (no service worker in the app).
- **Exports and backups:** the browser download may do nothing.
- **Voice search:** the app's web view may not allow it.
- **Google address lookup and 3D view:** they fail if the Google key only allows
  masterweeks.github.io. The 3D view also needs a connection to load Cesium.
- **App icon and launch screen** are Capacitor's defaults, including in TestFlight.
- **Check for update** says updates come through TestFlight.

Note anything else that behaves differently from the web app; that list becomes step 2.

## TestFlight (Developer Program)

1. In App Store Connect, create the app with the same bundle id.
2. In Xcode, choose **Any iOS Device** as the destination, then **Product → Archive**.
3. In the Organizer, choose **Distribute App → App Store Connect → Upload**.
4. In App Store Connect → **TestFlight**, add yourself or your team as testers.

Raise **Version** or **Build** under the target's **General** tab for each new upload.
