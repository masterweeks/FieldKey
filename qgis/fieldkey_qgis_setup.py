"""FieldKey QGIS project setup.

Run inside QGIS (3.30 or later):
  1. Fill in HOST and AUTHCFG below (see docs/qgis-setup.md).
  2. Plugins -> Python Console -> Show Editor -> Open Script... -> this file -> Run Script.

It adds the FieldKey layers from Supabase PostGIS (session pooler, SSL required), styles
them, sets up the attribute forms, saves each layer's style into the database as its
default (public.layer_styles), and saves the whole project into Postgres
(schema qgis, project "FieldKey") so anyone can open it with Project -> Open From ->
PostgreSQL. Running it again rebuilds the FieldKey group and saves again.

It also adds what FieldKey's map shows around the data, read live from the same online
sources: the five basemaps (Dark, Aerial, Hybrid, Streets, Topo), the terrain behind 3D
views, FAA airspace with TFRs, wildfires and fire weather, hospitals and protected areas.
Set ADD_REFERENCE_LAYERS = False to leave them out.

No passwords live in this file: AUTHCFG is the id of a QGIS authentication configuration
that holds the qgis_editor login, stored in QGIS's encrypted password database.
"""
import json
import re

from qgis.core import (
    Qgis, QgsAction, QgsActionManager, QgsBilinearRasterResampler, QgsBlockingNetworkRequest,
    QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDataSourceUri,
    QgsDefaultValue, QgsEditorWidgetSetup, QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsHillshadeRenderer,
    QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsProject, QgsProperty, QgsRasterDemTerrainProvider,
    QgsRasterLayer, QgsRectangle, QgsReferencedRectangle, QgsRendererCategory, QgsRendererRange,
    QgsSingleSymbolRenderer, QgsSymbolLayer,
    QgsTextFormat, QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsVectorTileBasicLabeling,
    QgsVectorTileBasicLabelingStyle, QgsVectorTileBasicRenderer, QgsVectorTileBasicRendererStyle,
    QgsVectorTileLayer, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.PyQt.QtNetwork import QNetworkRequest

# ---------------------------------------------------------------- connection (edit these)
PROJECT_REF = "fdclbfqgsookhxfboxpn"
HOST = "aws-1-us-east-2.pooler.supabase.com"   # Dashboard -> Connect -> Session pooler -> host, e.g. aws-1-us-east-2.pooler.supabase.com
PORT = "5432"                                  # session pooler port
DBNAME = "postgres"
AUTHCFG = "g12a680"                            # QGIS auth config id (7 characters), e.g. "fk3dqgs"
SAVE_PROJECT_TO_DB = True
PROJECT_NAME = "FieldKey"
GROUP_NAME = "FieldKey"

# ---------------------------------------------------------------- what the forms show
SYSTEM_READ_ONLY = ["id", "created_at", "created_by", "updated_at", "updated_by", "client_updated_at", "legacy_id"]
HIDDEN = ["deleted_at"]

ASSET_STATUS = [  # value, label, colour (same colours as FieldKey's pins)
    ("new", "New", "#9aa4b0"), ("enriched", "New (details added)", "#b8c0ca"), ("texted", "Texted", "#FFB000"),
    ("replied", "Replied", "#5AA9FF"), ("scheduled", "Scheduled", "#41D88B"), ("done", "Done", "#5E6775"),
]
ISSUE_COLOUR = "#FF4D4D"   # FieldKey's access-issue pin colour
# as on FieldKey's map, an access issue shows as its own status, whatever the site's status is
ASSET_STYLE_KEY = "CASE WHEN \"access_issue\" THEN 'issue' ELSE \"status\" END"
PIN_KINDS = [("entrance", "Entrance / path", "#C084FC"), ("parking", "Parking", "#1E63FF"),
             ("hazard", "Hazard", "#FF4D4D"), ("note", "Note", "#3FB6A8")]
MISSION_STATUS = [("planned", "Planned"), ("active", "Active"), ("complete", "Complete"), ("archived", "Archived")]
INSPECTION_OUTCOME = [("planned", "Planned"), ("completed", "Completed"), ("partial", "Partial"),
                      ("no_access", "No access"), ("cancelled", "Cancelled")]

ALIASES = {
    "id": "ID", "owner_id": "Owner", "mission_id": "Mission", "circuit_id": "Circuit", "asset_id": "Asset",
    "pin_id": "Pin", "inspection_id": "Inspection", "sap_id": "SAP ID", "name": "Name", "address": "Address",
    "phones": "Phones", "access": "Access", "access_notes": "Access notes", "status": "Status",
    "text_count": "Texts sent", "last_texted_at": "Last texted", "scheduled_at": "Scheduled for", "notes": "Notes",
    "access_issue": "Access issue", "access_issue_reason": "Access issue reason", "extra": "Other columns",
    "kind": "Kind", "label": "Label", "inspected_at": "Inspected at", "outcome": "Outcome",
    "storage_path": "Photo", "mime_type": "File type", "taken_at": "Taken at", "caption": "Caption",
    "code": "Code", "source_file": "Source file", "created_at": "Created", "created_by": "Created by",
    "updated_at": "Updated", "updated_by": "Updated by", "client_updated_at": "Edited on device",
    "legacy_id": "FieldKey ID", "deleted_at": "Deleted",
}

# table, layer name, geometry
LAYERS = [
    ("missions", "Missions", "MultiPolygon"),
    ("circuits", "Circuits", "MultiPolygon"),
    ("inspections", "Inspections", "Point"),
    ("photos", "Photos", "Point"),
    ("pins", "Pins", "Point"),
    ("assets", "Assets", "Point"),
]
PARENT_LAYERS = {"mission_id": ("Missions", "name"), "circuit_id": ("Circuits", "name"),
                 "asset_id": ("Assets", "sap_id"), "pin_id": ("Pins", "label"), "inspection_id": ("Inspections", "inspected_at")}

# ---------------------------------------------------------------- reference layers (same sources as FieldKey)
ADD_REFERENCE_LAYERS = True
DEFAULT_BASEMAP = "Dark"          # Dark, Aerial, Hybrid, Streets or Topo
BASEMAP_GROUP = "Basemaps"
AIRSPACE_GROUP = "Airspace"
PROTECTED_LAYER = "Protected areas"
REF_TAG = "fieldkey/reference"    # marks what this script added, so a re-run replaces it
PX = 0.26                         # one screen pixel in millimetres (FieldKey's line widths are in pixels)

OFM_TILEJSON = "https://tiles.openfreemap.org/planet"
OFM_DARK_STYLE = "https://tiles.openfreemap.org/styles/dark"
OFM_OFFLINE_TILES = "https://tiles.openfreemap.org/planet/offline/{z}/{x}/{y}.pbf"   # tests only
OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USGS_TOPO = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}"
USGS_IMAGERY = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
NAIP_SERVICE = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer"
NAIP_FROM_SCALE = 7000            # USGS imagery tiles stop at zoom 16 (about 1:8,500); NAIP takes over closer in
DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
DEM_ZMAX = 15
RELIEF_TO_SCALE = 12000

