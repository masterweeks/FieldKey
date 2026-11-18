-- FieldKey Phase 1 / 2 of 4: feature tables.
-- Every table: client-generated uuid id, EPSG:4326 geometry with a GiST index, audit
-- fields kept by public.fk_audit(), soft delete via deleted_at, owner_id for per-user
-- visibility, legacy_id for records that came from FieldKey's on-device database.

-- ---------- missions (a FieldKey import batch / work package) ----------
create table if not exists public.missions (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id),
  name              text not null,
  source_file       text,
  status            text not null default 'active' check (status in ('planned', 'active', 'complete', 'archived')),
  notes             text,
  geom              extensions.geometry(MultiPolygon, 4326),
  legacy_id         text,
  created_at        timestamptz not null default now(),
  created_by        text,
  updated_at        timestamptz not null default now(),
  updated_by        text,
  client_updated_at timestamptz,
  deleted_at        timestamptz
);

-- ---------- circuits (optional grouping of assets) ----------
create table if not exists public.circuits (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id),
  name              text not null,
  code              text,
  notes             text,
  geom              extensions.geometry(MultiPolygon, 4326),
  legacy_id         text,
  created_at        timestamptz not null default now(),
  created_by        text,
  updated_at        timestamptz not null default now(),
  updated_by        text,
  client_updated_at timestamptz,
  deleted_at        timestamptz
);

-- ---------- assets (one inspection site; FieldKey's "customers" records) ----------
-- name and phones are customer personal data: exports leave them out by default.
-- geom is nullable: contacts added by hand can lack coordinates.
create table if not exists public.assets (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null references auth.users (id),
  mission_id          uuid references public.missions (id),
  circuit_id          uuid references public.circuits (id),
  sap_id              text,
  name                text,
  address             text,
  phones              jsonb not null default '[]'::jsonb check (jsonb_typeof(phones) = 'array'),
  access              text,
  access_notes        text,
  status              text not null default 'new'
                        check (status in ('new', 'enriched', 'texted', 'replied', 'scheduled', 'done')),
  text_count          integer not null default 0 check (text_count >= 0),
  last_texted_at      timestamptz,
  scheduled_at        timestamptz,
  notes               text,
  access_issue        boolean not null default false,
  access_issue_reason text,
  extra               jsonb not null default '{}'::jsonb check (jsonb_typeof(extra) = 'object'),
  geom                extensions.geometry(Point, 4326),
  legacy_id           text,
  created_at          timestamptz not null default now(),
  created_by          text,
  updated_at          timestamptz not null default now(),
  updated_by          text,
  client_updated_at   timestamptz,
  deleted_at          timestamptz
);

-- ---------- pins (FieldKey's map pins: one table, kind tells them apart) ----------
create table if not exists public.pins (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id),
  mission_id        uuid references public.missions (id),
  asset_id          uuid references public.assets (id),
  kind              text not null default 'note' check (kind in ('entrance', 'parking', 'hazard', 'note')),
  label             text,
  notes             text,
  geom              extensions.geometry(Point, 4326) not null,
  legacy_id         text,
  created_at        timestamptz not null default now(),
  created_by        text,
  updated_at        timestamptz not null default now(),
  updated_by        text,
  client_updated_at timestamptz,
  deleted_at        timestamptz
);

-- ---------- inspections (one visit to an asset) ----------
create table if not exists public.inspections (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id),
  mission_id        uuid references public.missions (id),
  asset_id          uuid references public.assets (id),
  inspected_at      timestamptz,
  outcome           text not null default 'planned'
                      check (outcome in ('planned', 'completed', 'partial', 'no_access', 'cancelled')),
  notes             text,
  geom              extensions.geometry(Point, 4326),
  legacy_id         text,
  created_at        timestamptz not null default now(),
  created_by        text,
  updated_at        timestamptz not null default now(),
  updated_by        text,
  client_updated_at timestamptz,
  deleted_at        timestamptz
);

-- ---------- photos (files live in Supabase Storage; this row points at one) ----------
create table if not exists public.photos (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id),
  mission_id        uuid references public.missions (id),
  asset_id          uuid references public.assets (id),
  pin_id            uuid references public.pins (id),
  inspection_id     uuid references public.inspections (id),
  storage_path      text not null,
  mime_type         text,
  taken_at          timestamptz,
  caption           text,
  geom              extensions.geometry(Point, 4326),
  legacy_id         text,
  created_at        timestamptz not null default now(),
  created_by        text,
  updated_at        timestamptz not null default now(),
  updated_by        text,
  client_updated_at timestamptz,
  deleted_at        timestamptz,
  constraint photos_one_parent check (num_nonnulls(asset_id, pin_id, inspection_id) = 1)
);

