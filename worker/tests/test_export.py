"""Offline tests for the export worker (no database, no network).

  python -m unittest discover -s worker/tests -t worker        (from the repo root, with GDAL's Python)
"""
import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock

from osgeo import gdal, ogr

from fieldkey_export import package as P
from fieldkey_export import tiles as T
from fieldkey_export import worker as W

gdal.UseExceptions()
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "export_estimate.json")
OWNER = "11111111-2222-3333-4444-555555555555"


def point_wkb(lon, lat):
    g = ogr.Geometry(ogr.wkbPoint)
    g.AddPoint_2D(lon, lat)
    return bytes(g.ExportToWkb())


def png_tile(shade=128):
    mem = gdal.GetDriverByName("MEM").Create("", 256, 256, 3, gdal.GDT_Byte)
    for b in (1, 2, 3):
        mem.GetRasterBand(b).Fill(shade)
    gdal.GetDriverByName("PNG").CreateCopy("/vsimem/t.png", mem)
    f = gdal.VSIFOpenL("/vsimem/t.png", "rb")
    gdal.VSIFSeekL(f, 0, 2)
    n = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)
    data = gdal.VSIFReadL(1, n, f)
    gdal.VSIFCloseL(f)
    gdal.Unlink("/vsimem/t.png")
    return bytes(data)


PNG = png_tile()


def sample_data(n_sites=6, spread=0.02):
    mid = str(uuid.uuid4())
    sites = []
    for i in range(n_sites):
        lon, lat = -121.49 + i * spread, 38.58 + (i % 2) * spread
        sites.append({"id": str(uuid.uuid4()), "mission_id": mid, "circuit_id": None, "sap_id": f"10000000{i}",
                      "name": f"Customer {i}", "address": f"{i} Main St", "phones": [{"display": "(530) 555-0100", "tel": "+15305550100"}],
                      "access": "gate", "access_notes": None, "status": "new", "text_count": i, "last_texted_at": None,
                      "scheduled_at": "2026-11-20T16:30:00+00:00", "notes": "note", "access_issue": i == 2,
                      "access_issue_reason": None, "extra": {"k": i}, "updated_at": "2026-11-18T10:00:00Z",
                      "geom_wkb": point_wkb(lon, lat)})
    sites.append(dict(sites[0], id=str(uuid.uuid4()), sap_id="no-location", geom_wkb=None))
    return {
        "missions": [{"id": mid, "name": "Batch A / North", "source_file": "a.csv", "status": "active", "notes": None,
                      "created_at": "2026-11-18T10:00:00Z", "updated_at": "2026-11-18T10:00:00Z", "geom_wkb": None}],
        "assets": sites, "circuits": [], "inspections": [], "photos": [],
        "pins": [{"id": str(uuid.uuid4()), "mission_id": None, "asset_id": None, "kind": "parking", "label": "Lot",
                  "notes": None, "updated_at": "2026-11-18T10:00:00Z", "geom_wkb": point_wkb(-121.488, 38.581)}],
    }


SOURCE = {"id": "test_topo", "name": "Test Topo", "url_template": "https://tiles.invalid/{z}/{x}/{y}.png", "tile_format": "png",
          "min_zoom": 0, "max_zoom": 16, "avg_tile_bytes": 20000, "attribution": "Test", "license": "Public domain"}
STYLE_QML = ('<qgis><attributeactions><actionsetting name="Soft delete" action="update ..."/></attributeactions>'
             '<labeling><settings><text-style fieldName="coalesce(&quot;sap_id&quot;, &quot;name&quot;)"/></settings></labeling></qgis>')


class Fixture:
    def __init__(self, data, sources=(), styles=()):
        self.patches = [mock.patch.object(W, "load_mission_data", lambda *a, **k: data),
                        mock.patch.object(W, "load_sources", lambda con, ids: [s for s in sources if s["id"] in ids]),
                        mock.patch.object(W, "load_styles", lambda con: list(styles)),
                        mock.patch.object(W, "q", lambda *a, **k: [])]

    def __enter__(self):
        for p in self.patches:
            p.start()

    def __exit__(self, *a):
        for p in self.patches:
            p.stop()


def job(**kw):
    j = {"owner_id": OWNER, "mission_ids": ["x"], "include_contacts": False, "include_pins": True, "basemaps": [],
         "min_zoom": 10, "max_zoom": 16, "buffer_m": 300, "cap_mb": 45}
    j.update(kw)
    return j