FAA = "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
WFIGS = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"    # NIFC current wildfires (public domain)
HOSPITALS = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/Hospitals_RAPT/FeatureServer/6"   # FEMA copy of HIFLD
RELAY = "https://%s.supabase.co/functions/v1/tfr" % PROJECT_REF     # FieldKey's relay: FAA TFRs and NWS fire-weather zones
HOSPITAL_TYPES = ("GENERAL ACUTE CARE", "CRITICAL ACCESS", "CHILDREN", "MILITARY")   # the kinds that may treat an injury
# key: service, its CRS, filter (the one FieldKey uses), and the scale beyond which it hides
OVERLAYS = {
    # B/C/D and surface-area E only: Class A and E with a 700 ft+ floor sit above drone altitudes
    "class": (FAA + "Class_Airspace/FeatureServer/0", "EPSG:4326",
              "CLASS IN ('B','C','D') OR LOCAL_TYPE IN ('CLASS_E2','CLASS_E3','CLASS_E4')", 2500000),
    "sua": (FAA + "Special_Use_Airspace/FeatureServer/0", "EPSG:4326", "", 5000000),
    "nsr": (FAA + "DoD_Mar_13/FeatureServer/0", "EPSG:4326", "", 2500000),
    "nsrpt": (FAA + "Part_Time_National_Security_UAS_Flight_Restrictions/FeatureServer/0", "EPSG:4326", "", 2500000),
    "uasfm": (FAA + "FAA_UAS_FacilityMap_Data/FeatureServer/0", "EPSG:4326", "", 150000),
    # GeoJSON from the relay; its first shape is a blank placeholder so the layer keeps its type when nothing is active
    "tfr": (RELAY + "?bbox=-180,15,-60,72&qgis=1", "EPSG:4326", '"placeholder" IS NULL', 10000000),
    "rfw": (RELAY + "?fire=1&qgis=1", "EPSG:4326", '"placeholder" IS NULL', 10000000),
    "fireper": (WFIGS + "WFIGS_Interagency_Perimeters_Current/FeatureServer/0", "EPSG:4326", "attr_IncidentTypeCategory = 'WF'", 10000000),
    "fire": (WFIGS + "WFIGS_Incident_Locations_Current/FeatureServer/0", "EPSG:4326", "IncidentTypeCategory = 'WF'", 10000000),
    "hosp": (HOSPITALS, "EPSG:3857", "STATUS = 'OPEN' AND TYPE IN (%s)" % ",".join("'%s'" % t for t in HOSPITAL_TYPES), 1000000),
    "env": ("https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/Manager_Name_PADUS/FeatureServer/0", "EPSG:3857",
            "Mang_Name IN ('NPS','FWS') OR Des_Tp IN ('NWR','WPA','WA','WSA','MPA') OR "
            "(Mang_Type='STAT' AND (Mang_Name IN ('SPR','SFW') OR Des_Tp IN ('SP','SREC','SW')))", 1000000),
}
AIRSPACE_LAYERS = [   # top of the group first; the LAANC grid sits lowest
    ("tfr", "TFRs"), ("nsr", "National security restrictions"), ("nsrpt", "Part-time national security restrictions"),
    ("class", "Controlled airspace"), ("sua", "Special use airspace"), ("uasfm", "LAANC grid"),
]
FIRE_GROUP = "Wildfire"
FIRE_LAYERS = [("fire", "Wildfires"), ("fireper", "Fire perimeters"), ("rfw", "Red Flag Warnings and Fire Weather Watches")]
HOSPITAL_LAYER = "Hospitals"
LIVE = ("tfr", "rfw", "fire", "fireper")   # these change through the day: reloaded every LIVE_MINUTES
LIVE_MINUTES = 10
TFR_COLOUR, FIRE_COLOUR, HOSPITAL_COLOUR = "#FF2D55", "#FF5A1F", "#E03131"
FIRE_WEATHER = [("Red Flag Warning", "#FF1744", "Critical fire weather now: a spark can start a fast-moving fire."),
                ("Fire Weather Watch", "#FF9100", "Critical fire weather is possible soon.")]
AIR_CLASSES = [("B", "Class B", "#3B7BFF"), ("C", "Class C", "#D6336C"), ("D", "Class D", "#4DABF7"),
               ("E", "Class E surface area", "#E64980")]
