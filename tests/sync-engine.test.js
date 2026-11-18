// Tests for sync-engine.js:  node --test tests/
// The fake server below follows the same rules as public.fk_sync_push / fk_sync_pull
// (those are tested against the real database too; see docs/runbook.md).
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { createSyncEngine, backoffDelay, uuid5 } = require("../sync-engine.js");

// ------------------------------------------------------------------ fake server
function makeServer() {
  const tables = {}; const conflicts = []; let tick = 0;
  const T = name => (tables[name] = tables[name] || new Map());
  const stamp = () => new Date(Date.UTC(2026, 10, 19, 0, 0, 0) + (++tick) * 1000).toISOString().replace("Z", "123+00:00");
  const SKIP = new Set(["id", "_base_updated_at", "client_updated_at"]);
  return {
    conflicts, tables,
    failNextPush: null,     // "before": fail before applying; "after": apply, then lose the response
    failNextPull: false,
    async push(table, rows) {
      const mode = this.failNextPush; this.failNextPush = null;
      if (mode === "before") throw new Error("network down");
      const out = rows.map(r0 => {
        const r = Object.assign({}, r0); const t = T(table); const ex = t.get(r.id);
        if (!r.client_updated_at) r.client_updated_at = new Date().toISOString();
        if (!ex && r.deleted_at) return { id: r.id, status: "unchanged", row: null };
        if (!ex) {
          const row = Object.assign({}, r); delete row._base_updated_at; row.updated_at = stamp();
          t.set(r.id, row); return { id: r.id, status: "inserted", row: Object.assign({}, row) };
        }
        const keys = Object.keys(r).filter(k => !SKIP.has(k));
        const differs = keys.some(k => JSON.stringify(ex[k] === undefined ? null : ex[k]) !== JSON.stringify(r[k]));
        const concurrent = ex.updated_at > (r._base_updated_at || "");
        if (!differs) return { id: r.id, status: "unchanged", row: Object.assign({}, ex) };
        if (concurrent && r.client_updated_at < ex.client_updated_at) {
          conflicts.push({ table, id: r.id, kept: "server", kept_version: Object.assign({}, ex), overwritten_version: r });
          return { id: r.id, status: "stale", row: Object.assign({}, ex) };
        }
        if (concurrent) conflicts.push({ table, id: r.id, kept: "incoming", kept_version: r, overwritten_version: Object.assign({}, ex) });
        const row = Object.assign({}, ex); keys.concat("client_updated_at").forEach(k => { row[k] = r[k]; });
        row.updated_at = stamp(); t.set(r.id, row);
        return { id: r.id, status: "updated", row: Object.assign({}, row) };
      });
      if (mode === "after") throw new Error("connection lost after upload");
      return out;
    },
    async pull(table, sinceTs, sinceId, limit) {
      if (this.failNextPull) { this.failNextPull = false; throw new Error("network down"); }
      const rows = [...T(table).values()].sort((a, b) => a.updated_at < b.updated_at ? -1 : a.updated_at > b.updated_at ? 1 : a.id < b.id ? -1 : 1);
      return rows.filter(r => !sinceTs || r.updated_at > sinceTs || (r.updated_at === sinceTs && r.id > sinceId))
                 .slice(0, limit).map(r => Object.assign({}, r));
    },
  };
}

// ------------------------------------------------------------------ fake phone
function makeDevice(server, name, extra) {
  const outbox = new Map(), meta = new Map(), local = new Map(), base = new Map();
  let online = true; const timers = [];
  const store = {
    async outboxAll() { return [...outbox.values()].map(e => JSON.parse(JSON.stringify(e))); },
    async outboxPut(e) { outbox.set(e.key, JSON.parse(JSON.stringify(e))); },
    async outboxDelete(k) { outbox.delete(k); },
    async metaGet(k) { return meta.has(k) ? JSON.parse(JSON.stringify(meta.get(k))) : null; },
    async metaSet(k, v) { meta.set(k, v); },
  };
  let clock = 0;
  const engine = createSyncEngine(Object.assign({
    store, transport: server, isOnline: () => online,
    setTimer: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimer: () => {},
    now: () => new Date(Date.UTC(2026, 10, 19, 12) + (++clock)),
    async applyRemote(table, row) {
      base.set(row.id, row.updated_at);
      if (row.deleted_at) local.delete(row.id); else local.set(row.id, Object.assign({}, row));
    },
  }, extra));
  return {
    name, engine, outbox, local, timers,
    setOnline(v) { online = v; },
    async edit(table, id, changes, editedAt) {
      const row = Object.assign({}, local.get(id) || { id }, changes, { client_updated_at: editedAt, _base_updated_at: base.get(id) || null });
      delete row.updated_at;
      if (row.deleted_at) local.delete(id); else local.set(id, Object.assign({}, row));
      await engine.enqueue(table, row);
    },
  };
}

const ID = "6f1c9a52-0d3b-4c41-9a8e-111111111111";

