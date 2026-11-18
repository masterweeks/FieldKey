#!/usr/bin/env python3
"""Move a FieldKey phone backup into the Supabase PostGIS tables.

FieldKey keeps its data on the phone. Make a backup in FieldKey (Settings -> Data ->
Back up data), copy the .json file here, then:

  Dry run (default; reads the file, writes nothing, prints what it would import):
    python scripts/import_backup.py fieldkey-backup-2026-11-18.json --owner <auth user uuid>

  Write a SQL file you then run in the Supabase SQL editor (or psql):
    python scripts/import_backup.py fieldkey-backup-2026-11-18.json --owner <uuid> --sql import.sql

--owner is the Supabase Auth user id the records belong to (Authentication -> Users).

Ids are fixed: each record's uuid is derived from its FieldKey id (uuid5), and inserts
use ON CONFLICT DO NOTHING, so running the SQL twice never duplicates anything.
The backup's "settings" block (which can hold API keys) is never read into the output.
"""
import argparse
import json
import sys
import uuid
from collections import Counter

NS = uuid.UUID("8f4e6c1a-3b2d-4e5f-9a7b-1c2d3e4f5a6b")   # FieldKey legacy-id namespace
STATUSES = {"new", "enriched", "texted", "replied", "scheduled", "done"}
PIN_KINDS = {"entrance", "parking", "hazard", "note"}


def fixed_id(owner, kind, legacy):
    return str(uuid.uuid5(NS, f"{owner}:{kind}:{legacy}"))


def lit(v):
    """SQL literal."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def jlit(v):
    return lit(json.dumps(v, ensure_ascii=False)) + "::jsonb"


def coord(rec):
    try:
        la, lo = float(rec.get("lat")), float(rec.get("lng"))
    except (TypeError, ValueError):
        return None
    if -90 <= la <= 90 and -180 <= lo <= 180 and not (la == 0 and lo == 0):
        return la, lo
    return None


def ts(v):
    v = (v or "").strip() if isinstance(v, str) else ""
    return v or None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup")
    ap.add_argument("--owner", required=True, help="Supabase Auth user id (uuid) that owns the data")
    ap.add_argument("--sql", help="write the import as SQL to this file (otherwise dry run only)")
    a = ap.parse_args()

    try:
        owner = str(uuid.UUID(a.owner))
    except ValueError:
        sys.exit("--owner must be a uuid (Supabase -> Authentication -> Users -> user id)")
    with open(a.backup, encoding="utf-8") as f:
        data = json.load(f)
    customers = data if isinstance(data, list) else data.get("customers") or []
    pins = [] if isinstance(data, list) else data.get("pins") or []

    missions, rows_a, rows_p, notes = {}, [], [], Counter()
    for c in customers:
        legacy = str(c.get("id") or "").strip()
        if not legacy:
            notes["customers skipped: no id"] += 1
            continue
        batch = (c.get("assignment") or "").strip()
        mid = None
        if batch:
            mid = missions.setdefault(batch, fixed_id(owner, "mission", batch))
        status = c.get("status") or "new"
        if status not in STATUSES:
            notes[f"unknown status '{status}' -> new"] += 1
            status = "new"
        pt = coord(c)
        if not pt:
            notes["assets without coordinates (imported, not drawn)"] += 1
        phones = [{"display": p.get("display", ""), "tel": p.get("tel", "")} for p in (c.get("phones") or []) if isinstance(p, dict)]
        rows_a.append({
            "id": fixed_id(owner, "asset", legacy), "legacy_id": legacy, "mission_id": mid,
            "sap_id": (c.get("sapId") or None), "name": c.get("name") or None, "address": c.get("address") or None,
            "phones": phones, "access": c.get("access") or None, "access_notes": c.get("accessNotes") or None,
            "status": status, "text_count": int(c.get("textCount") or 0),
            "last_texted_at": ts(c.get("lastTexted")), "scheduled_at": ts(c.get("scheduledAt")),
            "notes": c.get("notes") or None, "access_issue": bool(c.get("accessIssue")),
            "access_issue_reason": c.get("accessIssueReason") or None,
            "extra": c.get("extra") if isinstance(c.get("extra"), dict) else {}, "pt": pt,
        })
    for p in pins:
        legacy = str(p.get("id") or "").strip()
        pt = coord(p)
        if not legacy or not pt:
            notes["pins skipped: no id or location"] += 1
            continue
        kind = p.get("type") if p.get("type") in PIN_KINDS else "note"
        rows_p.append({"id": fixed_id(owner, "pin", legacy), "legacy_id": legacy, "kind": kind,
                       "label": p.get("label") or None, "notes": p.get("notes") or None,
                       "created": ts(p.get("created")), "pt": pt})

    print(f"Backup: {a.backup}")
    print(f"  missions (import batches): {len(missions)}")
    print(f"  assets: {len(rows_a)}  (with location: {sum(1 for r in rows_a if r['pt'])})")
    print(f"  pins:   {len(rows_p)}  {dict(Counter(r['kind'] for r in rows_p))}")
    for k, n in notes.items():
        print(f"  note: {k}: {n}")
    if not a.sql:
        print("\nDry run only: nothing written. Add --sql import.sql to produce the import.")
        return

    out = ["-- FieldKey backup import (generated by scripts/import_backup.py). Safe to run twice.",
           "begin;"]
    for name, mid in missions.items():
        out.append("insert into public.missions (id, owner_id, name, source_file, legacy_id) values "
                   f"({lit(mid)}, {lit(owner)}, {lit(name)}, {lit(name)}, {lit('batch:' + name)}) on conflict (id) do nothing;")
    for r in rows_a:
        geom = f"extensions.st_setsrid(extensions.st_makepoint({r['pt'][1]}, {r['pt'][0]}), 4326)" if r["pt"] else "null"
        out.append(
            "insert into public.assets (id, owner_id, mission_id, sap_id, name, address, phones, access, access_notes, status, "
            "text_count, last_texted_at, scheduled_at, notes, access_issue, access_issue_reason, extra, geom, legacy_id) values ("
            + ", ".join([lit(r["id"]), lit(owner), lit(r["mission_id"]), lit(r["sap_id"]), lit(r["name"]), lit(r["address"]),
                         jlit(r["phones"]), lit(r["access"]), lit(r["access_notes"]), lit(r["status"]), lit(r["text_count"]),
                         lit(r["last_texted_at"]), lit(r["scheduled_at"]), lit(r["notes"]), lit(r["access_issue"]),
                         lit(r["access_issue_reason"]), jlit(r["extra"]), geom, lit(r["legacy_id"])])
            + ") on conflict (id) do nothing;")
    for r in rows_p:
        geom = f"extensions.st_setsrid(extensions.st_makepoint({r['pt'][1]}, {r['pt'][0]}), 4326)"
        out.append("insert into public.pins (id, owner_id, kind, label, notes, geom, legacy_id, client_updated_at) values ("
                   + ", ".join([lit(r["id"]), lit(owner), lit(r["kind"]), lit(r["label"]), lit(r["notes"]), geom,
                                lit(r["legacy_id"]), lit(r["created"])]) + ") on conflict (id) do nothing;")
    out.append("commit;")
    with open(a.sql, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"\nWrote {len(out) - 3} insert statements to {a.sql}. Review it, then run it in the Supabase SQL editor.")


if __name__ == "__main__":
    main()
