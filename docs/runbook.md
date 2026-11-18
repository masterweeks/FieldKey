# FieldKey runbook

Short procedures for the Supabase side of FieldKey. Project: `fdclbfqgsookhxfboxpn` (us-east-2).

## Rotate the `qgis_editor` password

The `qgis_editor` role is created by `supabase/migrations/20261118194037_qgis_editor_role.sql`
with **no password**, so nothing secret is ever in the repo. To set or rotate it:

Supabase logs every schema statement (`log_statement = ddl`), so never run
`alter role … password 'the-real-password'`: the password would end up in the database logs.
Set it from a one-way hash made on your computer instead:

1. In the repo folder, run:
   ```
   python scripts/make_db_password.py
   ```
   It prints a new random password and an `alter role qgis_editor with password 'SCRAM-SHA-256$…';`
   line. (To hash a password you already have: `python scripts/make_db_password.py --password-from-stdin`,
   then type it and press Enter.)
2. Save the **password** in your password manager.
3. Supabase dashboard → **SQL Editor** → **New query** → paste the `alter role …` line → **Run**.
   It holds only the hash, so it's safe in logs. Close the tab without saving it.
4. Update each QGIS install: **Settings → Options → Authentication** → edit
   **FieldKey qgis_editor** → paste the new password → **Save**.
5. Open QGIS connections keep working until they reconnect; new connections need the new password.

To lock QGIS out at once (lost laptop, etc.): run `alter role qgis_editor with password null;`,
then set a new one with the steps above when ready.

Check the hashing tool itself: `python scripts/make_db_password.py --self-test` (it compares against
the RFC 7677 test vector).

## Restore a paused project

Free Supabase projects pause after a week without activity. Restore from the dashboard
(**Project → Restore**). It takes a few minutes; QGIS and sync can't connect until it's back.

## Create a FieldKey sign-in (one per person)

FieldKey signs in with a Supabase Auth email + password. There is no sign-up screen in the app.

1. Supabase dashboard → **Authentication → Users → Add user → Create new user**.
2. Enter the email and a password, tick **Auto Confirm User**, then **Create user**.
3. On the phone: FieldKey → Settings → **Account & sync** → sign in.
4. Recommended: **Authentication → Sign In / Providers → Email**, turn **off** "Allow new users to sign up",
   so only accounts you create can sign in. (The publishable key in the app is public by design;
   row-level security means each account only ever sees its own rows.)

The first sign-in on a phone uploads everything already on it. If a *different* account signs in
later on the same phone, FieldKey refuses until local data is cleared, so one person's sites never
land in someone else's account.

## Resolve a logged sync conflict

Two edits to the same row that neither side had seen are settled automatically: the edit with the
later `client_updated_at` wins, and the losing version is kept in `sync_conflicts`. Nothing is lost,
but someone may want to check. In the SQL Editor (or QGIS → DB Manager):

```sql
-- open conflicts, newest first
select id, table_name, row_id, kept, overwritten_by, overwritten_edited_at, detected_at
from public.sync_conflicts
where resolved_at is null
order by detected_at desc;

-- compare the two versions of one conflict
select kept, kept_version, overwritten_version
from public.sync_conflicts where id = '<conflict id>';
```

`kept = 'incoming'` means the arriving edit won and `overwritten_version` is what was on the server;
`kept = 'server'` means the arriving edit was older and was the one set aside.

**If the kept version is right**, just mark it resolved:

```sql
update public.sync_conflicts
set resolved_at = now(), resolved_by = 'your name', resolution_note = 'kept as is'
where id = '<conflict id>';
```

**If the overwritten version should win**, edit the feature in QGIS (or FieldKey) to put the right
values back — that's a normal edit, so it syncs to every phone — then mark the conflict resolved as
above with a note like `restored overwritten status`. Don't copy values by hand-written `update`
statements into feature tables unless you also set `client_updated_at = now()`.

**A row that came back after a delete**: an edit made later than the delete restores the row (newer
wins). To delete it again, use the QGIS "Soft delete" action or delete it in FieldKey.

## Sync isn't moving

- Settings → Account & sync shows the pending count, last sync and the last error. "N waiting"
  with a cloud-off icon is just weak signal; it retries with backoff (2 s … 30 s) and every minute.
- **Retry failed** appears when the server rejected rows (for example a bad value). They stay on the
  phone; fix the site and tap Retry failed, or check the error text.
- "Your sign-in expired" means the refresh token was revoked or the password changed: sign in again.
  Queued edits are kept and upload after sign-in.
- To re-check the server rules, paste `supabase/tests/sync_rules_test.sql` into the SQL Editor and run
  it. It rolls everything back; the "error" it prints is the test report.

*Re-running a failed export is added with Phase 4.*
