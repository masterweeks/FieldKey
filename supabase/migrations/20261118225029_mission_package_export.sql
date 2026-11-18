-- FieldKey Phase 4: "Export mission package" (GeoPackage) jobs.
-- Additive only: two new tables, one new login role, one new private bucket, helper functions.
--
--   export_tile_sources  basemaps the export may download. EMPTY on purpose: a source is only
--                        added (by a later migration) after it has been approved. See docs/export.md.
--   export_jobs          one row per requested package. FieldKey inserts it; the worker
--                        (worker/ in the repo) claims it, builds the .gpkg, uploads it to the
--                        private "exports" bucket and marks it done.
--   export_worker        database login the worker uses. Reads the feature tables (all owners,
--                        filtered per job by owner_id in the worker's queries), updates jobs.
--                        No password here: set one with scripts/make_db_password.py --role export_worker.

-- ---------- approved basemap sources ----------
create table if not exists public.export_tile_sources (
  id             text primary key check (id ~ '^[a-z][a-z0-9_]{1,30}$'),
  name           text not null,
  url_template   text not null check (url_template like 'https://%' and url_template like '%{z}%' and url_template like '%{x}%' and url_template like '%{y}%'),
  tile_format    text not null check (tile_format in ('png', 'jpeg')),
  min_zoom       int  not null default 0  check (min_zoom between 0 and 22),
  max_zoom       int  not null            check (max_zoom between 0 and 22),
  avg_tile_bytes int  not null            check (avg_tile_bytes between 1000 and 500000),   -- used for size estimates
  attribution    text not null,
  license        text not null,
  approved_by    text not null,
  approved_at    timestamptz not null default now(),
  enabled        boolean not null default true,
  check (min_zoom <= max_zoom)
);
alter table public.export_tile_sources enable row level security;
revoke all on public.export_tile_sources from anon, authenticated;
grant select on public.export_tile_sources to authenticated;
drop policy if exists export_tile_sources_read on public.export_tile_sources;
create policy export_tile_sources_read on public.export_tile_sources for select to authenticated using (enabled);

-- ---------- export jobs ----------
create table if not exists public.export_jobs (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid not null references auth.users (id) on delete cascade,
  mission_ids      uuid[] not null check (cardinality(mission_ids) between 1 and 50),
  include_contacts boolean not null default false,          -- names and phone numbers (off by default)
  include_pins     boolean not null default true,
  basemaps         text[] not null default '{}',
  min_zoom         int not null default 10 check (min_zoom between 0 and 18),
  max_zoom         int not null default 16 check (max_zoom between 0 and 18),
  buffer_m         int not null default 300 check (buffer_m between 0 and 5000),
  cap_mb           int not null default 45 check (cap_mb between 1 and 1000),
  status           text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed', 'cancelled', 'expired')),
  cancel_requested boolean not null default false,
  progress         int not null default 0 check (progress between 0 and 100),
  message          text,
  error            text,
  estimate_bytes   bigint,
  size_bytes       bigint,
  feature_count    int,
  tile_count       int,
  storage_path     text,
  file_name        text,
  attempts         int not null default 0,
  created_at       timestamptz not null default now(),
  started_at       timestamptz,
  heartbeat_at     timestamptz,
  finished_at      timestamptz,
  expires_at       timestamptz,
  check (min_zoom <= max_zoom)
);
create index if not exists export_jobs_owner_idx on public.export_jobs (owner_id, created_at desc);
create index if not exists export_jobs_queue_idx on public.export_jobs (created_at) where status = 'queued';

-- New requests: owner comes from the sign-in, worker fields start empty, basemaps must be
-- approved sources, and a user can't flood the queue.
create or replace function public.fk_export_job_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  uid uuid := public.fk_uid();
  bad text;
begin
  if uid is null then
    raise exception 'export jobs are requested from FieldKey (signed in)';
  end if;
  new.owner_id := uid;
  new.status := 'queued'; new.cancel_requested := false; new.progress := 0; new.attempts := 0;
  new.message := null; new.error := null; new.size_bytes := null; new.feature_count := null; new.tile_count := null;
  new.storage_path := null; new.file_name := null; new.started_at := null; new.heartbeat_at := null;
  new.finished_at := null; new.expires_at := null; new.created_at := now();
  new.basemaps := coalesce((select array_agg(distinct b order by b) from unnest(new.basemaps) b), '{}');

  select b into bad from unnest(new.basemaps) b
  where not exists (select 1 from public.export_tile_sources s where s.id = b and s.enabled) limit 1;
  if bad is not null then
    raise exception 'basemap "%" is not an approved export source', bad;
  end if;
  if exists (select 1 from unnest(new.mission_ids) m
             where not exists (select 1 from public.missions x where x.id = m and x.owner_id = uid)) then
    raise exception 'one of the missions is not in your account (sync first)';
  end if;
  if (select count(*) from public.export_jobs j where j.owner_id = uid and j.status in ('queued', 'running')) >= 3 then
    raise exception 'you already have 3 exports in progress; wait for one to finish';
  end if;
  if (select count(*) from public.export_jobs j where j.owner_id = uid and j.created_at > now() - interval '1 day') >= 30 then
    raise exception 'daily export limit reached (30)';
  end if;
  return new;
end $$;

drop trigger if exists export_jobs_a_guard on public.export_jobs;
create trigger export_jobs_a_guard before insert on public.export_jobs
  for each row execute function public.fk_export_job_guard();

alter table public.export_jobs enable row level security;
revoke all on public.export_jobs from anon, authenticated;
grant select, insert on public.export_jobs to authenticated;
grant update (cancel_requested) on public.export_jobs to authenticated;   -- the only thing a user can change
drop policy if exists export_jobs_owner_select on public.export_jobs;
create policy export_jobs_owner_select on public.export_jobs for select to authenticated using (owner_id = (select public.fk_uid()));
drop policy if exists export_jobs_owner_insert on public.export_jobs;
create policy export_jobs_owner_insert on public.export_jobs for insert to authenticated with check (owner_id = (select public.fk_uid()));
drop policy if exists export_jobs_owner_cancel on public.export_jobs;
create policy export_jobs_owner_cancel on public.export_jobs for update to authenticated
  using (owner_id = (select public.fk_uid()) and status in ('queued', 'running'))
  with check (owner_id = (select public.fk_uid()));

-- ---------- wake the worker when a job is queued (optional; no-op until configured) ----------
-- After deploying the worker: enable pg_net and store two Vault secrets
-- (export_worker_url, export_worker_token). See docs/export.md. Until then this does nothing
-- and the worker can run in "loop" mode instead.
create or replace function public.fk_export_notify()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  u text; t text;
begin
  if to_regnamespace('net') is null or to_regnamespace('vault') is null then
    return null;
  end if;
  execute 'select max(decrypted_secret) filter (where name = ''export_worker_url''),
                  max(decrypted_secret) filter (where name = ''export_worker_token'')
           from vault.decrypted_secrets where name in (''export_worker_url'', ''export_worker_token'')'
    into u, t;
  if u is null or t is null then
    return null;
  end if;
  execute 'select net.http_post(url := $1, body := $2, headers := $3, timeout_milliseconds := 5000)'
    using rtrim(u, '/') || '/run', jsonb_build_object('job', new.id),
          jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' || t);
  return null;
exception when others then
  return null;   -- never block a request because the wake-up call failed
end $$;
revoke all on function public.fk_export_notify() from public, anon, authenticated;

drop trigger if exists export_jobs_b_notify on public.export_jobs;
create trigger export_jobs_b_notify after insert on public.export_jobs
  for each row execute function public.fk_export_notify();

-- ---------- the worker's login ----------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'export_worker') then
    create role export_worker with login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls;
  end if;
end $$;
alter role export_worker set search_path = public, extensions;
alter role export_worker set statement_timeout = '120s';
grant usage on schema public to export_worker;
grant usage on schema extensions to export_worker;
revoke create on schema public from export_worker;

do $$
declare
  t text;
begin
  foreach t in array array['missions', 'circuits', 'assets', 'pins', 'inspections', 'photos', 'layer_styles', 'export_tile_sources'] loop
    execute format('revoke all on public.%I from export_worker', t);
    execute format('grant select on public.%I to export_worker', t);
    execute format('drop policy if exists %1$s_export_read on public.%1$I', t);
    execute format('create policy %1$s_export_read on public.%1$I for select to export_worker using (true)', t);
  end loop;
end $$;

revoke all on public.export_jobs from export_worker;
grant select, update on public.export_jobs to export_worker;
drop policy if exists export_jobs_worker_select on public.export_jobs;
create policy export_jobs_worker_select on public.export_jobs for select to export_worker using (true);
drop policy if exists export_jobs_worker_update on public.export_jobs;
create policy export_jobs_worker_update on public.export_jobs for update to export_worker using (true) with check (true);
grant execute on function public.fk_uid() to export_worker;

-- Re-run a failed, cancelled or expired export. Run from the SQL Editor (see docs/runbook.md).
create or replace function public.fk_export_requeue(p_job uuid)
returns void
language plpgsql
set search_path = ''
as $$
begin
  update public.export_jobs
  set status = 'queued', progress = 0, message = 'Queued again', error = null, cancel_requested = false,
      started_at = null, heartbeat_at = null, finished_at = null
  where id = p_job and status in ('failed', 'cancelled', 'expired');
  if not found then
    raise exception 'job % is not failed, cancelled or expired (or not yours)', p_job;
  end if;
end $$;
revoke all on function public.fk_export_requeue(uuid) from public, anon, authenticated;
grant execute on function public.fk_export_requeue(uuid) to export_worker;
-- Users re-request from FieldKey instead; the column-level grant above keeps them off other columns.

-- ---------- package files: private bucket, one folder per user ----------
-- Paths are <owner uuid>/<job uuid>/<file>.gpkg. Users can read (and so sign download links for)
-- only their own folder; only the worker (service key) writes and deletes.
-- 50 MB is the Supabase Free plan's per-file ceiling; raise it here and in cap_mb on a paid plan.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('exports', 'exports', false, 52428800, array['application/geopackage+sqlite3', 'application/octet-stream'])
on conflict (id) do nothing;

drop policy if exists fk_exports_owner_read on storage.objects;
create policy fk_exports_owner_read on storage.objects for select to authenticated
  using (bucket_id = 'exports' and (storage.foldername(name))[1] = (select auth.uid())::text);

update public.schema_info set version = 3 where true;