SPECIAL_USE = [   # code, label, colour, drone rule; the empty code catches every other type
    ("P", "Prohibited area", "#FF3B3B", "No flight of any kind."),
    ("R", "Restricted area", "#FF6B6B", "Don't fly while it's active without the controlling agency's approval."),
    ("MOA", "Military Operations Area", "#B197FC", "Drones may fly, but expect fast, low military aircraft."),
    ("W", "Warning area", "#FFA94D", "Offshore military hazard area."),
    ("A", "Alert area", "#FFA94D", "High volume of pilot training or unusual aerial activity."),
    ("D", "Danger area", "#FFA94D", "Hazardous activity area."),
    ("", "Other special use airspace", "#FFA94D", ""),
]
LAANC_CEILINGS = [(0, 49.9, "0 ft (no automatic approval)", "#FA5252"), (50, 149.9, "50-100 ft", "#FD7E14"),
                  (150, 249.9, "150-200 ft", "#FCC419"), (250, 349.9, "250-300 ft", "#94D82D"),
                  (350, 100000, "350-400 ft", "#40C057")]
PROTECTED_CATEGORY = ("CASE WHEN \"Des_Tp\" IN ('WA','WSA') THEN 'wild' "
                      "WHEN \"Mang_Name\" = 'FWS' OR \"Des_Tp\" IN ('NWR','WPA') THEN 'fws' "
                      "WHEN \"Mang_Name\" = 'NPS' THEN 'nps' WHEN \"Des_Tp\" = 'MPA' THEN 'mpa' "
                      "WHEN \"Mang_Name\" = 'SFW' THEN 'stwild' ELSE 'stpark' END")
PROTECTED = [   # category, label, colour, drone rule
    ("nps", "National Park Service", "#F08C00",
     "Launching, landing or operating a drone is prohibited without the superintendent's approval."),
    ("fws", "National Wildlife Refuge", "#2FB344",
     "Drone takeoff and landing is prohibited on refuges (50 CFR 27.34) without a special use permit."),
    ("wild", "Wilderness", "#12B886", "No drone takeoff or landing inside wilderness."),
    ("stpark", "State park / recreation area", "#C0EB75",
     "Drone rules vary by state; many state parks ban drones or require a permit."),
    ("stwild", "State fish & wildlife area", "#82C91E", "Many state wildlife areas prohibit drones. Check with the managing agency."),
    ("mpa", "Marine protected area", "#22B8CF", "Some marine protected areas restrict low overflight. Check before flying."),
]
# Hybrid roads: name, OpenMapTiles classes, colour, then edge and fill widths in pixels at zoom 11, 16 and 19
HYBRID_ROADS = [
    ("highways", ("motorway", "trunk"), "#FFD24D", (5, 16, 30), (2.6, 10, 20)),
    ("main roads", ("primary", "secondary"), "#FFE9A6", (4, 13, 24), (2, 8, 16)),
    ("streets", ("tertiary", "minor", "residential", "unclassified"), "#FFFFFF", (2.5, 9, 18), (1.2, 5.5, 12)),
    ("lanes and tracks", ("service", "living_street", "road", "track"), "#FFFFFF", (2.5, 6, 13), (1.2, 3.5, 8)),
]

SOFT_DELETE_ACTION = """
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QDateTime
lyr = QgsProject.instance().mapLayer('[% @layer_id %]')
fid = [% $id %]
idx = lyr.fields().indexOf('deleted_at')
was_editing = lyr.isEditable()
if not was_editing:
    lyr.startEditing()
lyr.changeAttributeValue(fid, idx, QDateTime.currentDateTimeUtc())
if not was_editing:
    lyr.commitChanges()
lyr.reload()
"""


# ---------------------------------------------------------------- helpers
def value_map(pairs):
    return QgsEditorWidgetSetup("ValueMap", {"map": [{label: value} for value, label, *_ in pairs]})


def date_time():
    return QgsEditorWidgetSetup("DateTime", {"field_format": "yyyy-MM-ddTHH:mm:ss", "display_format": "yyyy-MM-dd HH:mm",
                                             "calendar_popup": True, "allow_null": True})


def postgres_layer(table, name):
    uri = QgsDataSourceUri()
    uri.setConnection(HOST, PORT, DBNAME, "", "", QgsDataSourceUri.SslRequire, AUTHCFG)
    uri.setDataSource("public", table, "geom", "deleted_at IS NULL", "id")
    return QgsVectorLayer(uri.uri(False), name, "postgres")


