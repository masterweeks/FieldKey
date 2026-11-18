-- Server-side sync tests. Paste into the Supabase SQL Editor and run.
-- Everything happens inside one transaction that ends by raising the report as an error,
-- so nothing is kept: the "error" you see IS the test report. Every line should read as expected.
do $$
declare
  a uuid := '00000000-0000-4000-8000-00000000000a';
  b uuid := '00000000-0000-4000-8000-00000000000b';
  sid uuid := gen_random_uuid(); mid uuid := gen_random_uuid();
  r jsonb; base1 text; base2 text; rep text := ''; n int; v text; cur_ts text; cur_id text;
  pt jsonb := '{"type":"Point","coordinates":[-121.49,38.58]}';
begin
  insert into auth.users (id, aud, role, email) values (a,'authenticated','authenticated','a@test.invalid'), (b,'authenticated','authenticated','b@test.invalid');
  perform set_config('request.jwt.claims', json_build_object('sub',a,'role','authenticated')::text, true);
  execute 'set local role authenticated';

  r := public.fk_sync_push('missions', jsonb_build_array(jsonb_build_object('id',mid,'name','Batch A','client_updated_at','2026-11-19T10:00:00Z')));
  rep := rep || '1a new mission (inserted): ' || (r->0->>'status') || E'\n';
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'mission_id',mid,'sap_id','100000001','name','Jane','status','new',
          'phones','[{"display":"(530) 555-0101","tel":"+15305550101"}]'::jsonb,'geom',pt,'deleted_at',null,'client_updated_at','2026-11-19T10:00:00Z')));
  rep := rep || '1b new asset (inserted): ' || (r->0->>'status') || E'\n';
  base1 := r->0->'row'->>'updated_at';

  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'mission_id',mid,'sap_id','100000001','name','Jane','status','new',
          'phones','[{"display":"(530) 555-0101","tel":"+15305550101"}]'::jsonb,'geom',pt,'deleted_at',null,'client_updated_at','2026-11-19T10:00:00Z')));
  rep := rep || '2 interrupted upload retried (unchanged): ' || (r->0->>'status') || E'\n';

  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base1,'status','texted','client_updated_at','2026-11-19T11:00:00Z')));
  rep := rep || '3 plain edit (updated): ' || (r->0->>'status') || E'\n';

  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base1,'status','replied','client_updated_at','2026-11-19T12:00:00Z')));
  rep := rep || '4a two devices, later edit (updated/replied): ' || (r->0->>'status') || '/' || (r->0->'row'->>'status') || E'\n';
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base1,'status','done','client_updated_at','2026-11-19T10:30:00Z')));
  rep := rep || '4b two devices, earlier edit (stale/replied): ' || (r->0->>'status') || '/' || (r->0->'row'->>'status') || E'\n';
  select count(*) into n from public.sync_conflicts where row_id = sid; rep := rep || '4c conflicts logged (2): ' || n || E'\n';

  select (public.fk_sync_row_out('assets', sid))->>'updated_at' into base2;
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base2,'deleted_at','2026-11-19T13:00:00Z','client_updated_at','2026-11-19T13:00:00Z')));
  rep := rep || '5a delete (updated): ' || (r->0->>'status') || E'\n';
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base1,'name','Jane D','deleted_at',null,'client_updated_at','2026-11-19T12:30:00Z')));
  rep := rep || '5b older edit vs delete (stale, still deleted): ' || (r->0->>'status') || ', deleted=' || ((r->0->'row'->>'deleted_at') is not null) || E'\n';
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'_base_updated_at',base1,'name','Jane D','deleted_at',null,'client_updated_at','2026-11-19T14:00:00Z')));
  rep := rep || '5c newer edit vs delete (updated, restored): ' || (r->0->>'status') || ', deleted=' || ((r->0->'row'->>'deleted_at') is not null) || E'\n';

  r := public.fk_sync_push('pins', jsonb_build_array(jsonb_build_object('id',gen_random_uuid(),'deleted_at','2026-11-19T15:00:00Z')));
  rep := rep || '6 delete of a never-synced row (unchanged): ' || (r->0->>'status') || E'\n';

  r := public.fk_sync_pull('assets', null, null, 500);
  cur_ts := r->-1->>'updated_at'; cur_id := r->-1->>'id';
  rep := rep || '7a pull from start (1): ' || jsonb_array_length(r) || E'\n';
  r := public.fk_sync_pull('assets', cur_ts::timestamptz, cur_id::uuid, 500);
  rep := rep || '7b pull after cursor (0): ' || jsonb_array_length(r) || E'\n';

  r := public.fk_sync_push('pins', jsonb_build_array(
        jsonb_build_object('id',gen_random_uuid(),'kind','nonsense','geom',pt),
        jsonb_build_object('id',gen_random_uuid(),'kind','parking','geom',pt,'mission_id',mid)));
  rep := rep || '8 bad row doesn''t block the batch (error, inserted): ' || (r->0->>'status') || ', ' || (r->1->>'status') || E'\n';

  perform set_config('request.jwt.claims', json_build_object('sub',b,'role','authenticated')::text, true);
  r := public.fk_sync_push('assets', jsonb_build_array(jsonb_build_object('id',sid,'name','hijack','client_updated_at','2026-11-20T00:00:00Z')));
  rep := rep || '9a other user pushes onto the row (rejected): ' || (r->0->>'status') || E'\n';
  r := public.fk_sync_pull('assets', null, null, 500);
  rep := rep || '9b other user pulls (0): ' || jsonb_array_length(r) || E'\n';

  raise exception E'SYNC TEST REPORT (all rolled back)\n%', rep;
end $$;
