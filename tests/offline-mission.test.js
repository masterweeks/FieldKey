// "Save mission offline" plans its tiles with the same rule as mission packages.   node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const X = require("../export-plan.js");

const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "worker", "tests", "fixtures", "export_estimate.json"), "utf8"));
const USGS = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}";
const DEM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";

for (const c of fx.cases) {
  test("tile list matches the package plan: " + c.name, () => {
    const boxes = c.points.map(([lo, la]) => X.bufferBbox([lo, la, lo, la], c.buffer_m));
    const counts = X.planTiles(boxes, c.min_zoom, c.max_zoom);
    const list = X.planTileList(boxes, c.min_zoom, c.max_zoom);
    assert.equal(list.total, counts.total);
    for (const z of Object.keys(counts.perZoom)) {
      assert.equal(list.byZoom[z].length, counts.perZoom[z], "zoom " + z);
      assert.equal(new Set(list.byZoom[z].map(([x, y]) => x + "/" + y)).size, list.byZoom[z].length, "no duplicates at zoom " + z);
    }
  });
}

test("every site's own tile is included at every zoom", () => {
  const pts = [[-122.3917, 40.5865], [-122.2, 40.45], [-122.6, 40.7]];
  const boxes = pts.map(([lo, la]) => X.bufferBbox([lo, la, lo, la], 300));
  const list = X.planTileList(boxes, 10, 16);
  for (let z = 10; z <= 16; z++) {
    const have = new Set(list.byZoom[z].map(([x, y]) => x + "/" + y));
    for (const [lo, la] of pts) { const [x, y] = X.lonlatToTile(lo, la, z); assert.ok(have.has(x + "/" + y), z + "/" + x + "/" + y); }
  }
});

test("layer URLs: zoom ranges, {y}/{x} order, no duplicates", () => {
  const byZoom = { 12: [[660, 1550]], 13: [[1320, 3100], [1321, 3100]], 14: [[2641, 6200]] };
  const urls = X.layerUrls([{ tpl: USGS, z0: 13, z1: 16 }, { tpl: DEM, z0: 12, z1: 13 }, { tpl: DEM, z0: 12, z1: 13 }], byZoom);
  assert.deepEqual(urls.sort(), [
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/13/3100/1320",
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/13/3100/1321",
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/14/6200/2641",
    "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/12/660/1550.png",
    "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1320/3100.png",
    "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1321/3100.png",
  ].sort());
});

test("a limit stops planning early", () => {
  const pts = [];
  for (let i = 0; i < 40; i++) pts.push([-122 + i * 0.05, 40 + (i % 5) * 0.05]);
  const boxes = pts.map(([lo, la]) => X.bufferBbox([lo, la, lo, la], 2000));
  const p = X.planTileList(boxes, 10, 16, 500);
  assert.equal(p.truncated, true);
  assert.ok(p.total > 500);
});

test("a larger whole-area threshold fills the map between sites", () => {
  const pts = [[-121.70, 40.51], [-121.96, 40.82], [-121.92, 40.63]];
  const boxes = pts.map(([lo, la]) => X.bufferBbox([lo, la, lo, la], 300));
  const area = X.unionBbox(boxes);
  const pkg = X.planTileList(boxes, 10, 16), phone = X.planTileList(boxes, 10, 16, 0, 400);
  for (let z = 10; z <= 16; z++) {
    const [x0, y0, x1, y1] = X.tileRange(area, z), all = (x1 - x0 + 1) * (y1 - y0 + 1);
    if (all <= 400) assert.equal(phone.byZoom[z].length, all, "zoom " + z + " saved whole");
    else assert.equal(phone.byZoom[z].length, pkg.byZoom[z].length, "zoom " + z + " near sites only");
  }
  assert.ok(phone.total > pkg.total);
});