class TileMaths(unittest.TestCase):
    def test_known_tiles(self):
        self.assertEqual(T.lonlat_to_tile(0, 0, 0), (0, 0))
        self.assertEqual(T.lonlat_to_tile(0.0001, -0.0001, 1), (1, 1))
        self.assertEqual(T.lonlat_to_tile(-180, 89, 3), (0, 0))
        self.assertEqual(T.lonlat_to_tile(180, -89, 3), (7, 7))
        # Sacramento at z16 (checked against the standard slippy-map formula)
        self.assertEqual(T.lonlat_to_tile(-121.4944, 38.5816, 16), (10650, 25144))

    def test_buffer_is_about_right(self):
        w, s, e, n = T.buffer_bbox((-121.5, 38.5, -121.5, 38.5), 1000)
        self.assertAlmostEqual((n - s) * 111320, 2000, delta=5)
        self.assertAlmostEqual((e - w) * 111320 * 0.7826, 2000, delta=10)

    def test_plan_takes_whole_area_at_low_zoom_and_only_near_sites_at_high_zoom(self):
        far = [T.buffer_bbox((-121.5, 38.5, -121.5, 38.5), 300), T.buffer_bbox((-120.0, 39.5, -120.0, 39.5), 300)]
        plan, total, trunc = T.plan_tiles(far, 8, 16)
        self.assertFalse(trunc)
        x0, y0, x1, y1 = T.tile_range(T.union_bbox(far), 8)
        self.assertEqual(len(plan[8]), (x1 - x0 + 1) * (y1 - y0 + 1))      # small: all of it
        x0, y0, x1, y1 = T.tile_range(T.union_bbox(far), 16)
        self.assertLess(len(plan[16]), 20)                                   # only around the two sites
        self.assertGreater((x1 - x0 + 1) * (y1 - y0 + 1), 50000)             # vs. the whole box
        self.assertEqual(total, sum(len(v) for v in plan.values()))

    def test_plan_stops_at_limit(self):
        big = [T.buffer_bbox((-121.5 + i * 0.05, 38.5, -121.5 + i * 0.05, 38.5), 2000) for i in range(40)]
        _plan, total, trunc = T.plan_tiles(big, 10, 18, limit=5000)
        self.assertTrue(trunc)
        self.assertGreater(total, 5000)

    def test_shared_fixture_matches(self):
        """FieldKey's JavaScript estimate is tested against the same file (tests/export-estimate.test.js in the repo root)."""
        with open(FIXTURE, encoding="utf-8") as f:
            fx = json.load(f)
        for case in fx["cases"]:
            boxes = [T.buffer_bbox((lon, lat, lon, lat), case["buffer_m"]) for lon, lat in case["points"]]
            plan, total, _ = T.plan_tiles(boxes, case["min_zoom"], case["max_zoom"])
            self.assertEqual({str(z): len(v) for z, v in plan.items()}, case["per_zoom"], case["name"])
            self.assertEqual(total, case["total"], case["name"])
            self.assertEqual(T.estimate_bytes(case["features"], [(total, case["avg_tile_bytes"])]), case["estimate_bytes"], case["name"])


