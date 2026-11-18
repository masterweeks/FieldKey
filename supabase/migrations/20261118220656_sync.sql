-- FieldKey Phase 3: offline sync. Additive only.
--
-- Phones push and pull through two functions so the conflict rules live in one place:
--   fk_sync_push(table, rows)            idempotent upserts by uuid, last-write-wins
--   fk_sync_pull(table, since, since_id) changes after a (updated_at, id) cursor
-- Both run as the calling user (SECURITY INVOKER), so row-level security still decides
-- what each user can see and change.
--
-- Last-write-wins, with causality:
--   Each pushed row carries _base_updated_at: the server's updated_at the phone last saw.
--   * Server row unchanged since then  -> the push applies (a plain edit, not a conflict).
--   * Server row changed since then    -> a real conflict. The edit with the later
--     client_updated_at (the time it was made on its device) wins, and the losing version
--     is written to sync_conflicts so nothing is silently lost.
--   * Same content as the server row   -> "unchanged" (a retried upload is harmless).

-- ---------- QGIS edits count as made now (they have no device time) ----------
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
    else
      new.client_updated_at := now();   -- QGIS / SQL edits: stamped with the server's time
    end if;
  end if;
  new.updated_at := clock_timestamp();   -- distinct per row, so sync cursors never tie inside a batch
  new.updated_by := public.fk_actor();
  if new.client_updated_at is null then
    new.client_updated_at := now();
  end if;
  return new;
end;
$$;

-- ---------- conflict log ----------
create table if not exists public.sync_conflicts (
  id                     bigserial primary key,
  owner_id               uuid not null references auth.users (id),
  table_name             text not null,
  row_id                 uuid not null,
  kept                   text not null check (kept in ('incoming', 'server')),
  kept_version           jsonb not null,
  overwritten_version    jsonb not null,
  overwritten_edited_at  timestamptz,
  overwritten_by         text,
  detected_at            timestamptz not null default now(),
  resolved_at            timestamptz,
  resolved_by            text,
  resolution_note        text
);
create index if not exists sync_conflicts_owner_idx on public.sync_conflicts (owner_id, detected_at desc);
create index if not exists sync_conflicts_open_idx on public.sync_conflicts (row_id) where resolved_at is null;

alter table public.sync_conflicts enable row level security;
revoke all on public.sync_conflicts from anon, authenticated;
grant select, insert on public.sync_conflicts to authenticated;
grant update (resolved_at, resolved_by, resolution_note) on public.sync_conflicts to authenticated;
grant usage on sequence public.sync_conflicts_id_seq to authenticated;
drop policy if exists sync_conflicts_owner_select on public.sync_conflicts;
create policy sync_conflicts_owner_select on public.sync_conflicts for select to authenticated using (owner_id = (select auth.uid()));
drop policy if exists sync_conflicts_owner_insert on public.sync_conflicts;
create policy sync_conflicts_owner_insert on public.sync_conflicts for insert to authenticated with check (owner_id = (select auth.uid()));
drop policy if exists sync_conflicts_owner_resolve on public.sync_conflicts;
create policy sync_conflicts_owner_resolve on public.sync_conflicts for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

grant select on public.sync_conflicts to qgis_editor;
grant update (resolved_at, resolved_by, resolution_note) on public.sync_conflicts to qgis_editor;
drop policy if exists sync_conflicts_qgis_select on public.sync_conflicts;
create policy sync_conflicts_qgis_select on public.sync_conflicts for select to qgis_editor using (true);
drop policy if exists sync_conflicts_qgis_resolve on public.sync_conflicts;
create policy sync_conflicts_qgis_resolve on public.sync_conflicts for update to qgis_editor using (true) with check (true);

-- ---------- helpers ----------
-- Columns a phone may write, per table (everything else is set by the server).
create or replace function public.fk_sync_columns(p_table text)
returns text[]
language sql
immutable
set search_path = ''
as $$
  select case p_table
    when 'missions'    then array['name','source_file','status','notes','geom','legacy_id','client_updated_at','deleted_at']
    when 'circuits'    then array['name','code','notes','geom','legacy_id','client_updated_at','deleted_at']
    when 'assets'      then array['mission_id','circuit_id','sap_id','name','address','phones','access','access_notes','status',
                                  'text_count','last_texted_at','scheduled_at','notes','access_issue','access_issue_reason',
                                  'extra','geom','legacy_id','client_updated_at','deleted_at']
    when 'pins'        then array['mission_id','asset_id','kind','label','notes','geom','legacy_id','client_updated_at','deleted_at']
    when 'inspections' then array['mission_id','asset_id','inspected_at','outcome','notes','geom','legacy_id','client_updated_at','deleted_at']
    when 'photos'      then array['mission_id','asset_id','pin_id','inspection_id','storage_path','mime_type','taken_at','caption',
                                  'geom','legacy_id','client_updated_at','deleted_at']
  end;
