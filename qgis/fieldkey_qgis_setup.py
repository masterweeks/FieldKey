"""FieldKey QGIS project setup.

Run inside QGIS (3.30 or later):
  1. Fill in HOST and AUTHCFG below (see docs/qgis-setup.md).
  2. Plugins -> Python Console -> Show Editor -> Open Script... -> this file -> Run Script.

It adds the FieldKey layers from Supabase PostGIS (session pooler, SSL required), styles
them, sets up the attribute forms, saves each layer's style into the database as its
default (public.layer_styles), and saves the whole project into Postgres
(schema qgis, project "FieldKey") so anyone can open it with Project -> Open From ->
PostgreSQL. Running it again rebuilds the FieldKey group and saves again.

No passwords live in this file: AUTHCFG is the id of a QGIS authentication configuration
that holds the qgis_editor login, stored in QGIS's encrypted password database.
"""
from qgis.core import (
    QgsAction, QgsActionManager, QgsCategorizedSymbolRenderer, QgsDataSourceUri,
    QgsDefaultValue, QgsEditorWidgetSetup, QgsFillSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
    QgsProject, QgsRasterLayer, QgsRendererCategory, QgsSingleSymbolRenderer, QgsTextFormat,
    QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

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
        for value, label, colour in ASSET_STATUS:
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "size": "3.4",
                                                "outline_color": "#0E1116", "outline_width": "0.4"})
            cats.append(QgsRendererCategory(value, sym, label))
        layer.setRenderer(QgsCategorizedSymbolRenderer("status", cats))
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


def project_uri():
    return (f"postgresql://{HOST}:{PORT}?sslmode=require&dbname={DBNAME}&schema=qgis"
            f"&project={PROJECT_NAME}&authcfg={AUTHCFG}")


def build(project=None, make_layer=postgres_layer, save_styles=True, save_project=SAVE_PROJECT_TO_DB):
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

    if not any(isinstance(l, QgsRasterLayer) and l.name() == "OpenStreetMap" for l in project.mapLayers().values()):
        osm = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
                             "OpenStreetMap", "wms")
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
    except Exception:
        pass
