-- FieldKey Phase 2: what QGIS needs in the database, plus the photo bucket.
-- Additive only. qgis_editor can't create tables, so the tables QGIS would normally
-- create on first use are created here, with only the rights it needs.

-- ---------- QGIS projects stored in Postgres (Project -> Save To -> PostgreSQL) ----------
-- Its own schema, not exposed through the Supabase API.
create schema if not exists qgis;
revoke all on schema qgis from public;
grant usage on schema qgis to qgis_editor;

-- The layout QGIS uses for project storage.
create table if not exists qgis.qgis_projects (
  name     text primary key,
  metadata jsonb,
  content  bytea
);
alter table qgis.qgis_projects enable row level security;
revoke all on qgis.qgis_projects from public;
grant select, insert, update, delete on qgis.qgis_projects to qgis_editor;   -- delete only removes a saved project file
drop policy if exists qgis_projects_qgis on qgis.qgis_projects;
create policy qgis_projects_qgis on qgis.qgis_projects for all to qgis_editor using (true) with check (true);

-- ---------- layer styles (QGIS "Save as default in datasource database"; Phase 4 embeds them) ----------
-- Same columns QGIS creates itself (unquoted names, so lower case).
create table if not exists public.layer_styles (
  id                serial primary key,
  f_table_catalog   varchar,
  f_table_schema    varchar,
  f_table_name      varchar,
  f_geometry_column varchar,
  stylename         text,
  styleqml          xml,
  stylesld          xml,
  useasdefault      boolean,
  description       text,
  owner             varchar(63) default current_user,
  ui                xml,
  update_time       timestamp default current_timestamp,
  type              varchar,
  r_raster_column   varchar
);
alter table public.layer_styles enable row level security;
revoke all on public.layer_styles from anon, authenticated;
grant select, insert, update on public.layer_styles to qgis_editor;
grant usage on sequence public.layer_styles_id_seq to qgis_editor;
drop policy if exists layer_styles_qgis on public.layer_styles;
create policy layer_styles_qgis on public.layer_styles for all to qgis_editor using (true) with check (true);

-- ---------- photo files: private bucket, one folder per user ----------
-- Paths are <owner uuid>/<photo uuid>.<ext>; the photos table keeps the path.
-- FieldKey users can add and read only their own folder; nobody deletes through the API.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', false, 15728640, array['image/jpeg', 'image/png', 'image/webp', 'image/heic'])
on conflict (id) do nothing;

drop policy if exists fk_photos_owner_read on storage.objects;
create policy fk_photos_owner_read on storage.objects for select to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists fk_photos_owner_insert on storage.objects;
create policy fk_photos_owner_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists fk_photos_owner_update on storage.objects;
create policy fk_photos_owner_update on storage.objects for update to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);