$$;

-- A row as phones see it: geometry as GeoJSON.
create or replace function public.fk_sync_row_out(p_table text, p_id uuid)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  r jsonb;
begin
  if public.fk_sync_columns(p_table) is null then
    raise exception 'FieldKey sync: unknown table %', p_table using errcode = '22023';
  end if;
  execute format('select to_jsonb(t) - ''geom'' || jsonb_build_object(''geom'', extensions.st_asgeojson(t.geom)::jsonb)
                  from public.%I t where t.id = $1', p_table) into r using p_id;
  return r;
end;
$$;

-- An incoming row, keeping only writable columns, with values in the same form as
-- fk_sync_row_out (timestamps, numbers, GeoJSON) so the two can be compared.
create or replace function public.fk_sync_normalize(p_table text, p_row jsonb)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  cols text[] := public.fk_sync_columns(p_table);
  typed jsonb;
  out jsonb := '{}'::jsonb;
  k text;
begin
  execute format('select to_jsonb(r) from jsonb_populate_record(null::public.%I, $1) r', p_table)
    into typed using (p_row - 'geom');
  foreach k in array cols loop
    continue when not (p_row ? k);
    if k = 'geom' then
      out := out || jsonb_build_object('geom',
        case when p_row->'geom' is null or jsonb_typeof(p_row->'geom') = 'null' then null
             else extensions.st_asgeojson(extensions.st_setsrid(extensions.st_geomfromgeojson(p_row->>'geom'), 4326))::jsonb end);
    else
      out := out || jsonb_build_object(k, typed->k);
    end if;
  end loop;
  return out;
end;
$$;

-- ---------- push ----------
create or replace function public.fk_sync_push(p_table text, p_rows jsonb)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  cols text[] := public.fk_sync_columns(p_table);
  results jsonb := '[]'::jsonb;
  item jsonb; rid uuid; base timestamptz; incoming jsonb; existing jsonb;
  keys text[]; k text; differs boolean; concurrent boolean; in_cu timestamptz; ex_cu timestamptz;
  col_list text; val_list text; set_list text; status text; n int;
begin
  if cols is null then
    raise exception 'FieldKey sync: unknown table %', p_table using errcode = '22023';
  end if;
  if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) > 200 then
    raise exception 'FieldKey sync: send an array of at most 200 rows' using errcode = '22023';
  end if;

  for item in select value from jsonb_array_elements(p_rows) loop
    begin
      rid := (item->>'id')::uuid;
      base := nullif(item->>'_base_updated_at', '')::timestamptz;
      incoming := public.fk_sync_normalize(p_table, item);
      if not (incoming ? 'client_updated_at') or incoming->>'client_updated_at' is null then
        incoming := incoming || jsonb_build_object('client_updated_at', to_jsonb(now()));
      end if;
      select array_agg(x) into keys from jsonb_object_keys(incoming) x;

      execute format('select 1 from public.%I where id = $1 for update', p_table) using rid;   -- serialize edits to one row
      existing := public.fk_sync_row_out(p_table, rid);

      if existing is null and incoming->>'deleted_at' is not null then
        status := 'unchanged';   -- deleted before it ever reached the server
      elsif existing is null then
        col_list := 'id'; val_list := '$1';
        foreach k in array keys loop
          col_list := col_list || ', ' || quote_ident(k);
          val_list := val_list || ', ' || case when k = 'geom'
            then 'extensions.st_setsrid(extensions.st_geomfromgeojson($3), 4326)'
            else format('(jsonb_populate_record(null::public.%I, $2)).%I', p_table, k) end;
        end loop;
        execute format('insert into public.%I (%s) values (%s) on conflict (id) do nothing', p_table, col_list, val_list)
          using rid, incoming - 'geom', incoming->>'geom';
        get diagnostics n = row_count;
        status := case when n = 1 then 'inserted' else 'rejected' end;   -- id taken by a row this user can't see
      else
        differs := false;
        foreach k in array keys loop
          continue when k = 'client_updated_at';
          if (existing->k) is distinct from (incoming->k) then differs := true; exit; end if;
        end loop;
        in_cu := (incoming->>'client_updated_at')::timestamptz;
        ex_cu := (existing->>'client_updated_at')::timestamptz;
        concurrent := (existing->>'updated_at')::timestamptz > coalesce(base, '-infinity'::timestamptz);

        if not differs then
          status := 'unchanged';
        elsif concurrent and in_cu < ex_cu then
          status := 'stale';   -- someone else's later edit stands; keep this one in the log
          insert into public.sync_conflicts (owner_id, table_name, row_id, kept, kept_version, overwritten_version,
                                             overwritten_edited_at, overwritten_by)
          values ((existing->>'owner_id')::uuid, p_table, rid, 'server', existing, incoming, in_cu, public.fk_actor());
        else
          if concurrent then
            insert into public.sync_conflicts (owner_id, table_name, row_id, kept, kept_version, overwritten_version,
                                               overwritten_edited_at, overwritten_by)
            values ((existing->>'owner_id')::uuid, p_table, rid, 'incoming', incoming, existing, ex_cu, existing->>'updated_by');
          end if;
          set_list := '';
          foreach k in array keys loop
            set_list := set_list || case when set_list = '' then '' else ', ' end || quote_ident(k) || ' = ' ||
              case when k = 'geom'
                then 'extensions.st_setsrid(extensions.st_geomfromgeojson($3), 4326)'
                else format('(jsonb_populate_record(null::public.%I, $2)).%I', p_table, k) end;
          end loop;
          execute format('update public.%I set %s where id = $1', p_table, set_list) using rid, incoming - 'geom', incoming->>'geom';
          get diagnostics n = row_count;
          status := case when n = 1 then 'updated' else 'rejected' end;
        end if;
      end if;

      results := results || jsonb_build_array(jsonb_build_object(
        'id', rid, 'status', status, 'row', public.fk_sync_row_out(p_table, rid)));
    exception when others then
      results := results || jsonb_build_array(jsonb_build_object(
        'id', item->>'id', 'status', 'error', 'error', sqlerrm, 'code', sqlstate));
    end;
  end loop;
  return results;