def configure_layer(layer, table, layers_by_name):
    """Aliases, widgets, read-only and hidden fields, defaults, style, labels, action."""
    fields = layer.fields()
    form = layer.editFormConfig()

    for f in fields:
        name, i = f.name(), fields.indexOf(f.name())
        if name in ALIASES:
            layer.setFieldAlias(i, ALIASES[name])
        if name in SYSTEM_READ_ONLY:
            form.setReadOnly(i, True)
        if name in HIDDEN:
            layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup("Hidden", {}))
        if name in ("created_at", "updated_at", "client_updated_at", "last_texted_at", "scheduled_at",
                    "inspected_at", "taken_at"):
            layer.setEditorWidgetSetup(i, date_time())
        if name in ("phones", "extra"):
            layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup("JsonEdit", {}))
            form.setReadOnly(i, True)   # edited in FieldKey; raw JSON in a form is easy to break
        if name in PARENT_LAYERS and PARENT_LAYERS[name][0] in layers_by_name and PARENT_LAYERS[name][0] != layer.name():
            parent, shown = PARENT_LAYERS[name]
            pl = layers_by_name[parent]
            layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup("ValueRelation", {
                "Layer": pl.id(), "LayerName": pl.name(), "LayerSource": pl.source(), "LayerProviderName": pl.providerType(),
                "Key": "id", "Value": shown, "AllowNull": True, "OrderByValue": True, "AllowMulti": False,
                "UseCompleter": False, "NofColumns": 1}))

    # owner: hidden. Child features take their mission's owner (the server checks it matches);
    # a mission takes the owner of the existing missions unless you type another user's id.
    oi = fields.indexOf("owner_id")
    if oi >= 0:
        layer.setEditorWidgetSetup(oi, QgsEditorWidgetSetup("Hidden", {}))
        if table == "missions":
            expr = "coalesce(\"owner_id\", aggregate(layer:='Missions', aggregate:='max', expression:=\"owner_id\"))"
        elif fields.indexOf("mission_id") >= 0:
            expr = "coalesce(\"owner_id\", attribute(get_feature('Missions', 'id', \"mission_id\"), 'owner_id'))"
        else:
            expr = ""
        if expr:
            layer.setDefaultValueDefinition(oi, QgsDefaultValue(expr, True))

    # table-specific widgets and style
    if table == "assets":
        layer.setEditorWidgetSetup(fields.indexOf("status"), value_map(ASSET_STATUS))
        layer.setEditorWidgetSetup(fields.indexOf("access_issue"), QgsEditorWidgetSetup("CheckBox", {}))
        cats = []
        for value, label, colour in ASSET_STATUS + [("issue", "Access issue", ISSUE_COLOUR)]:
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "size": "3.4",
                                                "outline_color": "#0E1116", "outline_width": "0.4"})
            cats.append(QgsRendererCategory(value, sym, label))
        layer.setRenderer(QgsCategorizedSymbolRenderer(ASSET_STYLE_KEY, cats))
        set_labels(layer, "coalesce(\"sap_id\", \"name\")", 10000)
    elif table == "pins":
        layer.setEditorWidgetSetup(fields.indexOf("kind"), value_map(PIN_KINDS))
        cats = [QgsRendererCategory(value, QgsMarkerSymbol.createSimple(
                    {"name": "diamond", "color": colour, "size": "3.6", "outline_color": "#ffffff", "outline_width": "0.3"}), label)
                for value, label, colour in PIN_KINDS]
        layer.setRenderer(QgsCategorizedSymbolRenderer("kind", cats))
        set_labels(layer, "\"label\"", 5000)
    elif table == "missions":
        layer.setEditorWidgetSetup(fields.indexOf("status"), value_map([(v, l) for v, l in MISSION_STATUS]))
        layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "255,176,0,25", "outline_color": "#FFB000", "outline_width": "0.6"})))
        set_labels(layer, "\"name\"", 250000)
    elif table == "circuits":
        layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "90,169,255,20", "outline_color": "#5AA9FF", "outline_width": "0.5", "outline_style": "dash"})))
        set_labels(layer, "coalesce(\"code\", \"name\")", 250000)
    elif table == "inspections":
        layer.setEditorWidgetSetup(fields.indexOf("outcome"), value_map([(v, l) for v, l in INSPECTION_OUTCOME]))
        layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "square", "color": "#41D88B", "size": "2.6", "outline_color": "#0E1116"})))
    elif table == "photos":
        # Attachment widget showing the image; see docs/qgis-setup.md to point it at the
        # private bucket (Storage type AWS S3 + the Supabase S3 credentials).
        layer.setEditorWidgetSetup(fields.indexOf("storage_path"), QgsEditorWidgetSetup("ExternalResource", {
            "DocumentViewer": 1, "DocumentViewerHeight": 320, "FileWidget": True, "FileWidgetButton": True,
            "UseLink": True, "FullUrl": True}))
        layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "triangle", "color": "#ffffff", "size": "2.8", "outline_color": "#0E1116"})))

    layer.setEditFormConfig(form)

    # Deleting is off for everyone (soft deletes only), so give a one-click "hide" instead.
    am = layer.actions()
    for a in list(am.actions()):
        if a.name() == "Soft delete (hide this feature)":
            am.removeAction(a.id())
    act = QgsAction(QgsAction.ActionType.GenericPython, "Soft delete (hide this feature)", SOFT_DELETE_ACTION, "", False,
                    "Soft delete", {"Feature", "Canvas"})
    am.addAction(act)


def set_labels(layer, expression, max_scale):
    s = QgsPalLayerSettings()
    s.fieldName = expression
    s.isExpression = True
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 8))
    fmt.setSize(8)
    fmt.setColor(QColor("#1b1f26"))
    buf = fmt.buffer()
    buf.setEnabled(True)
    buf.setColor(QColor("#ffffff"))
    buf.setSize(0.8)
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    s.scaleVisibility = True
    s.maximumScale = 0           # no limit when zoomed in
    s.minimumScale = max_scale   # hidden when zoomed out beyond this
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)


def save_style_to_db(layer):
    """Make this style the layer's default in public.layer_styles (also used by GeoPackage exports)."""
    try:
        return layer.saveStyleToDatabaseV2("FieldKey", "FieldKey default style", True, "")
    except AttributeError:
        return layer.saveStyleToDatabase("FieldKey", "FieldKey default style", True, "")


# ---------------------------------------------------------------- reference layers
def _tag(node_or_layer, key):
    node_or_layer.setCustomProperty(REF_TAG, key)
    return node_or_layer


def xyz_layer(url, name, zmax, extra=""):
    return QgsRasterLayer(f"type=xyz&url={url}&zmax={zmax}&zmin=0{extra}", name, "wms")


def http_json(url):
    """GET a small JSON document through QGIS's network settings (proxy, timeouts). None if it fails."""
    req = QgsBlockingNetworkRequest()
    if req.get(QNetworkRequest(QUrl(url))) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        return None
    try:
        return json.loads(bytes(req.reply().content()).decode("utf-8"))
    except ValueError:
        return None


def openfreemap_tiles():
    """OpenFreeMap puts a build date in its tile address, so ask for the current one."""
    tiles = (http_json(OFM_TILEJSON) or {}).get("tiles") or []
    return tiles[0] if tiles else None


def vector_tiles(tile_url, name, style_url=""):
    return QgsVectorTileLayer(f"type=xyz&url={tile_url}&zmax=14&zmin=0" + (f"&styleUrl={style_url}" if style_url else ""), name)


def _without_geometry_tests(styles):
    """The Dark style tests each feature's geometry type in a way QGIS converts to an empty
    field name ("" IN ('Polygon', ...)), which is never true, so roads, water and names vanish.
    Every QGIS style is already tied to one geometry type, so the test can simply go."""
    for st in styles:
        if '"" IN (' in st.filterExpression():
            st.setFilterExpression(re.sub(r'"" IN \([^)]*\)', "TRUE", st.filterExpression()))
    return styles


