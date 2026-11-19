# Mission packages (GeoPackage export)

A mission package is one `.gpkg` file with a mission's data, ready for QGIS, ArcGIS Pro, or a
client. FieldKey asks for it; a small worker builds it on a server and FieldKey downloads it.

```
FieldKey ──insert──▶ export_jobs (Supabase) ──wake-up call──▶ export worker (Docker, GDAL)
   ▲                                                              │ reads missions/assets/pins…
   └── signed download link ◀── private "exports" bucket ◀───────┘ uploads the .gpkg
```

## What's in a package

| Layer | Contents |
|---|---|
| `missions` | the chosen missions |
| `assets` ("Sites") | every site in those missions, with status, access, notes, schedule |
| `pins` | pins tied to the mission or its sites, plus loose pins (parking, gates…) inside the area |
| `circuits`, `inspections`, `photos` | linked rows; photos are metadata + storage path only, not the image files |
| `package_info` | missions, date, counts, whether contacts are included, basemap credits and licences |
| `layer_styles` | the same QGIS styles as the live project, applied automatically when a layer is added |
| `basemap_<id>` | optional offline tiles (only sources approved below) |

- **Names and phone numbers are left out by default.** Ticking "Include names and phone numbers"
  adds the `name` and `phones` columns. Free-text notes are always included, so keep personal
  details out of notes on client jobs.
- Deleted rows are never exported. Owner ids and the internal audit columns are not exported.
- In packages without names, the site labels show the SAP ID.
- **Coordinates:** data-only packages use EPSG:4326 (latitude/longitude). Packages with a basemap
  write everything in EPSG:3857 (Web Mercator), because QGIS gives a GeoPackage's basemap layers
  the CRS of its vector layers and would otherwise put the map in the wrong place. QGIS and ArcGIS
  reproject either on the fly. `package_info` records which one (`vector_crs`).

## Size estimate and cap

FieldKey shows an estimate before you request, using the same rules as the worker
(`export-plan.js` and `worker/fieldkey_export/tiles.py`, tested against one shared fixture).

- **Tiles:** at each zoom, the whole mission area is taken while it fits in 64 tiles; past that,
  only tiles within the chosen distance (150 m – 2 km) of each site. A spread-out mission doesn't
  pull in the empty land between sites.
- **Estimate:** about 0.5 MB for the file and styles, plus ~1 KB a feature, plus tiles × the
  source's typical tile size.
