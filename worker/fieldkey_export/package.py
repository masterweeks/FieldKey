"""Write a FieldKey mission package: a GeoPackage with the mission's vector layers,
an info table, QGIS default styles and (optionally) basemap tile tables.

Only GDAL/OGR and the standard library are used, so it runs in the osgeo/gdal image
and in the Python that ships with QGIS.
"""
import datetime as dt
import json
import re
import sqlite3

from osgeo import ogr, osr

from . import tiles as T

ogr.UseExceptions()
osr.UseExceptions()

# Columns written for each layer: (column, kind). kind: text, int, bool, datetime, json.
# "contact" columns are left out unless the job asks for names and phone numbers.
CONTACT_COLUMNS = {"assets": {"name", "phones"}}

LAYERS = [
    ("missions", ogr.wkbMultiPolygon, "Missions", [
        ("id", "text"), ("name", "text"), ("source_file", "text"), ("status", "text"), ("notes", "text"),
        ("created_at", "datetime"), ("updated_at", "datetime")]),
    ("circuits", ogr.wkbMultiPolygon, "Circuits", [
        ("id", "text"), ("name", "text"), ("code", "text"), ("notes", "text"), ("updated_at", "datetime")]),
    ("assets", ogr.wkbPoint, "Sites", [
        ("id", "text"), ("mission_id", "text"), ("circuit_id", "text"), ("sap_id", "text"), ("name", "text"),
        ("address", "text"), ("phones", "json"), ("access", "text"), ("access_notes", "text"), ("status", "text"),
        ("text_count", "int"), ("last_texted_at", "datetime"), ("scheduled_at", "datetime"), ("notes", "text"),
        ("access_issue", "bool"), ("access_issue_reason", "text"), ("extra", "json"), ("updated_at", "datetime")]),
    ("pins", ogr.wkbPoint, "Pins", [
        ("id", "text"), ("mission_id", "text"), ("asset_id", "text"), ("kind", "text"), ("label", "text"),
        ("notes", "text"), ("updated_at", "datetime")]),
    ("inspections", ogr.wkbPoint, "Inspections", [
        ("id", "text"), ("mission_id", "text"), ("asset_id", "text"), ("inspected_at", "datetime"),
        ("outcome", "text"), ("notes", "text"), ("updated_at", "datetime")]),
    ("photos", ogr.wkbPoint, "Photos (metadata; files stay in FieldKey storage)", [
        ("id", "text"), ("mission_id", "text"), ("asset_id", "text"), ("pin_id", "text"), ("inspection_id", "text"),
        ("storage_path", "text"), ("mime_type", "text"), ("taken_at", "datetime"), ("caption", "text"),
        ("updated_at", "datetime")]),
]
LAYER_NAMES = [l[0] for l in LAYERS]


def columns_for(layer, include_contacts):
    for name, _gt, _desc, cols in LAYERS:
        if name == layer:
            hide = set() if include_contacts else CONTACT_COLUMNS.get(layer, set())
            return [c for c in cols if c[0] not in hide]
    raise KeyError(layer)


def _ogr_field(col, kind):
    if kind == "int":
        return ogr.FieldDefn(col, ogr.OFTInteger)
    if kind == "bool":
        f = ogr.FieldDefn(col, ogr.OFTInteger)
        f.SetSubType(ogr.OFSTBoolean)
        return f
    if kind == "datetime":
        return ogr.FieldDefn(col, ogr.OFTDateTime)
    f = ogr.FieldDefn(col, ogr.OFTString)
    if kind == "json":
        f.SetSubType(ogr.OFSTJSON)
    return f