LABEL_REPEAT_MM = 30   # the same name drawn again within this distance on screen is left out


def _no_duplicate_labels(styles):
    """Vector tiles repeat a town near a tile edge in each neighbouring tile, and QGIS would draw every copy
    side by side ("Healdsburg Healdsburg"). Drop a name when the same one is already drawn close by."""
    for st in styles:
        s = st.labelSettings()
        thin = s.thinningSettings()
        thin.setAllowDuplicateRemoval(True)
        thin.setMinimumDistanceToDuplicate(LABEL_REPEAT_MM)
        thin.setMinimumDistanceToDuplicateUnit(Qgis.RenderUnit.Millimeters)
        s.setThinningSettings(thin)
        st.setLabelSettings(s)
    return styles


def dark_layer(tile_url, name="Dark map"):
    lyr = vector_tiles(tile_url, name, OFM_DARK_STYLE)
    if lyr.isValid():
        lyr.loadDefaultStyle()      # FieldKey's Dark style, converted for QGIS
        renderer, labeling = lyr.renderer().clone(), lyr.labeling().clone() if lyr.labeling() else None
        renderer.setStyles(_without_geometry_tests(renderer.styles()))
        lyr.setRenderer(renderer)
        if labeling:
            labeling.setStyles(_no_duplicate_labels(_without_geometry_tests(labeling.styles())))
            lyr.setLabeling(labeling)
    return lyr


def _zoom_mm(w11, w16, w19):
    """FieldKey's road widths (pixels at zoom 11, 16 and 19, growing 1.4x a zoom level), in millimetres."""
    z = "@vector_tile_zoom"
    return (f"{PX} * CASE WHEN {z} <= 11 THEN {w11} "
            f"WHEN {z} <= 16 THEN {w11} + ({w16} - {w11}) * (1.4^({z} - 11) - 1) / (1.4^5 - 1) "
            f"WHEN {z} < 19 THEN {w16} + ({w19} - {w16}) * (1.4^({z} - 16) - 1) / (1.4^3 - 1) "
            f"ELSE {w19} END")


def _halo_text(size):
    fmt = QgsTextFormat()
    font = QFont("Arial", size)
    font.setBold(True)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor("#ffffff"))
    buf = fmt.buffer()
    buf.setEnabled(True)
    buf.setColor(QColor("#0a0d12"))
    buf.setSize(0.9)
    fmt.setBuffer(buf)
    return fmt


def hybrid_roads_layer(tile_url, name="Roads and names"):
    """Bright roads with a dark edge, and white road and town names, drawn over the aerial."""
    lyr = vector_tiles(tile_url, name)
    if not lyr.isValid():
        return lyr
    styles = []
    for edge in (True, False):          # every dark edge first, then the bright road surfaces on top
        for key, classes, colour, edge_w, fill_w in HYBRID_ROADS:
            sym = QgsLineSymbol.createSimple({"color": "#0a0d12" if edge else colour, "capstyle": "round", "joinstyle": "round"})
            if edge:
                sym.setOpacity(0.85)
            sym.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth,
                                                      QgsProperty.fromExpression(_zoom_mm(*(edge_w if edge else fill_w))))
            st = QgsVectorTileBasicRendererStyle(("edge: " if edge else "road: ") + key, "transportation", QgsWkbTypes.LineGeometry)
            st.setFilterExpression("\"class\" IN (%s)" % ", ".join("'%s'" % c for c in classes))
            st.setSymbol(sym)
            styles.append(st)
    renderer = QgsVectorTileBasicRenderer()
    renderer.setStyles(styles)
    lyr.setRenderer(renderer)

    labels = []
    for st_name, source_layer, geom, size, filt in (
            ("road names", "transportation_name", QgsWkbTypes.LineGeometry, 8, ""),
            ("towns", "place", QgsWkbTypes.PointGeometry, 10, "\"class\" IN ('city', 'town', 'village', 'suburb')")):
        s = QgsPalLayerSettings()
        s.fieldName = "coalesce(\"name:en\", \"name\")"
        s.isExpression = True
        if geom == QgsWkbTypes.LineGeometry:
            s.placement = Qgis.LabelPlacement.Curved
        s.setFormat(_halo_text(size))
        ls = QgsVectorTileBasicLabelingStyle()
        ls.setStyleName(st_name)
        ls.setLayerName(source_layer)
        ls.setGeometryType(geom)
        ls.setFilterExpression(filt)
        ls.setLabelSettings(s)
        labels.append(ls)
    labeling = QgsVectorTileBasicLabeling()
    labeling.setStyles(_no_duplicate_labels(labels))
    lyr.setLabeling(labeling)
    return lyr


def naip_layer(name="Close-ups (NAIP)"):
    lyr = QgsRasterLayer(f"url='{NAIP_SERVICE}' format='JPG' crs='EPSG:3857'", name, "arcgismapserver")
    if lyr.isValid():
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(NAIP_FROM_SCALE)     # only when zoomed in closer than the USGS tiles go
    return lyr


def terrain_layers():
    """The elevation layer behind the 3D view, and a shaded-relief copy for the Dark basemap."""
    dem = xyz_layer(DEM_TILES, "Terrain (elevation)", DEM_ZMAX, "&interpretation=terrariumterrain")
    relief = xyz_layer(DEM_TILES, "Terrain relief", DEM_ZMAX, "&interpretation=terrariumterrain")
    if relief.isValid():
        relief.setRenderer(QgsHillshadeRenderer(relief.dataProvider(), 1, 315, 45))
        relief.resampleFilter().setZoomedInResampler(QgsBilinearRasterResampler())
        relief.setBlendMode(QPainter.CompositionMode_SoftLight)
        relief.setOpacity(0.7)
        relief.setScaleBasedVisibility(True)
        relief.setMaximumScale(RELIEF_TO_SCALE)  # closer in, the elevation grid would show as a weave
    return dem, relief