// ------------------------------------------------------------------ tests
test("offline edits wait in the outbox, then upload once online", async () => {
  const s = makeServer(); const d = makeDevice(s, "A");
  d.setOnline(false);
  await d.edit("assets", ID, { name: "Jane", status: "new" }, "2026-11-19T10:00:00.000Z");
  await d.edit("assets", ID, { status: "texted" }, "2026-11-19T10:05:00.000Z");   // same row: replaces the queued one
  await d.edit("pins", "pin-1", { kind: "parking", geom: { type: "Point", coordinates: [-121.49, 38.58] } }, "2026-11-19T10:06:00.000Z");
  let st = await d.engine.syncNow();
  assert.equal(st.state, "offline");
  assert.equal(st.pending, 2, "two rows queued (the asset's two edits coalesced)");
  assert.equal(s.tables.assets, undefined, "nothing reached the server while offline");

  d.setOnline(true);
  st = await d.engine.syncNow();
  assert.equal(st.state, "idle");
  assert.equal(st.pending, 0);
  assert.equal(s.tables.assets.get(ID).status, "texted");
  assert.equal(s.tables.pins.get("pin-1").kind, "parking");
  assert.equal(s.conflicts.length, 0);
});

test("two devices edit the same feature: later edit wins, the other is logged, both converge", async () => {
  const s = makeServer(); const a = makeDevice(s, "A"); const b = makeDevice(s, "B");
  await a.edit("assets", ID, { name: "Jane", status: "new" }, "2026-11-19T09:00:00.000Z");
  await a.engine.syncNow(); await b.engine.syncNow();
  assert.equal(b.local.get(ID).name, "Jane", "B pulled A's site");

  a.setOnline(false); b.setOnline(false);
  await a.edit("assets", ID, { status: "texted" }, "2026-11-19T10:00:00.000Z");    // earlier
  await b.edit("assets", ID, { status: "replied" }, "2026-11-19T11:00:00.000Z");   // later
  b.setOnline(true); await b.engine.syncNow();     // B uploads first
  a.setOnline(true); await a.engine.syncNow();     // A's older edit arrives second: stale
  await b.engine.syncNow();

  assert.equal(s.tables.assets.get(ID).status, "replied");
  assert.equal(a.local.get(ID).status, "replied", "A took the winning version");
  assert.equal(b.local.get(ID).status, "replied");
  assert.equal(s.conflicts.length, 1);
  assert.equal(s.conflicts[0].kept, "server");
  assert.equal(s.conflicts[0].overwritten_version.status, "texted", "A's edit is kept in the conflict log");
});

test("the later edit wins even when it uploads second", async () => {
  const s = makeServer(); const a = makeDevice(s, "A"); const b = makeDevice(s, "B");
  await a.edit("assets", ID, { name: "Jane" }, "2026-11-19T09:00:00.000Z");
  await a.engine.syncNow(); await b.engine.syncNow();
  a.setOnline(false); b.setOnline(false);
  await a.edit("assets", ID, { name: "Jane Doe" }, "2026-11-19T10:00:00.000Z");
  await b.edit("assets", ID, { name: "J. Doe" }, "2026-11-19T12:00:00.000Z");      // later, uploads second
  a.setOnline(true); await a.engine.syncNow();
  b.setOnline(true); await b.engine.syncNow();
  await a.engine.syncNow();
  assert.equal(s.tables.assets.get(ID).name, "J. Doe");
  assert.equal(a.local.get(ID).name, "J. Doe");
  assert.equal(s.conflicts.length, 1);
  assert.equal(s.conflicts[0].kept, "incoming");
  assert.equal(s.conflicts[0].overwritten_version.name, "Jane Doe", "the overwritten version is logged");
});

test("delete vs edit: an older edit can't undo a delete; a newer edit restores it (both logged)", async () => {
  const s = makeServer(); const a = makeDevice(s, "A"); const b = makeDevice(s, "B");
  await a.edit("assets", ID, { name: "Jane", deleted_at: null }, "2026-11-19T09:00:00.000Z");
  await a.engine.syncNow(); await b.engine.syncNow();

  a.setOnline(false); b.setOnline(false);
  await a.edit("assets", ID, { deleted_at: "2026-11-19T11:00:00.000Z" }, "2026-11-19T11:00:00.000Z");
  await b.edit("assets", ID, { notes: "gate code 1234", deleted_at: null }, "2026-11-19T10:00:00.000Z");
  a.setOnline(true); await a.engine.syncNow();
  b.setOnline(true); await b.engine.syncNow();
  assert.ok(s.tables.assets.get(ID).deleted_at, "delete stands");
  assert.equal(b.local.has(ID), false, "B removed the deleted site locally");
  assert.equal(s.conflicts.length, 1);
  assert.equal(s.conflicts[0].overwritten_version.notes, "gate code 1234", "B's lost note is in the log");

  // now an edit made after the delete brings the site back
  await b.edit("assets", ID, { name: "Jane", notes: "re-added", deleted_at: null }, "2026-11-19T12:00:00.000Z");
  await b.engine.syncNow(); await a.engine.syncNow();
  assert.equal(s.tables.assets.get(ID).deleted_at, null);
  assert.equal(a.local.get(ID).notes, "re-added", "A sees it again");
});