end;
$$;

-- ---------- pull ----------
-- Rows changed after the cursor, oldest first. Pass the last row's updated_at back exactly
-- as received (microseconds matter) together with its id.
create or replace function public.fk_sync_pull(p_table text, p_since timestamptz default null,
                                               p_since_id uuid default null, p_limit int default 500)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  r jsonb;
begin
  if public.fk_sync_columns(p_table) is null then
    raise exception 'FieldKey sync: unknown table %', p_table using errcode = '22023';
  end if;
  execute format(
    'select coalesce(jsonb_agg(x order by (x->>''updated_at'')::timestamptz, x->>''id''), ''[]''::jsonb) from (
       select to_jsonb(t) - ''geom'' || jsonb_build_object(''geom'', extensions.st_asgeojson(t.geom)::jsonb) as x
       from public.%I t
       where (t.updated_at, t.id) > (coalesce($1, ''-infinity''::timestamptz), coalesce($2, ''00000000-0000-0000-0000-000000000000''::uuid))
       order by t.updated_at, t.id
       limit least(greatest(coalesce($3, 500), 1), 1000)) s', p_table)
    into r using p_since, p_since_id, p_limit;
  return r;
end;
$$;

revoke all on function public.fk_sync_push(text, jsonb) from public, anon;
revoke all on function public.fk_sync_pull(text, timestamptz, uuid, int) from public, anon;
revoke all on function public.fk_sync_row_out(text, uuid) from public, anon;
revoke all on function public.fk_sync_normalize(text, jsonb) from public, anon;
grant execute on function public.fk_sync_push(text, jsonb) to authenticated;
grant execute on function public.fk_sync_pull(text, timestamptz, uuid, int) to authenticated;
grant execute on function public.fk_sync_row_out(text, uuid) to authenticated;
grant execute on function public.fk_sync_normalize(text, jsonb) to authenticated;
grant execute on function public.fk_sync_columns(text) to authenticated;

update public.schema_info set version = 2, updated_at = now() where id;
