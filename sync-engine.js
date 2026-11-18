/* FieldKey sync engine: outbox push + cursor pull against Supabase (fk_sync_push / fk_sync_pull).
 *
 * Every local create / update / delete is queued in an outbox first (one entry per row: a later
 * edit to the same row replaces the queued one). When online, the engine
 *   1. pushes the outbox table by table, parents first, in batches, as idempotent upserts by uuid;
 *   2. pulls everything changed on the server since its per-table (updated_at, id) cursor.
 * The server decides conflicts (last-write-wins on the device edit time, with every overwritten
 * version kept in sync_conflicts). A failed round retries with exponential backoff.
 *
 * No browser or Node APIs are used directly: storage, network, clock and "apply this row
 * locally" are passed in, so tests can run the same code against a fake server.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FKSync = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TABLE_ORDER = ["missions", "circuits", "assets", "pins", "inspections", "photos"];

  // retry delay after n consecutive failures: 2s, 4s, 8s ... capped, with jitter
  function backoffDelay(n, baseMs, maxMs, rand) {
    const exp = Math.min(maxMs, baseMs * Math.pow(2, Math.max(0, n - 1)));
    return Math.round(exp * (0.5 + 0.5 * (rand ? rand() : Math.random())));
  }

  // RFC 4122 version-5 uuid (same result as Python's uuid.uuid5), given an async SHA-1.
  async function uuid5(sha1, namespace, name) {
    const ns = namespace.replace(/-/g, "");
    const nsBytes = new Uint8Array(16);
    for (let i = 0; i < 16; i++) nsBytes[i] = parseInt(ns.substr(i * 2, 2), 16);
    const nameBytes = new TextEncoder().encode(name);
    const buf = new Uint8Array(16 + nameBytes.length);
    buf.set(nsBytes, 0); buf.set(nameBytes, 16);
    const h = new Uint8Array(await sha1(buf)).slice(0, 16);
    h[6] = (h[6] & 0x0f) | 0x50;
    h[8] = (h[8] & 0x3f) | 0x80;
    const hex = Array.from(h, b => b.toString(16).padStart(2, "0")).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
  }

  function createSyncEngine(opts) {
    const o = Object.assign({
      tables: TABLE_ORDER, batchSize: 100, pageSize: 500, maxAttempts: 5,
      retryBaseMs: 2000, retryMaxMs: 5 * 60 * 1000,
      now: () => new Date(), isOnline: () => true, setTimer: (fn, ms) => setTimeout(fn, ms), clearTimer: t => clearTimeout(t),
      onStatus: () => {}, rand: Math.random,
    }, opts);
    const { store, transport, applyRemote } = o;
    let running = null, failures = 0, retryTimer = null, intervalTimer = null;
    const st = { state: "idle", pending: 0, failed: 0, lastSyncAt: null, lastError: null, nextRetryAt: null, conflicts: 0 };

    function emit() { o.onStatus(Object.assign({}, st)); }
    async function refreshCounts() {
      const all = await store.outboxAll();
      st.pending = all.filter(e => !e.failed).length;
      st.failed = all.filter(e => e.failed).length;
    }

    async function enqueue(table, row) {
      if (!row || !row.id) throw new Error("enqueue needs a row with an id");
      const key = table + ":" + row.id;
      await store.outboxPut({ key, table, id: row.id, row, queuedAt: o.now().toISOString(), attempts: 0, failed: false, lastError: null });
      await refreshCounts(); emit();
    }

    async function pushTable(table) {
      const entries = (await store.outboxAll()).filter(e => e.table === table && !e.failed);
      for (let i = 0; i < entries.length; i += o.batchSize) {
        const batch = entries.slice(i, i + o.batchSize);
        const results = await transport.push(table, batch.map(e => e.row));   // throws on network / auth failure
        const byId = new Map((results || []).map(r => [String(r.id), r]));
        for (const e of batch) {
          const r = byId.get(String(e.id));
          const current = (await store.outboxAll()).find(x => x.key === e.key);
          const unchangedSinceSent = current && current.queuedAt === e.queuedAt;   // not edited again while in flight
          if (!r) continue;
          if (r.status === "inserted" || r.status === "updated" || r.status === "unchanged" || r.status === "stale") {
            if (r.status === "stale") st.conflicts++;
            if (unchangedSinceSent) {
              await store.outboxDelete(e.key);
              if (r.row) await applyRemote(table, r.row, { via: "push", status: r.status });
            } else if (r.row && current && r.status !== "stale") {
              // a newer local edit is queued on top of the version just accepted: move its base
              // forward so it isn't mistaken for a conflict. (After "stale" the base stays old, so
              // the server weighs that newer edit against the other device's.)
              current.row = Object.assign({}, current.row, { _base_updated_at: r.row.updated_at });
              await store.outboxPut(current);
            }
          } else {
            // "rejected" (id belongs to someone else) is permanent; errors retry a few times
            if (!current) continue;
            current.attempts = (current.attempts || 0) + 1;
            current.lastError = r.error || r.status;
            current.failed = r.status === "rejected" || current.attempts >= o.maxAttempts;
            await store.outboxPut(current);
          }
        }
      }
    }

    async function pullTable(table) {
      const ck = "cursor:" + table;
      let cursor = (await store.metaGet(ck)) || { ts: null, id: null };
      for (;;) {
        const rows = await transport.pull(table, cursor.ts, cursor.id, o.pageSize);
        if (!rows || !rows.length) break;
        const waiting = new Set((await store.outboxAll()).filter(e => e.table === table && !e.failed).map(e => String(e.id)));
        for (const row of rows) {
          // a local edit still waiting to upload wins locally until the server rules on it
          if (!waiting.has(String(row.id))) await applyRemote(table, row, { via: "pull" });
        }
        const last = rows[rows.length - 1];
        cursor = { ts: last.updated_at, id: last.id };   // updated_at kept as the server's string (microseconds)
        await store.metaSet(ck, cursor);
        if (rows.length < o.pageSize) break;
      }
    }

    function scheduleRetry() {
      if (retryTimer) o.clearTimer(retryTimer);
      const ms = backoffDelay(failures, o.retryBaseMs, o.retryMaxMs, o.rand);
      st.nextRetryAt = new Date(o.now().getTime() + ms).toISOString();
      retryTimer = o.setTimer(() => { retryTimer = null; syncNow(); }, ms);
      return ms;
    }

    function syncNow() {
      if (running) return running;
      running = (async () => {
        try {
          if (!o.isOnline()) { st.state = "offline"; await refreshCounts(); emit(); return st; }
          st.state = "syncing"; st.lastError = null; emit();
          for (const t of o.tables) await pushTable(t);
          for (const t of o.tables) await pullTable(t);
          failures = 0; st.nextRetryAt = null;
          st.state = "idle"; st.lastSyncAt = o.now().toISOString();
          if (retryTimer) { o.clearTimer(retryTimer); retryTimer = null; }
        } catch (err) {
          failures++;
          st.state = "error"; st.lastError = (err && err.message) || String(err);
          if (!(err && err.permanent)) scheduleRetry();
        } finally {
          await refreshCounts(); emit();
          running = null;
        }
        return Object.assign({}, st);
      })();
      return running;
    }

    function start(intervalMs) {
      stop();
      if (intervalMs) intervalTimer = setInterval(() => { if (o.isOnline()) syncNow(); }, intervalMs);
      return syncNow();
    }
    function stop() {
      if (intervalTimer) { clearInterval(intervalTimer); intervalTimer = null; }
      if (retryTimer) { o.clearTimer(retryTimer); retryTimer = null; }
    }
    async function retryFailed() {
      for (const e of await store.outboxAll()) if (e.failed) { e.failed = false; e.attempts = 0; await store.outboxPut(e); }
      await refreshCounts(); emit();
    }

    return { enqueue, syncNow, start, stop, retryFailed, status: () => Object.assign({}, st), refreshCounts,
             _failures: () => failures };
  }

  return { createSyncEngine, backoffDelay, uuid5, TABLE_ORDER };
});