class Package(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.out = os.path.join(self.dir, "p.gpkg")

    def tearDown(self):
        import gc
        import shutil
        gc.collect()
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, data, j, sources=(), styles=(), fetch=lambda url: PNG, cap=45):
        with Fixture(data, sources, styles):
            return W.build_package(None, j, self.out, fetch=fetch, max_cap_mb=cap)

    def test_vectors_without_contacts_by_default(self):
        res = self.build(sample_data(), job())
        self.assertEqual(res["feature_count"], 9)
        self.assertTrue(res["file_name"].startswith("Batch-A-North-"))
        ds = ogr.Open(self.out)
        names = [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
        for n in ("missions", "assets", "pins", "circuits", "inspections", "photos", "package_info"):
            self.assertIn(n, names)
        lyr = ds.GetLayerByName("assets")
        fields = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
        self.assertNotIn("name", fields)
        self.assertNotIn("phones", fields)
        self.assertIn("sap_id", fields)
        self.assertEqual(lyr.GetFeatureCount(), 7)
        lyr.SetAttributeFilter("sap_id = '100000002'")
        f = lyr.GetNextFeature()
        self.assertEqual(f.GetField("access_issue"), 1)
        self.assertEqual(json.loads(f.GetField("extra")), {"k": 2})
        self.assertTrue(f.GetFieldAsString("scheduled_at").startswith("2026/11/20 16:30"))
        self.assertAlmostEqual(f.GetGeometryRef().GetX(), -121.45, places=6)
        self.assertEqual(lyr.GetSpatialRef().GetAuthorityCode(None), "4326")
        info = {f.GetField("key"): f.GetField("value") for f in ds.GetLayerByName("package_info")}
        self.assertIn("no (names", info["contacts_included"])
        self.assertEqual(json.loads(info["missions"]), ["Batch A / North"])

    def test_contacts_when_asked(self):
        self.build(sample_data(), job(include_contacts=True))
        ds = ogr.Open(self.out)
        f = ds.GetLayerByName("assets").GetNextFeature()
        self.assertEqual(f.GetField("name"), "Customer 0")
        self.assertEqual(json.loads(f.GetField("phones"))[0]["tel"], "+15305550100")

    def test_styles_embedded_and_adapted(self):
        self.build(sample_data(), job(), styles=[("assets", "FieldKey", STYLE_QML, "")])
        con = sqlite3.connect(self.out)
        qml, = con.execute("select styleQML from layer_styles where f_table_name='assets' and useAsDefault").fetchone()
        con.close()
        self.assertNotIn("Soft delete", qml)
        self.assertNotIn("name&quot;", qml)
        self.assertIn("&quot;sap_id&quot;", qml)

    def test_basemap_tiles_readable_by_gdal(self):
        urls = []

        def fetch(url):
            urls.append(url)
            return PNG

        res = self.build(sample_data(), job(basemaps=["test_topo"], min_zoom=12, max_zoom=15), sources=[SOURCE], fetch=fetch)
        self.assertEqual(res["tile_count"], len(urls))
        self.assertGreater(res["tile_count"], 4)
        self.assertTrue(all(u.startswith("https://tiles.invalid/1") for u in urls))
        ds = gdal.Open("GPKG:" + self.out + ":basemap_test_topo")
        self.assertEqual(ds.RasterCount, 4)                               # RGBA
        self.assertEqual(ds.GetSpatialRef().GetAuthorityCode(None), "3857")
        self.assertEqual(ds.GetRasterBand(1).GetOverviewCount(), 3)       # z12..z14 below the z15 base
        gt = ds.GetGeoTransform()
        self.assertAlmostEqual(gt[1], 2 * T.WORLD / (256 * 2 ** 15), places=6)
        self.assertEqual(ds.GetRasterBand(1).ReadAsArray(0, 0, 1, 1) is not None, True)
        ds = None
        # vectors intact alongside, in the tiles' CRS (QGIS gives tile layers the vectors' CRS)
        v = ogr.Open(self.out)
        a = v.GetLayerByName("assets")
        self.assertEqual(a.GetFeatureCount(), 7)
        self.assertEqual(a.GetSpatialRef().GetAuthorityCode(None), "3857")
        a.SetAttributeFilter("sap_id = '100000000'")
        feat = a.GetNextFeature()
        g = feat.GetGeometryRef()
        self.assertAlmostEqual(g.GetX(), -121.49 * T.WORLD / 180, places=2)
        info = {f.GetField("key"): f.GetField("value") for f in v.GetLayerByName("package_info")}
        self.assertEqual(info["vector_crs"], "EPSG:3857")
        v = None

    def test_over_cap_refused_before_downloading(self):
        calls = []
        with self.assertRaises(W.JobFailed) as e:
            self.build(sample_data(30, 0.05), job(basemaps=["test_topo"], min_zoom=10, max_zoom=18, buffer_m=3000),
                       sources=[dict(SOURCE, max_zoom=18, avg_tile_bytes=60000)], fetch=lambda u: calls.append(u) or PNG, cap=5)
        self.assertIn("over the 5 MB cap", str(e.exception))
        self.assertEqual(calls, [])
        self.assertFalse(os.path.exists(self.out))

    def test_job_cap_cannot_exceed_worker_ceiling(self):
        with self.assertRaises(W.JobFailed) as e:
            self.build(sample_data(30, 0.05), job(basemaps=["test_topo"], max_zoom=17, buffer_m=2000, cap_mb=1000),
                       sources=[dict(SOURCE, max_zoom=17, avg_tile_bytes=60000)], cap=2)
        self.assertIn("2 MB cap", str(e.exception))

    def test_broken_source_fails_cleanly(self):
        def fetch(url):
            raise OSError("connection reset")

        with self.assertRaises(W.JobFailed) as e:
            self.build(sample_data(20, 0.03), job(basemaps=["test_topo"], min_zoom=12, max_zoom=16), sources=[SOURCE], fetch=fetch)
        self.assertIn("isn't responding", str(e.exception))

    def test_missing_tiles_are_skipped(self):
        res = self.build(sample_data(), job(basemaps=["test_topo"], min_zoom=13, max_zoom=14), sources=[SOURCE],
                         fetch=lambda url: None if url.endswith("0.png") else PNG)
        self.assertGreater(res["tile_count"], 0)

    def test_cancel_stops_the_job(self):
        def progress(pct, msg, force=False):
            if "tiles" in msg:
                raise W.Cancelled()

        with Fixture(sample_data(), [SOURCE]):
            with self.assertRaises(W.Cancelled):
                W.build_package(None, job(basemaps=["test_topo"], min_zoom=12, max_zoom=16), self.out, progress=progress,
                                fetch=lambda u: PNG)


class Http(unittest.TestCase):
    def test_run_needs_the_token(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with mock.patch.dict(os.environ, {"WORKER_TOKEN": "s3cret"}), mock.patch.object(W, "_safe_work", lambda: None):
                with urllib.request.urlopen(url + "/healthz") as r:
                    self.assertEqual(r.status, 200)
                for hdr in ({}, {"Authorization": "Bearer wrong"}):
                    with self.assertRaises(urllib.error.HTTPError) as e:
                        urllib.request.urlopen(urllib.request.Request(url + "/run", data=b"{}", headers=hdr))
                    self.assertEqual(e.exception.code, 401)
                r = urllib.request.urlopen(urllib.request.Request(url + "/run", data=b"{}", headers={"Authorization": "Bearer s3cret"}))
                self.assertEqual(r.status, 202)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
