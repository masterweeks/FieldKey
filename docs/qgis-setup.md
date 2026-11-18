# FieldKey in QGIS

QGIS reads and edits FieldKey's data directly in Supabase PostGIS. Tested with QGIS 3.44
(works with 3.30 or later). Supabase project: `fdclbfqgsookhxfboxpn` (us-east-2).

You only do steps 1–4 once per computer. After that, anyone with the login opens the project
with **Project → Open From → PostgreSQL → FieldKey**.

---

## 1. Give `qgis_editor` a password (once)

The login is created with no password. Set it without the password ever reaching the database
in readable form (Supabase logs schema statements, so a plain `alter role … password 'x'` would
leave it in the logs):

1. On your computer, in the repo folder:
   ```
   python scripts/make_db_password.py
   ```
2. It prints a new password and an `alter role qgis_editor with password 'SCRAM-SHA-256$…';` line.
   Save the **password** in your password manager now.
3. Open the Supabase dashboard → project **FieldKey** → **SQL Editor** → **New query**, paste the
   `alter role …` line, and click **Run**. It contains only a one-way hash.
4. Close the query tab without saving it.

To change it later, repeat these steps (see `docs/runbook.md`).

## 2. Find the connection details

Supabase dashboard → **Connect** (top of the project page) → **Session pooler**. Note:

| Setting  | Value |
|----------|-------|
| Host     | the pooler host shown there, e.g. `aws-1-us-east-2.pooler.supabase.com` |
| Port     | `5432` (session mode) |
| Database | `postgres` |
| Username | `qgis_editor.fdclbfqgsookhxfboxpn`, not `postgres.…` (the pooler needs the `.project-ref` suffix) |
| SSL mode | `require` |

Use the **session pooler**, not the direct `db.fdclbfqgsookhxfboxpn.supabase.co` host. The direct
host is IPv6-only, and most home and office networks can't reach it. Session mode also keeps the
connection's settings for its whole life, which QGIS relies on; transaction mode (port 6543) breaks it.

## 3. Store the login in QGIS (encrypted)

1. **Settings → Options → Authentication → ➕ (Add new authentication configuration)**.
2. Name: `FieldKey qgis_editor`. Type: **Basic authentication**.
3. Username: `qgis_editor.fdclbfqgsookhxfboxpn`. Password: the one from step 1.
4. **Save**. QGIS asks for its master password the first time; it encrypts every stored login.
5. Note the configuration's **ID**: 7 characters, shown next to the name, e.g. `fk3dqgs`.

## 4. Add the connection, then build the project

**Connection.** Browser panel → right-click **PostgreSQL** → **New Connection…**:

1. Fill in the name `FieldKey`, then the host, port, database and SSL mode from step 2.
2. Under **Authentication → Configurations**, pick `FieldKey qgis_editor`.
3. Tick **Allow saving/loading QGIS projects in the database**.
4. Click **Test Connection**, then **OK**.

**Build the project.** In the repo, open `qgis/fieldkey_qgis_setup.py` and set:
```python
HOST = "aws-1-us-east-2.pooler.supabase.com"   # your host from step 2
AUTHCFG = "fk3dqgs"                            # your ID from step 3
```
Then in QGIS: **Plugins → Python Console → Show Editor → Open Script…** → pick the file →
**Run Script**. It:

- adds a **FieldKey** group: Assets, Pins, Photos, Inspections, Circuits, Missions, plus OpenStreetMap
- styles and labels every layer and sets up the forms (next section)
- saves each style into the database as that layer's default (`public.layer_styles`), so anyone
  adding a layer from the Browser gets the same look, and GeoPackage exports carry it
- saves the project into Postgres as **FieldKey** in schema `qgis`

Run it again any time to rebuild the group and re-save.

---

## What the layers and forms do

**Filter.** Every layer shows only live features: its source has the filter
`deleted_at IS NULL`. To see deleted ones, open **Layer Properties → Source → Query Builder**
and clear the filter.

| Layer | Geometry | Styled by | Labels |
|-------|----------|-----------|--------|
| Assets | point (can be empty for hand-added contacts) | status, using FieldKey's pin colours | SAP ID, or name (closer than 1:10,000) |
| Pins | point | kind: Entrance / Parking / Hazard / Note | label |
| Photos | point (where taken) | white triangle | — |
| Inspections | point | green square | — |
| Missions | multipolygon (work area) | amber outline | name |
| Circuits | multipolygon | dashed blue outline | code or name |

**Forms:**

- **Value maps** turn stored codes into readable choices:
  - Asset `status`: new, enriched, texted, replied, scheduled, done.
  - Pin `kind`.
  - Mission `status`.
  - Inspection `outcome`.
- **Dropdowns:** Mission, Circuit, Asset, Pin and Inspection fields pick from the other layers
  by name, so you never type an ID.
- **Read-only system fields:** `id`, `created_at`, `created_by`, `updated_at`, `updated_by`,
  `client_updated_at` and `legacy_id`. The database sets them; it records QGIS edits as
  `db:qgis_editor`.