def set_terrain(project, dem):
    """Make the elevation layer the project's terrain: new 3D map views and elevation profiles use it."""
    try:
        dem.elevationProperties().setEnabled(True)
        dem.elevationProperties().setMode(Qgis.RasterElevationMode.RepresentsElevationSurface)
    except AttributeError:
        pass                                     # older QGIS: the terrain setting below is enough
    provider = QgsRasterDemTerrainProvider()
    provider.setLayer(dem)
    project.elevationProperties().setTerrainProvider(provider)


def feature_service_layer(key, name):
    """One of the FAA or USGS layers FieldKey draws, read live from its ArcGIS feature service."""
    url, crs, where, _scale = OVERLAYS[key]
    if url.startswith(RELAY):     # TFRs and fire-weather zones: GeoJSON read by GDAL straight from the relay
        opts = QgsVectorLayer.LayerOptions()
        opts.forceReadOnly = True                 # a web file can't be edited; this stops GDAL asking to
        lyr = QgsVectorLayer(url, name, "ogr", opts)
    else:
        lyr = QgsVectorLayer(f"crs='{crs}' url='{url}'", name, "arcgisfeatureserver")
    if lyr.isValid() and where:
        lyr.setSubsetString(where)
    return lyr


def _area(colour, fill_opacity, line_px, dashed=False, line_opacity=1.0):
    c = QColor(colour)
    rgb = "%d,%d,%d," % (c.red(), c.green(), c.blue())
    return QgsFillSymbol.createSimple({
        "color": rgb + str(round(fill_opacity * 255)), "outline_color": rgb + str(round(line_opacity * 255)),
        "outline_width": str(round(line_px * PX, 2)), "outline_style": "dash" if dashed else "solid"})


def _rule_cases(test, rows):
    """QGIS expression cases 'WHEN <test> = key THEN label: rule' for a hover tip."""
    return " ".join("WHEN %s = '%s' THEN '%s'" % (test, key, (label + ": " + rule).replace("'", "''"))
                    for key, label, _colour, rule in rows if key)


def style_overlay(layer, key):
    """FieldKey's colours, plus a hover tip with the drone rule (View -> Show Map Tips)."""
    if key == "class":      # sectional-chart style: B and C solid, D and surface E dashed
        cats = [QgsRendererCategory(cls, _area(colour, 0.04 if cls == "E" else 0.07, 2.2 if cls in "BC" else 2, cls not in "BC"), label)
                for cls, label, colour in AIR_CLASSES]
        layer.setRenderer(QgsCategorizedSymbolRenderer("CLASS", cats))
        tip = ("<b>[% \"NAME\" %]</b><br>[% CASE WHEN \"CLASS\" = 'E' THEN 'Class E surface area' ELSE 'Class ' || \"CLASS\" END %]"
               "<br>Drones need FAA authorization (LAANC or DroneZone).")
    elif key == "sua":
        cats = [QgsRendererCategory(code, _area(colour, 0.12 if code in ("P", "R") else 0.05, 2, True), label)
                for code, label, colour, _rule in SPECIAL_USE]
        layer.setRenderer(QgsCategorizedSymbolRenderer("TYPE_CODE", cats))
        tip = ("<b>[% \"NAME\" %]</b><br>[% CASE " + _rule_cases("\"TYPE_CODE\"", SPECIAL_USE)
               + " ELSE 'Special use airspace' END %]<br>[% coalesce(\"TIMESOFUSE\", '') %]")
    elif key in ("nsr", "nsrpt"):
        layer.setRenderer(QgsSingleSymbolRenderer(_area("#FF2D2D", 0.2, 2)))
        tip = ("<b>[% coalesce(\"Facility\", \"Base\", 'National security restriction') %]</b>"
               "<br>No drones: national security flight restriction"
               + (" (part-time: check when it is active)." if key == "nsrpt" else "."))
    elif key == "uasfm":    # LAANC grid: colour by the altitude that can be approved automatically
        ranges = [QgsRendererRange(lo, hi, _area(colour, 0.13, 0.6, line_opacity=0.5), label) for lo, hi, label, colour in LAANC_CEILINGS]
        layer.setRenderer(QgsGraduatedSymbolRenderer("CEILING", ranges))
        set_labels(layer, "to_string(\"CEILING\")", 50000)
        tip = ("<b>LAANC grid: [% \"CEILING\" %] ft AGL</b><br>[% coalesce(\"APT1_NAME\", '') %]"
               "<br>[% CASE WHEN \"CEILING\" = 0 THEN 'No automatic approval here: request authorization through FAA DroneZone.'"
               " ELSE 'Automatic approval up to ' || \"CEILING\" || ' ft AGL through a LAANC provider, if the airport is LAANC-enabled.' END %]")
    elif key == "tfr":
        layer.setRenderer(QgsSingleSymbolRenderer(_area(TFR_COLOUR, 0.16, 2.6, True)))
        tip = ("<b>TFR [% \"id\" %] · [% title(lower(\"type\")) %]</b><br>[% \"title\" %]"
               "<br>No drone flights inside while it's active unless the FAA has approved yours."
               "<br><a href=\"https://tfr.faa.gov/tfr3/?page=detail_[% replace(\"id\", '/', '_') %]\">Times, altitudes and NOTAM text (FAA)</a>")
    elif key == "rfw":
        cats = [QgsRendererCategory(event, _area(colour, 0.1, 1.5, True), event) for event, colour, _rule in FIRE_WEATHER]
        layer.setRenderer(QgsCategorizedSymbolRenderer("event", cats))
        tip = ("<b>[% \"event\" %]</b><br>[% coalesce(nullif(\"zoneName\", ''), \"area\") %]"
               "<br>Until [% \"ends\" %]<br>[% CASE " + _rule_cases("\"event\"", [(e, e, c, r) for e, c, r in FIRE_WEATHER]) + " END %]")
    elif key == "fireper":
        layer.setRenderer(QgsSingleSymbolRenderer(_area(FIRE_COLOUR, 0.3, 2)))
        tip = ("<b>[% title(lower(\"poly_IncidentName\")) %] fire · perimeter</b>"
               "<br>[% format_number(\"poly_GISAcres\", 0) %] acres · [% coalesce(\"attr_PercentContained\", '?') %]% contained"
               "<br>Mapped [% format_date(\"poly_DateCurrent\", 'd MMM yyyy h:mm ap') %]")
    elif key == "fire":
        layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": FIRE_COLOUR, "outline_color": "#ffffff", "outline_width": "0.4", "size": "3"})))
        set_labels(layer, "title(lower(\"IncidentName\"))", 500000)
        tip = ("<b>[% title(lower(\"IncidentName\")) %] fire</b>"
               "<br>[% format_number(\"IncidentSize\", 0) %] acres · [% coalesce(\"PercentContained\", '?') %]% contained"
               "<br>Updated [% format_date(\"ModifiedOnDateTime_dt\", 'd MMM yyyy h:mm ap') %]")
    elif key == "hosp":
        layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "cross_fill", "color": HOSPITAL_COLOUR, "outline_color": "#ffffff", "outline_width": "0.3", "size": "4.2"})))
        set_labels(layer, "title(lower(\"NAME\"))", 150000)
        tip = ("<b>[% title(lower(\"NAME\")) %]</b><br>[% title(lower(\"ADDRESS\")) %], [% title(lower(\"CITY\")) %]"
               "<br>[% title(lower(\"TYPE\")) %][% CASE WHEN \"TRAUMA\" LIKE 'LEVEL%' THEN ' · Trauma ' || replace(\"TRAUMA\", 'LEVEL ', '') END %]"
               "[% CASE WHEN \"HELIPAD\" = 'Y' THEN ' · Helipad' END %]"
               "<br><a href=\"tel:[% regexp_replace(\"TELEPHONE\", '[^0-9+]', '') %]\">[% \"TELEPHONE\" %]</a>"
               "<br>Not every hospital has an emergency room: call ahead. In an emergency, call 911.")
    else:                   # protected areas
        cats = [QgsRendererCategory(cat, _area(colour, 0.15, 1.6, line_opacity=0.9), label) for cat, label, colour, _rule in PROTECTED]
        layer.setRenderer(QgsCategorizedSymbolRenderer(PROTECTED_CATEGORY, cats))
        tip = "<b>[% \"Unit_Nm\" %]</b><br>[% CASE " + _rule_cases(PROTECTED_CATEGORY, PROTECTED) + " END %]"
    layer.setMapTipTemplate(tip)
    layer.setScaleBasedVisibility(True)
    layer.setMinimumScale(OVERLAYS[key][3])      # hidden when zoomed out beyond this, as in FieldKey
    layer.setReadOnly(True)
    if key in LIVE:                              # fires and TFRs change through the day
        layer.setAutoRefreshInterval(LIVE_MINUTES * 60000)
        try:
            layer.setAutoRefreshMode(Qgis.AutoRefreshMode.ReloadData)
        except AttributeError:                   # before QGIS 3.34
            layer.setAutoRefreshEnabled(True)


