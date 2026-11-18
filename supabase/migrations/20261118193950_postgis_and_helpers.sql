-- FieldKey Phase 1 / 1 of 4: PostGIS and shared trigger helpers.
-- Additive only. Safe to re-run.

create extension if not exists postgis with schema extensions;

-- The signed-in Supabase Auth user, read from the request's JWT claim (what auth.uid()
-- returns), so roles without access to the auth schema, like qgis_editor, can call it.
create or replace function public.fk_uid()
returns uuid
language sql
stable
set search_path = ''
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
  )::uuid;
$$;

-- Who made this change, as text: the Supabase Auth user id for FieldKey users,
-- otherwise "db:<role>" (e.g. db:qgis_editor for edits made in QGIS).
create or replace function public.fk_actor()
returns text
language sql
stable
set search_path = ''
as $$
  select coalesce(public.fk_uid()::text, 'db:' || session_user::text);
$$;

-- Audit fields on every feature table.
--  * created_at / created_by are set once and can't be changed afterwards.
--  * updated_at / updated_by are always set by the server (pull cursors use updated_at).
--  * client_updated_at is the edit time on the device (conflicts are decided on it);
--    it defaults to now() when a client doesn't send one.
--  * owner_id: FieldKey users always own what they write and can't hand a row to someone
--    else. Rows written from QGIS (no auth user) take the owner of their mission when
--    owner_id is left empty.
create or replace function public.fk_audit()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  uid uuid := public.fk_uid();
begin
  if tg_op = 'INSERT' then
    new.created_at := now();
    new.created_by := public.fk_actor();
    if uid is not null then
      new.owner_id := uid;
    end if;
  else
    new.created_at := old.created_at;
    new.created_by := old.created_by;
    if uid is not null then
      new.owner_id := old.owner_id;
    end if;
  end if;
  new.updated_at := now();
  new.updated_by := public.fk_actor();
  if new.client_updated_at is null then
    new.client_updated_at := now();
  end if;
  return new;
end;
$$;

-- Child rows must belong to the same owner as the mission (and parent feature) they
-- point at, so nobody can attach data to another user's mission by guessing its id.
create or replace function public.fk_check_same_owner(child_owner uuid, parent_table text, parent_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
declare
  parent_owner uuid;
begin
  if parent_id is null then
    return;
  end if;
  execute format('select owner_id from public.%I where id = $1', parent_table)
    into parent_owner using parent_id;
  if parent_owner is null then
    raise exception 'FieldKey: % % does not exist', parent_table, parent_id using errcode = '23503';
  end if;
  if child_owner is distinct from parent_owner then
    raise exception 'FieldKey: % % belongs to a different user', parent_table, parent_id using errcode = '42501';
  end if;
end;
$$;
