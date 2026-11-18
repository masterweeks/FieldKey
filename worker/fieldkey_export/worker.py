"""FieldKey export worker: turns queued export_jobs into GeoPackages.

  python -m fieldkey_export serve      HTTP: POST /run (Bearer WORKER_TOKEN) works the queue; GET /healthz
  python -m fieldkey_export loop       check the queue every --interval seconds (always-on host)
  python -m fieldkey_export once       work the queue until it's empty, then exit (cron, Cloud Run job)
  python -m fieldkey_export build ...  build a package straight to a local file (no job, no upload)

Settings come from environment variables only (never from the repo):
  DATABASE_URL               postgresql://export_worker.<project ref>:<password>@<pooler host>:5432/postgres?sslmode=require
  SUPABASE_URL               https://<project ref>.supabase.co          (upload / delete package files)
  SUPABASE_SERVICE_ROLE_KEY  secret key, used only for Storage
  WORKER_TOKEN               shared secret the database's wake-up call sends (serve mode)
  MAX_PACKAGE_MB             hard ceiling for any package (default 45: the Free plan's 50 MB file limit)
  EXPIRE_DAYS                how long a finished package stays downloadable (default 14)
  TILE_THREADS               parallel tile downloads (default 4, max 8)
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import hmac
import json
import os
import re
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import package as P
from . import tiles as T

USER_AGENT = "FieldKey-export/1.0 (+https://github.com/masterweeks/FieldKey)"
STALE_AFTER = "10 minutes"
MAX_ATTEMPTS = 3


def env_int(name, default, lo, hi):
    try:
        return max(lo, min(hi, int(os.environ.get(name, default))))
    except ValueError:
        return default


class JobFailed(Exception):
    """A failure the user should see as the reason (not a crash)."""


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- database

def connect(url=None):
    import psycopg2
    import psycopg2.extras
    psycopg2.extras.register_uuid()
    con = psycopg2.connect(url or os.environ["DATABASE_URL"], connect_timeout=15, application_name="fieldkey-export")
    con.autocommit = True
    return con


def q(con, sql, args=None):
    import psycopg2.extras
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else []


def claim_job(con):
    q(con, """update public.export_jobs set status = 'cancelled', message = 'Cancelled', finished_at = now()
              where status = 'queued' and cancel_requested""")
    rows = q(con, f"""
        update public.export_jobs j
        set status = 'running', started_at = now(), heartbeat_at = now(), attempts = attempts + 1,
            progress = 1, message = 'Starting'
        where j.id = (select id from public.export_jobs
                      where (status = 'queued' and not cancel_requested)
                         or (status = 'running' and heartbeat_at < now() - interval '{STALE_AFTER}' and attempts < {MAX_ATTEMPTS})
                      order by created_at
                      for update skip locked
                      limit 1)
        returning j.*""")
    return rows[0] if rows else None


def fail_abandoned(con):
    q(con, f"""update public.export_jobs set status = 'failed', finished_at = now(),
               error = 'The worker stopped during this export {MAX_ATTEMPTS} times. Try a smaller package.'
               where status = 'running' and heartbeat_at < now() - interval '{STALE_AFTER}' and attempts >= {MAX_ATTEMPTS}""")


class Progress:
    """Writes progress at most every 2 s, doubles as the heartbeat and the cancel check."""

    def __init__(self, con, job_id):
        self.con, self.job_id, self.last = con, job_id, 0.0

    def __call__(self, pct, message, force=False):
        now = time.monotonic()
        if not force and now - self.last < 2.0:
            return
        self.last = now
        r = q(self.con, """update public.export_jobs set progress = %s, message = %s, heartbeat_at = now()
                          where id = %s returning cancel_requested""", (int(max(1, min(99, pct))), message, self.job_id))
        if r and r[0]["cancel_requested"]:
            raise Cancelled()


# ---------------------------------------------------------------- loading the mission

GEOM = "case when geom is null then null else extensions.st_asbinary(geom) end as geom_wkb"


def _cols(layer):
    return ", ".join(c for c, _k in P.columns_for(layer, True))


def load_mission_data(con, owner, mission_ids, include_pins, buffer_m):
    """Everything in the package, for one owner. Deleted rows are never exported."""
    ids = [str(m) for m in mission_ids]
    data = {}
    data["missions"] = q(con, f"""select {_cols('missions')}, {GEOM} from public.missions
                                  where owner_id = %s and id = any(%s::uuid[]) and deleted_at is null order by name""", (owner, ids))
    if not data["missions"]:
        raise JobFailed("None of the chosen missions were found (were they deleted, or not synced yet?)")
    ids = [str(m["id"]) for m in data["missions"]]
    data["assets"] = q(con, f"""select {_cols('assets')}, {GEOM} from public.assets
                                where owner_id = %s and mission_id = any(%s::uuid[]) and deleted_at is null
                                order by sap_id nulls last, id""", (owner, ids))
    asset_ids = [str(a["id"]) for a in data["assets"]]
    circuit_ids = sorted({str(a["circuit_id"]) for a in data["assets"] if a["circuit_id"]})
    data["circuits"] = q(con, f"""select {_cols('circuits')}, {GEOM} from public.circuits
                                  where owner_id = %s and id = any(%s::uuid[]) and deleted_at is null""", (owner, circuit_ids))
    data["inspections"] = q(con, f"""select {_cols('inspections')}, {GEOM} from public.inspections
                                     where owner_id = %s and deleted_at is null
                                       and (mission_id = any(%s::uuid[]) or asset_id = any(%s::uuid[]))""", (owner, ids, asset_ids))

    boxes = feature_boxes(data, buffer_m)
    area = T.union_bbox(boxes)
    data["pins"] = []
    if include_pins:
        # pins tied to the mission or its sites, plus loose pins (parking, gates, notes) inside the area
        env = area or (0, 0, 0, 0)
        data["pins"] = q(con, f"""select {_cols('pins')}, {GEOM} from public.pins
                                  where owner_id = %s and deleted_at is null
                                    and (mission_id = any(%s::uuid[]) or asset_id = any(%s::uuid[])
                                         or (mission_id is null and asset_id is null
                                             and geom operator(extensions.&&) extensions.st_makeenvelope(%s, %s, %s, %s, 4326)))""",
                         (owner, ids, asset_ids, *env))
    pin_ids = [str(p["id"]) for p in data["pins"]]
    insp_ids = [str(i["id"]) for i in data["inspections"]]
    data["photos"] = q(con, f"""select {_cols('photos')}, {GEOM} from public.photos
                                where owner_id = %s and deleted_at is null
                                  and (mission_id = any(%s::uuid[]) or asset_id = any(%s::uuid[])
                                       or pin_id = any(%s::uuid[]) or inspection_id = any(%s::uuid[]))""",
                        (owner, ids, asset_ids, pin_ids, insp_ids))
    return data


def _wkb_bbox(wkb):
    from osgeo import ogr
    g = ogr.CreateGeometryFromWkb(bytes(wkb))
    w, e, s, n = g.GetEnvelope()
    return (w, s, e, n)


def feature_boxes(data, buffer_m):
    boxes = []
    for layer in ("missions", "circuits", "assets", "pins", "inspections"):
        for r in data.get(layer) or []:
            if r.get("geom_wkb"):
                boxes.append(T.buffer_bbox(_wkb_bbox(r["geom_wkb"]), buffer_m))
    return boxes


def load_sources(con, ids):
    if not ids:
        return []
    rows = q(con, "select * from public.export_tile_sources where enabled and id = any(%s) order by id", (list(ids),))
    missing = set(ids) - {r["id"] for r in rows}
    if missing:
        raise JobFailed("Basemap not approved for export: " + ", ".join(sorted(missing)))
    return rows


def load_styles(con):
    rows = q(con, """select f_table_name, stylename, styleqml::text as qml, stylesld::text as sld from public.layer_styles
                     where useasdefault and f_table_schema = 'public' and f_table_name = any(%s)""", (P.LAYER_NAMES,))
    return [(r["f_table_name"], r["stylename"], r["qml"], r["sld"]) for r in rows]


# ---------------------------------------------------------------- planning + size

def plan_package(data, sources, min_zoom, max_zoom, buffer_m):
    feats = sum(len(v) for v in data.values())
    boxes = feature_boxes(data, buffer_m)
    plans = []
    for s in sources:
        lo, hi = max(min_zoom, s["min_zoom"]), min(max_zoom, s["max_zoom"])
        if lo > hi:
            plans.append((s, {}, 0))
            continue
        plan, n, truncated = T.plan_tiles(boxes, lo, hi)
        if truncated:
            raise JobFailed(f"{s['name']} would need over {T.PLAN_TILE_LIMIT:,} tiles. Lower the top zoom or the area.")
        plans.append((s, plan, n))
    est = T.estimate_bytes(feats, [(n, s["avg_tile_bytes"]) for s, _p, n in plans])
    return feats, boxes, plans, est


# ---------------------------------------------------------------- tiles

def fetch_tile(url, timeout=20, tries=3):
    """Returns bytes, or None for a tile that doesn't exist (404/204/empty)."""
    delay = 1.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/jpeg,*/*;q=0.5"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status == 204:
                    return None
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
        time.sleep(delay)
        delay *= 2
    return None


def tile_url(template, z, x, y):
    return template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))


def write_tiles(path, source, plan, area, cap_bytes, progress, pct_lo, pct_hi, fetch=fetch_tile, threads=4):
    """Download one basemap into its own tile table. Returns (tiles written, missing)."""
    zooms = sorted(plan)
    if not zooms:
        return 0, 0
    table = "basemap_" + source["id"]
    tt = P.TileTable(path, table, source["name"], f"{source['name']} — {source['attribution']}", area, zooms[0], zooms[-1])
    jobs = [(z, x, y) for z in zooms for (x, y) in plan[z]]
    done = missing = bad = 0
    try:
        with cf.ThreadPoolExecutor(max_workers=threads) as pool:
            it = iter(jobs)
            running = {}

            def submit():
                for z, x, y in it:
                    running[pool.submit(fetch, tile_url(source["url_template"], z, x, y))] = (z, x, y)
                    if len(running) >= threads * 4:
                        return

            submit()
            while running:
                fin, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
                for f in fin:
                    z, x, y = running.pop(f)
                    try:
                        data = f.result()
                    except Exception:
                        data, bad = None, bad + 1
                    if data and P.looks_like_image(data):
                        tt.put(z, x, y, data)
                        done += 1
                    else:
                        missing += 1
                n = done + missing
                if n >= 50 and bad > n * 0.25:
                    raise JobFailed(f"{source['name']} isn't responding properly ({bad} of {n} tiles failed). Try again later.")
                if done % 100 == 0 and os.path.getsize(path) > cap_bytes:
                    raise JobFailed(f"The package grew past the {cap_bytes // 1048576} MB cap while downloading {source['name']}. "
                                    "Lower the top zoom or the buffer.")
                progress(pct_lo + (pct_hi - pct_lo) * n / len(jobs), f"{source['name']}: {n:,} of {len(jobs):,} tiles")
                submit()
    finally:
        tt.close()
    return done, missing


# ---------------------------------------------------------------- building

def slug(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-")
    return s[:40] or "mission"


def build_package(con, job, out_path, progress=lambda *a, **k: None, fetch=fetch_tile, max_cap_mb=None):
    """Builds the .gpkg at out_path. Returns a dict with counts and sizes."""
    max_cap_mb = max_cap_mb or env_int("MAX_PACKAGE_MB", 45, 1, 1000)
    cap_mb = min(int(job.get("cap_mb") or max_cap_mb), max_cap_mb)
    cap_bytes = cap_mb * 1048576
    include_contacts = bool(job.get("include_contacts"))
    buffer_m = int(job.get("buffer_m") if job.get("buffer_m") is not None else 300)

    progress(3, "Reading the mission", force=True)
    data = load_mission_data(con, str(job["owner_id"]), job["mission_ids"], job.get("include_pins", True), buffer_m)
    sources = load_sources(con, job.get("basemaps") or [])
    feats, boxes, plans, est = plan_package(data, sources, int(job.get("min_zoom", 10)), int(job.get("max_zoom", 16)), buffer_m)
    if est > cap_bytes:
        raise JobFailed(f"This package would be about {est / 1048576:.0f} MB, over the {cap_mb} MB cap. "
                        "Lower the top zoom, the buffer, or leave out a basemap.")
    if job.get("id"):
        q(con, "update public.export_jobs set estimate_bytes = %s where id = %s", (est, job["id"]))

    progress(8, f"Writing {feats:,} features", force=True)
    epsg = 3857 if any(n for _s, _p, n in plans) else 4326     # see package.write_vectors
    P.write_vectors(out_path, data, include_contacts, epsg)
    names = [m["name"] for m in data["missions"]]
    area = T.union_bbox(boxes)
    info = [("format", "FieldKey mission package 1"),
            ("created_at", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
            ("missions", names),
            ("contacts_included", "yes" if include_contacts else "no (names and phone numbers left out)"),
            ("vector_crs", f"EPSG:{epsg}"),
            ("area_wgs84", list(area) if area else None),
            ("counts", {k: len(v) for k, v in data.items()}),
            ("basemaps", [{"id": s["id"], "name": s["name"], "attribution": s["attribution"], "license": s["license"]}
                          for s, _p, _n in plans])]
    P.write_info(out_path, info)
    P.write_styles(out_path, load_styles(con), include_contacts)

    tile_total = 0
    threads = env_int("TILE_THREADS", 4, 1, 8)
    if plans and area:
        span = 80.0 / len(plans)
        for i, (s, plan, _n) in enumerate(plans):
            got, _missing = write_tiles(out_path, s, plan, area, cap_bytes, progress, 12 + i * span, 12 + (i + 1) * span,
                                        fetch=fetch, threads=threads)
            tile_total += got
    size = os.path.getsize(out_path)
    if size > cap_bytes:
        raise JobFailed(f"The package came out at {size / 1048576:.1f} MB, over the {cap_mb} MB cap.")
    base = slug(names[0]) + ("-and-%d-more" % (len(names) - 1) if len(names) > 1 else "")
    return {"feature_count": feats, "tile_count": tile_total, "size_bytes": size, "estimate_bytes": est,
            "file_name": f"{base}-{dt.date.today().isoformat()}.gpkg"}


# ---------------------------------------------------------------- storage

def _storage(method, path, body=None, ctype="application/json"):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Content-Type": ctype}
    if key.startswith("eyJ"):                      # legacy JWT service_role key
        headers["Authorization"] = "Bearer " + key
    if method == "POST" and ctype != "application/json":
        headers["x-upsert"] = "true"
    req = urllib.request.Request(base + "/storage/v1/" + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def upload(local_path, storage_path):
    with open(local_path, "rb") as f:
        body = f.read()
    _storage("POST", "object/exports/" + urllib.parse.quote(storage_path), body, "application/geopackage+sqlite3")


def delete_object(storage_path):
    _storage("DELETE", "object/exports", json.dumps({"prefixes": [storage_path]}).encode())


def sweep_expired(con):
    for r in q(con, """select id, storage_path from public.export_jobs
                       where status = 'done' and expires_at < now() and storage_path is not null limit 50"""):
        try:
            delete_object(r["storage_path"])
        except Exception as e:
            log(f"could not delete expired {r['storage_path']}: {e}")
            continue
        q(con, "update public.export_jobs set status = 'expired', storage_path = null, message = 'Expired' where id = %s", (r["id"],))


# ---------------------------------------------------------------- the queue

def log(msg):
    print(dt.datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def run_job(con, job):
    jid = str(job["id"])
    progress = Progress(con, jid)
    tmp = tempfile.mkdtemp(prefix="fk-export-")
    out = os.path.join(tmp, "package.gpkg")
    try:
        res = build_package(con, job, out, progress)
        progress(95, "Uploading", force=True)
        path = f"{job['owner_id']}/{jid}/{res['file_name']}"
        upload(out, path)
        days = env_int("EXPIRE_DAYS", 14, 1, 90)
        q(con, f"""update public.export_jobs set status = 'done', progress = 100, message = 'Ready',
                   size_bytes = %s, feature_count = %s, tile_count = %s, estimate_bytes = %s,
                   storage_path = %s, file_name = %s, finished_at = now(), expires_at = now() + interval '{days} days'
                   where id = %s""",
          (res["size_bytes"], res["feature_count"], res["tile_count"], res["estimate_bytes"], path, res["file_name"], jid))
        log(f"job {jid} done: {res['feature_count']} features, {res['tile_count']} tiles, {res['size_bytes']:,} bytes")
    except Cancelled:
        q(con, "update public.export_jobs set status = 'cancelled', message = 'Cancelled', finished_at = now() where id = %s", (jid,))
        log(f"job {jid} cancelled")
    except JobFailed as e:
        q(con, "update public.export_jobs set status = 'failed', error = %s, message = 'Failed', finished_at = now() where id = %s",
          (str(e)[:500], jid))
        log(f"job {jid} failed: {e}")
    except Exception as e:
        traceback.print_exc()
        q(con, "update public.export_jobs set status = 'failed', error = %s, message = 'Failed', finished_at = now() where id = %s",
          (("Export error: " + str(e))[:500], jid))
    finally:
        try:
            os.remove(out)
            os.rmdir(tmp)
        except OSError:
            pass


_run_lock = threading.Lock()


def work_queue():
    """Process queued jobs until none are left. Safe to call from several hosts at once."""
    if not _run_lock.acquire(blocking=False):
        return 0
    n = 0
    try:
        con = connect()
        try:
            fail_abandoned(con)
            while True:
                job = claim_job(con)
                if not job:
                    break
                n += 1
                run_job(con, job)
            sweep_expired(con)
        finally:
            con.close()
    finally:
        _run_lock.release()
    return n


# ---------------------------------------------------------------- entry points

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"ok": True}) if self.path == "/healthz" else self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "not found"})
        token = os.environ.get("WORKER_TOKEN", "")
        got = self.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(got.encode(), ("Bearer " + token).encode()):
            return self._send(401, {"error": "unauthorized"})
        threading.Thread(target=_safe_work, daemon=True).start()
        self._send(202, {"started": True})

    def log_message(self, fmt, *args):
        pass


def _safe_work():
    try:
        work_queue()
    except Exception:
        traceback.print_exc()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fieldkey_export", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    lp = sub.add_parser("loop")
    lp.add_argument("--interval", type=int, default=30)
    sub.add_parser("once")
    bp = sub.add_parser("build", help="build a package to a local file (no job, no upload)")
    bp.add_argument("--owner", required=True)
    bp.add_argument("--missions", required=True, help="comma-separated mission ids")
    bp.add_argument("--out", required=True)
    bp.add_argument("--include-contacts", action="store_true")
    bp.add_argument("--no-pins", action="store_true")
    bp.add_argument("--basemaps", default="")
    bp.add_argument("--min-zoom", type=int, default=10)
    bp.add_argument("--max-zoom", type=int, default=16)
    bp.add_argument("--buffer", type=int, default=300)
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        port = int(os.environ.get("PORT", "8080"))
        threading.Thread(target=_safe_work, daemon=True).start()    # catch up on anything queued while asleep
        log(f"listening on :{port}")
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
    elif a.cmd == "loop":
        log(f"checking the queue every {a.interval}s")
        while True:
            _safe_work()
            time.sleep(max(5, a.interval))
    elif a.cmd == "once":
        log(f"processed {work_queue()} job(s)")
    else:
        if os.path.exists(a.out):
            sys.exit(f"{a.out} already exists")
        con = connect()
        job = {"owner_id": a.owner, "mission_ids": [m.strip() for m in a.missions.split(",") if m.strip()],
               "include_contacts": a.include_contacts, "include_pins": not a.no_pins,
               "basemaps": [b for b in a.basemaps.split(",") if b], "min_zoom": a.min_zoom, "max_zoom": a.max_zoom,
               "buffer_m": a.buffer}
        res = build_package(con, job, a.out, lambda p, m, force=False: print(f"{int(p):3d}% {m}", flush=True))
        print(json.dumps(res, indent=2))