def remove_reference_layers(project):
    """Take out what an earlier run added. Returns the basemap that was switched on, if any."""
    root = project.layerTreeRoot()
    chosen = None
    for node in list(root.children()):
        if node.nodeType() == node.NodeGroup and node.customProperty(REF_TAG):
            if node.name() == BASEMAP_GROUP:
                chosen = next((c.name() for c in node.children() if c.itemVisibilityChecked()), None)
            root.removeChildNode(node)
        elif (node.nodeType() == node.NodeLayer and node.name() == "OpenStreetMap" and node.layer()
              and "tile.openstreetmap.org" in node.layer().source()):
            project.removeMapLayer(node.layerId())           # the one basemap older versions of this script added
    for lyr in list(project.mapLayers().values()):
        if lyr.customProperty(REF_TAG):
            project.removeMapLayer(lyr.id())
    return chosen


def data_extent(layers, crs, project):
    """The area the FieldKey features cover, in crs, with a margin. None when there are no features yet."""
    box = None
    for lyr in layers:
        if lyr.featureCount() == 0 or lyr.extent().isNull():
            continue
        part = QgsCoordinateTransform(lyr.crs(), crs, project).transformBoundingBox(lyr.extent())
        if box is None:
            box = QgsRectangle(part)
        else:
            box.combineExtentWith(part)
    if box is None:
        return None
    return box.buffered(max(box.width(), box.height()) * 0.1 + 1000)


