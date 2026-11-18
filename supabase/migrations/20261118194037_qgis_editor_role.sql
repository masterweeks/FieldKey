-- FieldKey Phase 1 / 4 of 4: the qgis_editor login for QGIS.
-- Can read, add and edit the feature tables only (all users' rows: it's the desktop
-- GIS account). No DELETE, no TRUNCATE, no access to auth, storage or other schemas,
-- and RLS still applies to it (no BYPASSRLS), through the qgis_* policies below.
--
-- No password is set here, so the role can't log in until you set one yourself:
--   alter role qgis_editor with password '<a long random password>';
-- Run that in the Supabase SQL editor; never commit it. See docs/runbook.md.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'qgis_editor') then
    create role qgis_editor with login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls;
  end if;
end $$;

alter role qgis_editor set search_path = public, extensions;
alter role qgis_editor set statement_timeout = '60s';

-- schemas: public (feature tables) and extensions (PostGIS types and functions)
grant usage on schema public to qgis_editor;
grant usage on schema extensions to qgis_editor;
revoke create on schema public from qgis_editor;

-- PostGIS metadata QGIS reads to list layers and their SRIDs
grant select on extensions.spatial_ref_sys to qgis_editor;
grant select on extensions.geometry_columns to qgis_editor;

do $$
declare
  t text;
begin
  foreach t in array array['missions', 'circuits', 'assets', 'pins', 'inspections', 'photos'] loop
    execute format('revoke all on public.%I from qgis_editor', t);
    execute format('grant select, insert, update on public.%I to qgis_editor', t);
    execute format('drop policy if exists %1$s_qgis_select on public.%1$I', t);
    execute format('create policy %1$s_qgis_select on public.%1$I for select to qgis_editor using (true)', t);
    execute format('drop policy if exists %1$s_qgis_insert on public.%1$I', t);
    execute format('create policy %1$s_qgis_insert on public.%1$I for insert to qgis_editor with check (true)', t);
    execute format('drop policy if exists %1$s_qgis_update on public.%1$I', t);
    execute format('create policy %1$s_qgis_update on public.%1$I for update to qgis_editor using (true) with check (true)', t);
  end loop;
end $$;

grant select on public.schema_info to qgis_editor;
drop policy if exists schema_info_qgis_read on public.schema_info;
create policy schema_info_qgis_read on public.schema_info for select to qgis_editor using (true);

-- the trigger helpers run as the caller, so qgis_editor needs to be able to call them
grant execute on function public.fk_uid() to qgis_editor;
grant execute on function public.fk_actor() to qgis_editor;
grant execute on function public.fk_check_same_owner(uuid, text, uuid) to qgis_editor;

-- Users are read for owner_id foreign keys only through the constraint check, which
-- doesn't need a grant; qgis_editor gets no access to the auth schema.