test("interrupted upload: applied on the server but the reply was lost; the retry is harmless", async () => {
  const s = makeServer(); const d = makeDevice(s, "A");
  await d.edit("assets", ID, { name: "Jane" }, "2026-11-19T10:00:00.000Z");
  s.failNextPush = "after";
  let st = await d.engine.syncNow();
  assert.equal(st.state, "error");
  assert.equal(st.pending, 1, "still queued: the phone never heard back");
  assert.equal(s.tables.assets.size, 1, "but the server did store it");
  assert.equal(d.timers.length, 1, "a retry is scheduled");

  st = await d.engine.syncNow();
  assert.equal(st.state, "idle");
  assert.equal(st.pending, 0);
  assert.equal(s.tables.assets.size, 1, "no duplicate");
  assert.equal(s.conflicts.length, 0, "and no false conflict");
});

test("failure before upload keeps the edit and retries with growing, capped delays", async () => {
  const s = makeServer(); const d = makeDevice(s, "A", { rand: () => 1, retryBaseMs: 2000, retryMaxMs: 30000 });
  await d.edit("assets", ID, { name: "Jane" }, "2026-11-19T10:00:00.000Z");
  for (let i = 0; i < 6; i++) { s.failNextPush = "before"; await d.engine.syncNow(); }
  assert.deepEqual(d.timers, [2000, 4000, 8000, 16000, 30000, 30000]);
  assert.equal(d.engine.status().pending, 1);
  const st = await d.engine.syncNow();
  assert.equal(st.state, "idle");
  assert.equal(s.tables.assets.get(ID).name, "Jane");
  assert.equal(d.engine._failures(), 0, "backoff resets after a good sync");
});

test("an edit made while an upload is in flight isn't lost", async () => {
  const s = makeServer(); let d;
  const slowServer = Object.assign(Object.create(s), {
    async push(table, rows) { const r = await s.push.call(s, table, rows); await d.edit("assets", ID, { name: "Jane 2" }, "2026-11-19T10:01:00.000Z"); return r; },
    pull: s.pull.bind(s),
  });
  d = makeDevice(slowServer, "A");
  await d.edit("assets", ID, { name: "Jane 1" }, "2026-11-19T10:00:00.000Z");
  await d.engine.syncNow();
  assert.equal(d.engine.status().pending, 1, "the second edit is still queued");
  slowServer.push = s.push.bind(s);
  await d.engine.syncNow();
  assert.equal(s.tables.assets.get(ID).name, "Jane 2");
  assert.equal(s.conflicts.length, 0, "its base moved forward, so it's a plain edit");
});

test("pull pages through many changes and keeps its cursor", async () => {
  const s = makeServer(); const writer = makeDevice(s, "W", { batchSize: 200 }); const reader = makeDevice(s, "R", { pageSize: 500 });
  for (let i = 0; i < 1200; i++) await writer.edit("assets", "id-" + String(i).padStart(4, "0"), { name: "S" + i }, "2026-11-19T10:00:00.000Z");
  await writer.engine.syncNow();
  let pulls = 0; const p = s.pull.bind(s); s.pull = async (...a) => { pulls++; return p(...a); };
  await reader.engine.syncNow();
  assert.equal(reader.local.size, 1200);
  const assetPulls = pulls; pulls = 0;
  await reader.engine.syncNow();
  assert.ok(assetPulls >= 3, "1,200 rows came in pages of 500");
  assert.equal(pulls, 6, "next sync asks each table once and gets nothing new");
});

test("a rejected row is set aside, not retried forever, and doesn't block the others", async () => {
  const s = makeServer(); const d = makeDevice(s, "A");
  const p = s.push.bind(s);
  s.push = async (table, rows) => (await p(table, rows)).map(r => r.id === "taken" ? { id: r.id, status: "rejected" } : r);
  await d.edit("assets", "taken", { name: "X" }, "2026-11-19T10:00:00.000Z");
  await d.edit("assets", ID, { name: "Jane" }, "2026-11-19T10:00:00.000Z");
  const st = await d.engine.syncNow();
  assert.equal(st.pending, 0);
  assert.equal(st.failed, 1);
  assert.equal(s.tables.assets.get(ID).name, "Jane");
});

test("uuid5 matches Python's uuid.uuid5 (the import script uses it)", async () => {
  const sha1 = async b => crypto.createHash("sha1").update(Buffer.from(b)).digest();
  const id = await uuid5(sha1, "8f4e6c1a-3b2d-4e5f-9a7b-1c2d3e4f5a6b", "11111111-2222-3333-4444-555555555555:mission:Batch A");
  assert.equal(id, "baea143f-3330-5c9f-8b88-0fff34788c0f");
});

test("backoffDelay grows and caps", () => {
  assert.equal(backoffDelay(1, 1000, 8000, () => 1), 1000);
  assert.equal(backoffDelay(4, 1000, 8000, () => 1), 8000);
  assert.equal(backoffDelay(9, 1000, 8000, () => 1), 8000);
  assert.equal(backoffDelay(3, 1000, 8000, () => 0), 2000, "jitter goes down to half");
});