- **Cap: 45 MB.** Supabase's Free plan won't store a file over 50 MB. FieldKey blocks a request
  that's over, the worker re-checks the estimate before downloading anything, watches the real
  file size while downloading, and fails the job with a clear message if it grows past the cap.
  On a paid Supabase plan the cap can go up to 1,000 MB: see
  [Raising the 45 MB cap](#raising-the-45-mb-cap-paid-supabase-plan).
- Other limits: 3 exports in progress and 30 a day per account; at most 50 missions per package.
- Finished packages can be downloaded for 14 days (`EXPIRE_DAYS`), then the file is deleted and the
  job shows "Expired". Request it again if you need it.

### Raising the 45 MB cap (paid Supabase plan)

The cap lives in four places, and each one has to allow the new size. Below, **N** is the new cap
in MB (the database accepts up to 1000). The bucket gets 5 MB of headroom above N.

Do them in this order. Then, if you stop halfway, the phone still asks for the old, smaller size,
and nothing fails.

1. **Supabase project upload limit.** Dashboard → **Storage** → **Settings** → *Upload file size
   limit*: set it to at least **N + 5 MB** and save. The Free plan is stuck at 50 MB, so this is the
   step that needs the paid plan.

2. **The `exports` bucket.** Add a new migration file to the repo, for example
   `supabase/migrations/<timestamp>_raise_export_cap.sql`, and apply it (Supabase SQL Editor, or
   `supabase db push`). For N = 200 that's 205 MB:
   ```sql
   -- Raise the mission package bucket limit to 205 MB (cap 200 MB + 5 MB headroom).
   update storage.buckets
   set file_size_limit = 205 * 1048576
   where id = 'exports';
   ```
   Check it: `select file_size_limit / 1048576 as mb from storage.buckets where id = 'exports';`

3. **The worker.** Set `MAX_PACKAGE_MB` to N. The worker loads the finished file into memory to
   upload it, so give it at least 2 × N MB plus 512 MB of memory (for 200 MB: 1Gi is enough;
   for 500 MB: 2Gi). On Cloud Run:
   ```
   gcloud run services update fieldkey-export --region us-west1 \
     --update-env-vars MAX_PACKAGE_MB=200 --memory 1Gi
   ```
   That restarts the worker with the new value (no rebuild). On another host, change
   `MAX_PACKAGE_MB` in `worker/.env` and restart the container.

4. **FieldKey.** In `index.html`, change the one line
   ```js
   const PKG_CAP_MB=45;                     // Supabase Free plan: 50 MB per stored file
   ```
   to `const PKG_CAP_MB=200;`. Then make the usual release bump so phones pick it up: `CACHE` in
   `sw.js` and `APP_VER` in `index.html`. Commit and push.

To check it worked: open FieldKey → Export → Mission package. The estimate line should end in
"(limit 200 MB)". Build a package bigger than 45 MB and it should finish as "Ready".

Things to know before going big:
- Every finished package counts toward your Storage space for 14 days. Lower `EXPIRE_DAYS` (same
  way as step 3) if space is tight.
- Downloading a few hundred MB over a cell connection is slow; Wi-Fi is better for big packages.
- To go back down, do the steps in reverse order: phone first, then the worker, then the bucket.

## Basemap sources and licensing

A source is enabled only after you approve it, by a migration that inserts it into
`export_tile_sources` (with its licence and credit, which are written into every package).
**Approved 2026-11-18: USGS Topo and USGS Imagery** (migration `20261118231121_approve_usgs_tile_sources.sql`).
Both are cached to zoom 16 and served as JPEG. Their size estimates use the 90th percentile of
sampled tiles (Topo 28 KB, Imagery 36 KB), so estimates run about 20% high. A test package of
8 sites around Redding with both basemaps at zoom 10–16 came out at 7.0 MB (estimated 8.6 MB) and
built in about 11 seconds.

| Source (used in FieldKey today) | Licence / terms for offline copies | Recommendation |
|---|---|---|
| **USGS Topo** (The National Map) | US Government work; USGS states no use restrictions on TNM map services, credit requested | ✅ **Approved.** US only, tiles to z16 |
| **USGS Imagery Only** (NAIP, 1 m) | Same as above | ✅ **Approved.** US only, tiles to z16 |
| **USDA NAIP via USGS** (USGSNAIPImagery image service, ~0.6 m) | US Government work (USDA/USGS), public domain, credit requested | ✅ **Approved 2026-11-18 for FieldKey's offline close-ups** (zoom 17–18 around sites), and 2026-11-19 for live viewing in the QGIS project (`docs/qgis-setup.md`). Not in mission packages yet |
| USGS Imagery Topo (imagery + labels) | Same as above (not in FieldKey yet) | ✅ Optional |
| ⚠️ **Esri World Imagery**, Esri reference / transportation overlays | Esri's terms don't allow exporting the standard layer for offline use; only small exports via the "for Export" layer inside ArcGIS apps with an ArcGIS account | ❌ Don't use |
| ⚠️ **Google** (Maps, Photorealistic 3D Tiles) | Google Maps Platform terms forbid pre-fetching, caching, storing or offline use | ❌ Don't use |
| OpenStreetMap standard tiles (tile.openstreetmap.org) | Map data is open (ODbL), but the tile server's policy forbids bulk/offline downloading | ❌ Don't use this server |
| OpenFreeMap (FieldKey's dark map) | Free, OSM data (ODbL, attribution); vector tiles, not images | Later: needs rendering to images first |
| CARTO dark tiles (older map) | Free tiers now need an API key; offline storage isn't clearly allowed | ❌ Not recommended |
| Regrid parcel lines | Regrid's licence; redistributing parcels in client files needs a Regrid licence | ❌ Not without a licence |
| AWS Terrain Tiles (elevation) | Open data with per-source attribution | Later: would need a hillshade step |
| Radar / rain (IEM HRRR, NOAA) | Forecast products, out of date within hours | Not useful offline |

Esri and Google are the two that look tempting and aren't allowed. **To approve:** tell me which
rows; the tile size gets measured, a migration adds it, and a test package is built with it.

## Running the worker

The worker is `worker/` — Python + GDAL in the official OSGeo image (`worker/Dockerfile`). It needs
four secrets, all as environment variables (see `worker/.env.example`; never commit `worker/.env`):

| Variable | What it is | Where it comes from |
|---|---|---|
| `DATABASE_URL` | the `export_worker` database login | password you set (step 1) |
| `SUPABASE_URL` | `https://fdclbfqgsookhxfboxpn.supabase.co` | — |
| `SUPABASE_SERVICE_ROLE_KEY` | a Supabase secret key, used only to upload/delete package files | Dashboard → Project Settings → API Keys → create secret key "export-worker" |
| `WORKER_TOKEN` | shared secret for the database's wake-up call | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

`export_worker` can only *read* the feature tables and update export jobs: no inserts, edits or
deletes of your data, no access to accounts (checked on the live database).

### Recommended host: Google Cloud Run

You already have a Google Cloud project for the Maps key. Cloud Run builds the image from the
folder (no Docker needed on your PC), scales to zero between exports, and light use like this
should stay inside its free monthly allowance — check the Cloud Run pricing page for current numbers.

1. **Database password** (same method as QGIS, so it never reaches the logs in plain text):
   `python scripts/make_db_password.py --role export_worker` → run the printed `alter role` line
   in the Supabase SQL Editor. Keep the password for step 3.
2. **Secrets in Google Secret Manager** (Console → Security → Secret Manager): create
   `fk-db-url` (the full `DATABASE_URL`), `fk-sb-secret`, `fk-worker-token`. Then let Cloud Run
   read them (it runs as the project's default compute account):
   ```
   PN=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
   for s in fk-db-url fk-sb-secret fk-worker-token; do
     gcloud secrets add-iam-policy-binding $s \
       --member serviceAccount:$PN-compute@developer.gserviceaccount.com \
       --role roles/secretmanager.secretAccessor
   done
   ```
   No gcloud on your PC? Use **Cloud Shell** (the `>_` button at the top of the Google Cloud
   console): it has gcloud and git, and `git clone https://github.com/masterweeks/FieldKey.git`
   gives it the repo folder for step 3.
3. **Deploy** from the repo folder:
   ```
   gcloud run deploy fieldkey-export --source worker --region us-west1 \
     --allow-unauthenticated --no-cpu-throttling --min-instances 0 --max-instances 1 \
     --memory 1Gi --timeout 3600 \
     --set-env-vars SUPABASE_URL=https://fdclbfqgsookhxfboxpn.supabase.co \
     --set-secrets DATABASE_URL=fk-db-url:latest,SUPABASE_SERVICE_ROLE_KEY=fk-sb-secret:latest,WORKER_TOKEN=fk-worker-token:latest
   ```
   "Allow unauthenticated" lets the database reach it; every call must still carry `WORKER_TOKEN`
   (`/run` answers 401 otherwise). `--no-cpu-throttling` keeps the export running after the wake-up
   call returns. The build runs the worker's unit tests and stops if they fail.
4. **Wake-up call** in Supabase: Database → Extensions → enable **pg_net**; then Project Settings →
   Vault (or Integrations → Vault) → add secret `export_worker_url` = the Cloud Run URL and secret
   `export_worker_token` = the same token. From then on each new job calls `POST <url>/run`.
5. **Test:** FieldKey → Export → Mission package → Build package. It should show progress within a
   few seconds and "Ready" with a Download button.

**Alternatives:** any always-on machine with Docker can run
`docker run --env-file worker/.env fieldkey-export loop --interval 30` (no step 4 needed). Or run
it by hand on a PC with QGIS: `cd worker` then
`"C:\Program Files\QGIS 3.44.15\bin\python-qgis-ltr.bat" -m fieldkey_export once` (with the
variables set), which works through the queue and exits.

### Building a package by hand

`python -m fieldkey_export build --owner <user uuid> --missions <id,id> --out mission.gpkg`
writes straight to a file without a job or upload (add `--include-contacts`, `--basemaps`, etc.).

## Tests

- `node --test tests/` — includes the phone-side estimate vs. the shared fixture.
- `cd worker` then `python -m unittest discover -s tests -t .` with GDAL's Python (QGIS's
  `python-qgis-ltr.bat`, or inside the image): tile maths, planning, size cap before and during
  download, contacts left out, styles adapted, tiles readable by GDAL, broken or missing tiles,
  cancel, and the `/run` token check.
- A built package passes GDAL's GeoPackage validator, and QGIS opens it with the styles applied.