def _set(feat, i, kind, v):
    if v is None:
        feat.SetFieldNull(i)
    elif kind == "datetime":
        if isinstance(v, str):
            v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc)
        feat.SetField(i, v.year, v.month, v.day, v.hour, v.minute, v.second + v.microsecond / 1e6, 100)
    elif kind == "json":
        feat.SetField(i, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    elif kind == "bool":
        feat.SetField(i, 1 if v else 0)
    elif kind == "int":
        feat.SetField(i, int(v))
    else:
        feat.SetField(i, str(v))


def write_vectors(path, data, include_contacts, epsg=4326):
    """data: {layer: [row dict with column values and 'geom_wkb' (bytes or None)]}. Returns feature count.

    Geometry comes from the database in EPSG:4326. Packages with basemap tiles are written in
    EPSG:3857 instead: QGIS gives a GeoPackage's tile layers the CRS of its vector layers, so
    mixing 4326 vectors with 3857 tiles puts the basemap in the wrong place."""
    drv = ogr.GetDriverByName("GPKG")
    ds = drv.CreateDataSource(path)
    src = osr.SpatialReference()
    src.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_out = None if epsg == 4326 else osr.CoordinateTransformation(src, srs)
    count = 0
    try:
        for name, gtype, desc, _cols in LAYERS:
            rows = data.get(name) or []
            cols = columns_for(name, include_contacts)
            lyr = ds.CreateLayer(name, srs, gtype, options=[
                "GEOMETRY_NAME=geom", "FID=fid", "SPATIAL_INDEX=YES", "IDENTIFIER=" + desc.split(" (")[0],
                "DESCRIPTION=" + desc])
            for col, kind in cols:
                lyr.CreateField(_ogr_field(col, kind))
            defn = lyr.GetLayerDefn()
            lyr.StartTransaction()
            for r in rows:
                feat = ogr.Feature(defn)
                for i, (col, kind) in enumerate(cols):
                    _set(feat, i, kind, r.get(col))
                wkb = r.get("geom_wkb")
                if wkb:
                    g = ogr.CreateGeometryFromWkb(bytes(wkb))
                    if gtype == ogr.wkbMultiPolygon and g.GetGeometryType() == ogr.wkbPolygon:
                        g = ogr.ForceToMultiPolygon(g)
                    if to_out is not None:
                        g.Transform(to_out)
                    feat.SetGeometry(g)
                lyr.CreateFeature(feat)
                count += 1
            lyr.CommitTransaction()
    finally:
        ds = None
    return count


def write_info(path, info):
    """A small attribute table with what's in the package and the basemap credits."""
    ds = ogr.Open(path, 1)
    try:
        lyr = ds.CreateLayer("package_info", None, ogr.wkbNone, options=["IDENTIFIER=Package info",
                                                                         "DESCRIPTION=FieldKey mission package"])
        lyr.CreateField(ogr.FieldDefn("key", ogr.OFTString))
        lyr.CreateField(ogr.FieldDefn("value", ogr.OFTString))
        for k, v in info:
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetField("key", k)
            f.SetField("value", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            lyr.CreateFeature(f)
    finally:
        ds = None


_ACTIONS = re.compile(r"<attributeactions\b.*?</attributeactions>|<attributeactions\b[^>]*/>", re.S)
_LABEL_NAME = re.compile(r'coalesce\((&quot;|")sap_id\1,\s*(&quot;|")name\2\)')


def adapt_style(qml, include_contacts):
    """Make a style saved for the database fit the package: no database actions, and
    labels that don't depend on columns that were left out."""
    qml = _ACTIONS.sub("<attributeactions/>", qml)
    if not include_contacts:
        qml = _LABEL_NAME.sub(lambda m: m.group(1) + "sap_id" + m.group(1), qml)
    return qml


def write_styles(path, styles, include_contacts):
    """styles: [(layer, stylename, qml, sld)]. Stored the way QGIS stores GeoPackage styles,
    so QGIS applies them automatically when the layer is added."""
    if not styles:
        return
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
            f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
            styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
            update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
        con.execute("""INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier, description, last_change)
                       VALUES ('layer_styles', 'attributes', 'layer_styles', 'QGIS layer styles',
                               strftime('%Y-%m-%dT%H:%M:%fZ','now'))""")
        for layer, name, qml, sld in styles:
            con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column,
                           styleName, styleQML, styleSLD, useAsDefault, description, owner)
                           VALUES ('', '', ?, 'geom', ?, ?, ?, 1, 'FieldKey default', 'fieldkey')""",
                        (layer, name or layer, adapt_style(qml or "", include_contacts), sld or ""))
        con.commit()
    finally:
        con.close()


def _ensure_3857(con):
    if con.execute("SELECT 1 FROM gpkg_spatial_ref_sys WHERE srs_id = 3857").fetchone():
        return
    s = osr.SpatialReference()
    s.ImportFromEPSG(3857)
    con.execute("""INSERT INTO gpkg_spatial_ref_sys (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
                   VALUES ('WGS 84 / Pseudo-Mercator', 3857, 'EPSG', 3857, ?, 'Web Mercator')""", (s.ExportToWkt(),))


class TileTable:
    """A GeoPackage tile pyramid in the GoogleMapsCompatible grid (EPSG:3857, 256 px tiles).
    Tiles are stored exactly as downloaded (PNG or JPEG), so nothing is re-encoded."""

    def __init__(self, path, table, identifier, description, area_bbox, min_zoom, max_zoom):
        self.con = sqlite3.connect(path)
        self.table = table
        con = self.con
        _ensure_3857(con)
        q = '"' + table.replace('"', '') + '"'
        con.execute(f"""CREATE TABLE {q} (id INTEGER PRIMARY KEY AUTOINCREMENT, zoom_level INTEGER NOT NULL,
                        tile_column INTEGER NOT NULL, tile_row INTEGER NOT NULL, tile_data BLOB NOT NULL,
                        UNIQUE (zoom_level, tile_column, tile_row))""")
        x0, y0, x1, y1 = T.bbox_to_3857(area_bbox)
        con.execute("""INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change,
                       min_x, min_y, max_x, max_y, srs_id)
                       VALUES (?, 'tiles', ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?, ?, 3857)""",
                    (table, identifier, description, x0, y0, x1, y1))
        W = T.WORLD
        con.execute("INSERT INTO gpkg_tile_matrix_set (table_name, srs_id, min_x, min_y, max_x, max_y) VALUES (?, 3857, ?, ?, ?, ?)",
                    (table, -W, -W, W, W))
        for z in range(min_zoom, max_zoom + 1):
            n = 1 << z
            px = 2 * W / (256 * n)
            con.execute("""INSERT INTO gpkg_tile_matrix (table_name, zoom_level, matrix_width, matrix_height,
                           tile_width, tile_height, pixel_x_size, pixel_y_size) VALUES (?, ?, ?, ?, 256, 256, ?, ?)""",
                        (table, z, n, n, px, px))
        con.commit()
        self.q = q
        self.pending = 0

    def put(self, z, x, y, data):
        # GeoPackage tile_row counts from the top, same as XYZ "y"
        self.con.execute(f"INSERT OR REPLACE INTO {self.q} (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                         (z, x, y, sqlite3.Binary(data)))
        self.pending += 1
        if self.pending >= 200:
            self.con.commit()
            self.pending = 0

    def close(self):
        self.con.commit()
        self.con.close()


def looks_like_image(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