-- ---------- indexes ----------
do $$
declare
  t text;
begin
  foreach t in array array['missions', 'circuits', 'assets', 'pins', 'inspections', 'photos'] loop
    execute format('create index if not exists %1$s_geom_gix on public.%1$I using gist (geom)', t);
    execute format('create index if not exists %1$s_owner_updated_idx on public.%1$I (owner_id, updated_at)', t);
    execute format('create index if not exists %1$s_updated_idx on public.%1$I (updated_at)', t);
    execute format('create unique index if not exists %1$s_owner_legacy_uq on public.%1$I (owner_id, legacy_id) where legacy_id is not null', t);
  end loop;
end $$;

create index if not exists assets_mission_idx      on public.assets (mission_id);
create index if not exists assets_circuit_idx      on public.assets (circuit_id);
create index if not exists assets_sap_idx          on public.assets (owner_id, sap_id) where sap_id is not null;
create index if not exists pins_mission_idx        on public.pins (mission_id);
create index if not exists pins_asset_idx          on public.pins (asset_id);
create index if not exists inspections_mission_idx on public.inspections (mission_id);
create index if not exists inspections_asset_idx   on public.inspections (asset_id);
create index if not exists photos_mission_idx      on public.photos (mission_id);
create index if not exists photos_asset_idx        on public.photos (asset_id);
create index if not exists photos_pin_idx          on public.photos (pin_id);
create index if not exists photos_inspection_idx   on public.photos (inspection_id);

-- ---------- triggers ----------
-- QGIS rows with no owner take their mission's owner (before the NOT NULL check fires).
create or replace function public.fk_inherit_owner()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.owner_id is null and new.mission_id is not null then
    select m.owner_id into new.owner_id from public.missions m where m.id = new.mission_id;
  end if;
  return new;
end;
$$;

-- Parents referenced by a row must have the same owner.
create or replace function public.fk_check_parents()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  j jsonb := to_jsonb(new);
begin
  if j ? 'mission_id'    then perform public.fk_check_same_owner(new.owner_id, 'missions',    (j->>'mission_id')::uuid); end if;
  if j ? 'circuit_id'    then perform public.fk_check_same_owner(new.owner_id, 'circuits',    (j->>'circuit_id')::uuid); end if;
  if j ? 'asset_id'      then perform public.fk_check_same_owner(new.owner_id, 'assets',      (j->>'asset_id')::uuid); end if;
  if j ? 'pin_id'        then perform public.fk_check_same_owner(new.owner_id, 'pins',        (j->>'pin_id')::uuid); end if;
  if j ? 'inspection_id' then perform public.fk_check_same_owner(new.owner_id, 'inspections', (j->>'inspection_id')::uuid); end if;
  return new;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array['missions', 'circuits', 'assets', 'pins', 'inspections', 'photos'] loop
    execute format('drop trigger if exists %1$s_a_audit on public.%1$I', t);
    execute format('create trigger %1$s_a_audit before insert or update on public.%1$I for each row execute function public.fk_audit()', t);
  end loop;
  foreach t in array array['assets', 'pins', 'inspections', 'photos'] loop
    execute format('drop trigger if exists %1$s_b_inherit_owner on public.%1$I', t);
    execute format('create trigger %1$s_b_inherit_owner before insert on public.%1$I for each row execute function public.fk_inherit_owner()', t);
    execute format('drop trigger if exists %1$s_c_check_parents on public.%1$I', t);
    execute format('create trigger %1$s_c_check_parents before insert or update on public.%1$I for each row execute function public.fk_check_parents()', t);
  end loop;
end $$;

-- Source schema version, read by exports (Phase 4) and sync (Phase 3).
create table if not exists public.schema_info (
  id         boolean primary key default true check (id),
  version    integer not null,
  updated_at timestamptz not null default now()
);
insert into public.schema_info (id, version) values (true, 1)
  on conflict (id) do update set version = greatest(public.schema_info.version, excluded.version), updated_at = now();
