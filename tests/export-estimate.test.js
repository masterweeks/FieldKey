// The phone's package-size estimate must match the worker's (worker/fieldkey_export/tiles.py).
// Both read the same fixture.   node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const X = require("../export-plan.js");

const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "worker", "tests", "fixtures", "export_estimate.json"), "utf8"));

test("tile maths matches the worker", () => {
  assert.deepEqual(X.lonlatToTile(0, 0, 0), [0, 0]);
  assert.deepEqual(X.lonlatToTile(-180, 89, 3), [0, 0]);
  assert.deepEqual(X.lonlatToTile(180, -89, 3), [7, 7]);
  assert.deepEqual(X.lonlatToTile(-121.4944, 38.5816, 16), [10650, 25144]);
});

for (const c of fx.cases) {
  test("same plan and estimate as the worker: " + c.name, () => {
    const boxes = c.points.map(([lo, la]) => X.bufferBbox([lo, la, lo, la], c.buffer_m));
    const p = X.planTiles(boxes, c.min_zoom, c.max_zoom);
    assert.deepEqual(Object.fromEntries(Object.entries(p.perZoom).map(([z, n]) => [String(z), n])), c.per_zoom);
    assert.equal(p.total, c.total);
    assert.equal(X.estimateBytes(c.features, [[p.total, c.avg_tile_bytes]]), c.estimate_bytes);
    const e = X.estimatePackage(c.points, c.features, [{ id: "s", min_zoom: 0, max_zoom: 22, avg_tile_bytes: c.avg_tile_bytes }],
      { bufferM: c.buffer_m, minZoom: c.min_zoom, maxZoom: c.max_zoom });
    assert.equal(e.bytes, c.estimate_bytes);
  });
}

test("no basemaps: data and styles only", () => {
  const e = X.estimatePackage([[-121.5, 38.5]], 150, [], { bufferM: 300, minZoom: 10, maxZoom: 16 });
  assert.equal(e.tiles, 0);
  assert.equal(e.bytes, X.BASE_BYTES + 150 * X.BYTES_PER_FEATURE);
});

test("source zoom limits are respected", () => {
  const e = X.estimatePackage([[-121.5, 38.5]], 1, [{ id: "t", min_zoom: 14, max_zoom: 15, avg_tile_bytes: 1000 }],
    { bufferM: 300, minZoom: 10, maxZoom: 18 });
  const only = X.planTiles([X.bufferBbox([-121.5, 38.5, -121.5, 38.5], 300)], 14, 15);
  assert.equal(e.tiles, only.total);
});