def add_reference_layers(project, make_feature_layer=feature_service_layer, online=True, default_basemap=None,
                         data_layers=()):
    """Basemaps, 3D terrain, airspace (with TFRs), wildfire, hospitals and protected areas from the sources FieldKey uses.

    Returns (layers by key, names that couldn't be loaded). A source that can't be reached is
    skipped: run the script again later to add it.
    """
    root = project.layerTreeRoot()
    chosen = remove_reference_layers(project) or default_basemap or DEFAULT_BASEMAP
    made, missing = {}, []

    def keep(lyr, key, what):
        if lyr is None or not lyr.isValid():
            missing.append(what)
            return None
        project.addMapLayer(_tag(lyr, key), False)
        made[key] = lyr
        return lyr

    # airspace over protected areas, both under the FieldKey layers
    at = 1 if root.findGroup(GROUP_NAME) else 0
    air = _tag(root.insertGroup(at, AIRSPACE_GROUP), "airspace")
    for key, name in AIRSPACE_LAYERS:
        lyr = keep(make_feature_layer(key, name), key, name)
        if lyr:
            style_overlay(lyr, key)
            air.addLayer(lyr)
    fire = _tag(root.insertGroup(at + 1, FIRE_GROUP), "wildfire")
    for key, name in FIRE_LAYERS:
        lyr = keep(make_feature_layer(key, name), key, name)
        if lyr:
            style_overlay(lyr, key)
            fire.addLayer(lyr)
    hosp = keep(make_feature_layer("hosp", HOSPITAL_LAYER), "hosp", HOSPITAL_LAYER)
    if hosp:
        style_overlay(hosp, "hosp")
        root.insertLayer(at + 2, hosp)
    env = keep(make_feature_layer("env", PROTECTED_LAYER), "env", PROTECTED_LAYER)
    if env:
        style_overlay(env, "env")
        root.insertLayer(at + 3 if hosp else at + 2, env)

    tile_url = openfreemap_tiles() if online else OFM_OFFLINE_TILES
    if not tile_url:
        missing.append("Dark map and Hybrid road names (OpenFreeMap)")
    dem, relief = terrain_layers()
    base = _tag(root.addGroup(BASEMAP_GROUP), "basemaps")

    def imagery(group, suffix):
        pair = [(xyz_layer(USGS_IMAGERY, "USGS imagery", 16), "USGS imagery")]
        if online:                               # NAIP has to be asked what it offers, so it needs a connection
            pair.insert(0, (naip_layer(), "Close-ups (NAIP)"))
        for lyr, what in pair:
            if keep(lyr, what + suffix, what):
                group.addLayer(lyr)

    dark = base.addGroup("Dark")
    if keep(relief, "relief", "Terrain relief"):
        dark.addLayer(relief)
    if tile_url and keep(dark_layer(tile_url) if online else vector_tiles(tile_url, "Dark map"), "dark", "Dark map"):
        dark.addLayer(made["dark"])
    imagery(base.addGroup("Aerial"), " (aerial)")
    hybrid = base.addGroup("Hybrid")
    if tile_url and keep(hybrid_roads_layer(tile_url), "roads", "Hybrid roads and names"):
        hybrid.addLayer(made["roads"])
    imagery(hybrid, " (hybrid)")
    if keep(xyz_layer(OSM_TILES, "Streets", 19), "streets", "Streets (OpenStreetMap)"):
        base.addLayer(made["streets"])
    if keep(xyz_layer(USGS_TOPO, "Topo", 16), "topo", "Topo (USGS)"):
        base.addLayer(made["topo"])

    names = [c.name() for c in base.children()]
    if chosen not in names or (chosen == "Dark" and "dark" not in made):
        chosen = "Streets" if "Streets" in names else names[0]
    for child in base.children():
        child.setItemVisibilityChecked(child.name() == chosen)
    base.setIsMutuallyExclusive(True, names.index(chosen))    # one basemap at a time, like FieldKey's switcher

    if keep(dem, "dem", "3D terrain"):
        root.addLayer(dem).setItemVisibilityChecked(False)    # used as the terrain in 3D views, not drawn on the flat map
        set_terrain(project, dem)

    # web maps are drawn in Web Mercator; this keeps the basemaps sharp and shaped as in FieldKey
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    try:
        display = project.displaySettings()
        display.setCoordinateType(Qgis.CoordinateDisplayType.CustomCrs)
        display.setCoordinateCustomCrs(QgsCoordinateReferenceSystem("EPSG:4326"))    # status bar keeps showing lat/long
    except AttributeError:
        pass
    # "Zoom Full" and new 3D views cover the FieldKey sites, not the whole country the overlays span
    box = data_extent(data_layers, project.crs(), project)
    if box:
        project.viewSettings().setPresetFullExtent(QgsReferencedRectangle(box, project.crs()))
    return made, missing


def project_uri():
    return (f"postgresql://{HOST}:{PORT}?sslmode=require&dbname={DBNAME}&schema=qgis"
            f"&project={PROJECT_NAME}&authcfg={AUTHCFG}")


def build(project=None, make_layer=postgres_layer, save_styles=True, save_project=SAVE_PROJECT_TO_DB,
          reference_layers=ADD_REFERENCE_LAYERS, reference_options=None):
    project = project or QgsProject.instance()
    if make_layer is postgres_layer and (not HOST or not AUTHCFG):
        raise RuntimeError("Set HOST and AUTHCFG at the top of fieldkey_qgis_setup.py first (see docs/qgis-setup.md).")
    root = project.layerTreeRoot()
    old = root.findGroup(GROUP_NAME)
    if old:
        for lyr in old.findLayers():
            project.removeMapLayer(lyr.layerId())
        root.removeChildNode(old)
    group = root.insertGroup(0, GROUP_NAME)

    layers = {}
    for table, name, _geom in LAYERS:
        lyr = make_layer(table, name)
        if not lyr.isValid():
            raise RuntimeError(f"Couldn't open {table}. Check HOST, the auth config and that the project isn't paused.")
        layers[name] = lyr
        project.addMapLayer(lyr, False)
    for table, name, _geom in LAYERS:
        configure_layer(layers[name], table, layers)
        group.insertLayer(0, layers[name])     # last in LAYERS ends up on top (assets over pins over photos...)
    if save_styles:
        for lyr in layers.values():
            save_style_to_db(lyr)

    build.missing = []
    if reference_layers:
        _made, build.missing = add_reference_layers(project, data_layers=list(layers.values()), **(reference_options or {}))
    elif not any(isinstance(l, QgsRasterLayer) and "tile.openstreetmap.org" in l.source() for l in project.mapLayers().values()):
        osm = xyz_layer(OSM_TILES, "OpenStreetMap", 19)
        if osm.isValid():
            project.addMapLayer(osm, False)
            root.addLayer(osm)

    if save_project:
        if not project.write(project_uri()):
            raise RuntimeError("Saving to PostgreSQL failed: " + project.error())
    return layers


if __name__ in ("__main__", "__console__"):
    build()
    try:
        from qgis.utils import iface
        iface.messageBar().pushSuccess("FieldKey", "Layers added" + (" and project saved to PostgreSQL" if SAVE_PROJECT_TO_DB else ""))
        if build.missing:
            iface.messageBar().pushWarning("FieldKey", "Couldn't reach: " + ", ".join(build.missing)
                                           + ". Run the script again later to add them.")
    except Exception:
        pass
