-- FieldKey Phase 1 / 3 of 4: row-level security.
-- FieldKey users (Supabase Auth) see and change only their own rows, soft-deleted ones
-- included so deletions can sync. Nobody can hard-delete through the API: there is no
-- DELETE policy or grant; a delete is an update that sets deleted_at.

do $$
declare
  t text;
begin
  foreach t in array array['missions', 'circuits', 'assets', 'pins', 'inspections', 'photos'] loop
    execute format('alter table public.%I enable row level security', t);

    -- Supabase grants table rights to anon/authenticated by default; narrow them.
    execute format('revoke all on public.%I from anon', t);
    execute format('revoke all on public.%I from authenticated', t);
    execute format('grant select, insert, update on public.%I to authenticated', t);

    execute format('drop policy if exists %1$s_owner_select on public.%1$I', t);
    execute format('create policy %1$s_owner_select on public.%1$I for select to authenticated using (owner_id = (select auth.uid()))', t);
    execute format('drop policy if exists %1$s_owner_insert on public.%1$I', t);
    execute format('create policy %1$s_owner_insert on public.%1$I for insert to authenticated with check (owner_id = (select auth.uid()))', t);
    execute format('drop policy if exists %1$s_owner_update on public.%1$I', t);
    execute format('create policy %1$s_owner_update on public.%1$I for update to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()))', t);
  end loop;
end $$;

alter table public.schema_info enable row level security;
revoke all on public.schema_info from anon, authenticated;
grant select on public.schema_info to authenticated;
drop policy if exists schema_info_read on public.schema_info;
create policy schema_info_read on public.schema_info for select to authenticated using (true);
