-- Approve two basemaps for mission packages (approved 2026-11-18; see docs/export.md).
-- USGS The National Map cached basemaps: US Government work, USGS states no use restrictions
-- on TNM map services; credit requested. Cached to zoom 16; tiles are JPEG.
-- avg_tile_bytes = 90th percentile of tiles sampled at z10-16 around Redding, CA (errs high).
insert into public.export_tile_sources
  (id, name, url_template, tile_format, min_zoom, max_zoom, avg_tile_bytes, attribution, license, approved_by)
values
  ('usgs_topo', 'USGS Topo',
   'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
   'jpeg', 0, 16, 28000,
   'USGS The National Map',
   'US Government work; no use restrictions on The National Map services (credit: "Map services and data available from U.S. Geological Survey, National Geospatial Program")',
   'FieldKey owner'),
  ('usgs_imagery', 'USGS Imagery',
   'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}',
   'jpeg', 0, 16, 36000,
   'USGS The National Map: Orthoimagery (USDA NAIP)',
   'US Government work; no use restrictions on The National Map services (credit: "Map services and data available from U.S. Geological Survey, National Geospatial Program")',
   'FieldKey owner')
on conflict (id) do nothing;