- **Read-only JSON:** `phones` and `extra`. Edit phone numbers in FieldKey.
- **Hidden:** `owner_id` and `deleted_at`.

**Owner.** Each feature belongs to one FieldKey user, and that user's phone is the only one
that sees it.
- **New assets, pins, inspections and photos:** pick a **Mission**. The owner is filled in from
  the mission, and the database rejects a mismatch.
- **New missions:** they take the owner of your existing missions. With several users, show
  `owner_id` in the form and set it to the right user's id (Supabase → Authentication → Users).

**Deleting.** Nobody can hard-delete, to keep sync safe. QGIS's delete tool fails with
*permission denied*. Instead, use the layer action **Soft delete (hide this feature)**: the
**Actions** toolbar or the right-click menu on a feature. It sets `deleted_at`, the feature
disappears from the layer, and FieldKey removes it on its next sync.

---

## Photos

The files live in the private Supabase Storage bucket **`photos`**.
- **Paths:** `<owner uuid>/<photo uuid>.jpg`, kept in `photos.storage_path`.
- **Phones:** FieldKey users can only read and add files in their own folder.
- **QGIS:** the **Photo** field uses the Attachment widget to show the image.

There are three ways to let QGIS fetch files from a private bucket:

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **A. Private bucket via S3 keys** (recommended) | Supabase Storage speaks S3. QGIS's Attachment widget fetches the file with an S3 access key saved in QGIS's encrypted store. | Photos stay private; no extra server; nothing expires | The S3 key can read the whole storage account, so keep it to trusted QGIS machines; needs QGIS 3.30+ |
| B. Signed URLs | A server (edge function) hands out links that expire after minutes | Finest control | A stored link stops working, so QGIS would need that function on every view: more to build and run |
| C. Public read-only bucket | Anyone with a file's URL can see it; paths are random UUIDs | Simplest | Photos of customers' property are viewable by anyone who gets a link |

**Setting up option A:**

1. Supabase → **Project Settings → Storage → S3 Connection**: note the endpoint
   (`https://fdclbfqgsookhxfboxpn.storage.supabase.co/storage/v1/s3`) and region (`us-east-2`).
   Create an **access key**; the secret is shown once.
2. QGIS → **Settings → Options → Authentication → ➕**:
   - Type: **AWS S3**.
   - Fill in the access key, the secret and region `us-east-2`.
   - Name it `FieldKey storage`.
3. In **Photos → Layer Properties → Attributes Form → Photo (storage_path)**:
   - Set **Storage type** to **AWS S3** and **Authentication** to `FieldKey storage`.
   - Set the **storage URL** expression to:
     ```
     'https://fdclbfqgsookhxfboxpn.storage.supabase.co/storage/v1/s3/photos/' || "storage_path"
     ```
   - Save the style as default when asked, or re-run the setup script after changing it there.

I couldn't test this without your S3 keys. If the image doesn't load, check the endpoint and
region first.

---

## Save and open the project from Postgres

The setup script saves it for you. To do it by hand:
- **Save:** **Project → Save To → PostgreSQL** → connection **FieldKey**, schema **qgis**,
  project name **FieldKey** → **OK**.
- **Open:** **Project → Open From → PostgreSQL** → **FieldKey** → **qgis** → **FieldKey**.
  Or browse to **FieldKey → qgis → FieldKey** in the Browser panel and double-click it.

**Check that project storage is ready.** Run this in the Supabase SQL Editor. Every column
except the last two should be `true`:

```sql
select
  to_regclass('qgis.qgis_projects') is not null                                      as qgis_projects_exists,
  has_schema_privilege('qgis_editor', 'qgis', 'usage')                              as qgis_schema_usage,
  has_table_privilege('qgis_editor', 'qgis.qgis_projects', 'select')                as can_open_projects,
  has_table_privilege('qgis_editor', 'qgis.qgis_projects', 'insert,update')         as can_save_projects,
  has_table_privilege('qgis_editor', 'public.layer_styles', 'select,insert,update') as can_save_styles,
  has_table_privilege('qgis_editor', 'public.assets', 'delete')                     as can_hard_delete,  -- false
  (select public from storage.buckets where id = 'photos')                          as photos_public;    -- false
```

## Troubleshooting

- **Connection refused / timeout:** the free Supabase project pauses after about a week without
  use. Restore it in the dashboard, which takes a few minutes. Also check you used the session
  pooler host on port 5432.
- **`password authentication failed`:** the username must be
  `qgis_editor.fdclbfqgsookhxfboxpn`, and the password the one you saved in step 1.
- **`null value in column "owner_id"`:** pick a Mission for the new feature.
- **`… belongs to a different user`:** the Mission, Asset or Pin you picked belongs to another
  user. Pick one of this feature owner's.
- **`permission denied for table …` when deleting:** use the Soft delete action.
