"""Test of fieldkey_qgis_setup.py: same configuration, applied to in-memory layers with the
real FieldKey columns, written to a .qgs file and read back. Runs without a connection.

  "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" qgis\\test_fieldkey_qgis_setup.py

Add --online to also load the real basemaps, terrain, airspace and protected areas from
their services and check they answer (about a minute; needs the internet).
"""
import os
import sys
import tempfile

from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, QgsExpressionContext,
    QgsExpressionContextScope, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer,
    QgsRectangle, QgsVectorLayer, QgsVectorTileBasicRendererStyle, QgsVectorTileLayer,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fieldkey_qgis_setup as fk  # noqa: E402

COMMON = ["id:string", "owner_id:string", "legacy_id:string", "created_at:datetime", "created_by:string",
          "updated_at:datetime", "updated_by:string", "client_updated_at:datetime", "deleted_at:datetime"]
COLUMNS = {
    "missions": ["name:string", "source_file:string", "status:string", "notes:string"],
    "circuits": ["name:string", "code:string", "notes:string"],
    "assets": ["mission_id:string", "circuit_id:string", "sap_id:string", "name:string", "address:string",
               "phones:string", "access:string", "access_notes:string", "status:string", "text_count:integer",
               "last_texted_at:datetime", "scheduled_at:datetime", "notes:string", "access_issue:boolean",
               "access_issue_reason:string", "extra:string"],
    "pins": ["mission_id:string", "asset_id:string", "kind:string", "label:string", "notes:string"],
    "inspections": ["mission_id:string", "asset_id:string", "inspected_at:datetime", "outcome:string", "notes:string"],
    "photos": ["mission_id:string", "asset_id:string", "pin_id:string", "inspection_id:string", "storage_path:string",
               "mime_type:string", "taken_at:datetime", "caption:string"],
}
GEOM = {t: g for t, _n, g in fk.LAYERS}
# the columns of the FAA and USGS services that the styles and hover tips use
OVERLAY_COLUMNS = {
    "class": ["NAME:string", "CLASS:string", "LOCAL_TYPE:string"],
    "sua": ["NAME:string", "TYPE_CODE:string", "TIMESOFUSE:string"],
    "nsr": ["Facility:string", "Base:string"],
    "nsrpt": ["Facility:string", "Base:string"],
    "uasfm": ["CEILING:integer", "APT1_NAME:string"],
    "env": ["Unit_Nm:string", "Des_Tp:string", "Mang_Name:string", "Mang_Type:string"],
}
BASEMAPS = ["Dark", "Aerial", "Hybrid", "Streets", "Topo"]
OFFLINE = {"make_feature_layer": None, "online": False}     # make_feature_layer is filled in below


def memory_layer(table, name):
    fields = "&".join("field=" + f for f in COMMON[:1] + COLUMNS[table] + COMMON[1:])
    return QgsVectorLayer(f"{GEOM[table]}?crs=EPSG:4326&{fields}", name, "memory")


def memory_overlay(key, name):
    fields = "&".join("field=" + f for f in OVERLAY_COLUMNS[key])
    return QgsVectorLayer(f"MultiPolygon?crs=EPSG:4326&{fields}", name, "memory")


OFFLINE["make_feature_layer"] = memory_overlay


def one_site(table, name):
    """Like memory_layer, with one asset in Redding so there is an area to zoom to."""
    lyr = memory_layer(table, name)
    if table == "assets":
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(-122.39, 40.58)))
        lyr.dataProvider().addFeatures([f])
        lyr.updateExtents()
    return lyr


def evaluate(expression, **variables):
    scope = QgsExpressionContextScope()
    for k, v in variables.items():
        scope.setVariable(k, v)
    ctx = QgsExpressionContext()
    ctx.appendScope(scope)
    return QgsExpression(expression).evaluate(ctx)


def checked(group):
    return [c.name() for c in group.children() if c.itemVisibilityChecked()]


def check_reference_layers(proj, check):
    """Basemaps, terrain, airspace and protected areas, as build() leaves them."""
    root = proj.layerTreeRoot()
    by = {l.name(): l for l in proj.mapLayers().values()}
    base = root.findGroup(fk.BASEMAP_GROUP)
    check(base is not None and [c.name() for c in base.children()] == BASEMAPS, "five basemaps, named as in FieldKey")
    check(base.isMutuallyExclusive() and checked(base) == [fk.DEFAULT_BASEMAP], "one basemap on at a time, Dark first")
    order = [c.name() for c in root.children()]
    check(order[:3] == [fk.GROUP_NAME, fk.AIRSPACE_GROUP, fk.PROTECTED_LAYER] and order[-2:] == [fk.BASEMAP_GROUP, "Terrain (elevation)"],
          "order: FieldKey data, airspace, protected areas ... basemaps, terrain")
    air = root.findGroup(fk.AIRSPACE_GROUP)
    check([c.name() for c in air.children()] == [n for _k, n in fk.AIRSPACE_LAYERS], "airspace: restrictions on top, LAANC grid lowest")

    cls = by["Controlled airspace"].renderer()
    check(cls.type() == "categorizedSymbol" and [c.value() for c in cls.categories()] == ["B", "C", "D", "E"], "controlled airspace by class")
    colour = {c.value(): c.symbol().symbolLayer(0).strokeColor().name().upper() for c in cls.categories()}
    check(colour == {"B": "#3B7BFF", "C": "#D6336C", "D": "#4DABF7", "E": "#E64980"}, "class colours match FieldKey")
    dashed = {c.value(): int(c.symbol().symbolLayer(0).strokeStyle()) != 1 for c in cls.categories()}
    check(dashed == {"B": False, "C": False, "D": True, "E": True}, "B and C solid, D and E dashed")
    sua = by["Special use airspace"].renderer()
    check(sua.type() == "categorizedSymbol" and len(sua.categories()) == 7 and sua.categories()[-1].value() in ("", None),
          "special use airspace by type, with a catch-all")
    grid = by["LAANC grid"]
    check(grid.renderer().type() == "graduatedSymbol" and len(grid.renderer().ranges()) == 5 and grid.labelsEnabled(),
          "LAANC grid coloured by ceiling and labelled")
    band = lambda v: (grid.renderer().symbolForValue(v).color().name().upper() if grid.renderer().symbolForValue(v) else None)
    check([band(v) for v in (0, 50, 100, 150, 200, 250, 300, 350, 400)]
          == ["#FA5252", "#FD7E14", "#FD7E14", "#FCC419", "#FCC419", "#94D82D", "#94D82D", "#40C057", "#40C057"],
          "LAANC ceilings 0 to 400 ft get FieldKey's colours")
    check(by["National security restrictions"].renderer().type() == "singleSymbol", "national security restrictions in red")

    env = by[fk.PROTECTED_LAYER]
    check(env.renderer().type() == "categorizedSymbol" and len(env.renderer().categories()) == 6, "protected areas in six kinds")
    # the same sorting as envCat() in index.html
    want = [("WA", "USFS", "wild"), ("WSA", "BLM", "wild"), ("NWR", "FWS", "fws"), ("WPA", "X", "fws"), ("NP", "NPS", "nps"),
            ("MPA", "NOAA", "mpa"), ("SW", "SFW", "stwild"), ("SP", "SPR", "stpark"), ("SREC", "OTHS", "stpark")]
    got = []
    for des, mang, _cat in want:
        f = QgsFeature(env.fields())
        f["Des_Tp"], f["Mang_Name"] = des, mang
        ctx = QgsExpressionContext()
        ctx.setFeature(f)
        ctx.setFields(env.fields())
        got.append(QgsExpression(fk.PROTECTED_CATEGORY).evaluate(ctx))
    check(got == [c for _d, _m, c in want], "protected areas sorted into kinds the way FieldKey does")

    for key, name in fk.AIRSPACE_LAYERS + [("env", fk.PROTECTED_LAYER)]:
        lyr = by[name]
        if not (lyr.hasScaleBasedVisibility() and lyr.minimumScale() == fk.OVERLAYS[key][3] and lyr.mapTipTemplate()
                and lyr.customProperty(fk.REF_TAG) == key):
            check(False, name + ": scale limit, hover tip and tag")
            break
    else:
        check(True, "every overlay hides when zoomed far out and has a hover tip")

    dem = by["Terrain (elevation)"]
    terrain = proj.elevationProperties().terrainProvider()
    check(terrain.type() == "raster" and terrain.layer() is not None and terrain.layer().id() == dem.id(), "elevation layer is the project's terrain")
    check("interpretation=terrariumterrain" in dem.source() and not root.findLayer(dem.id()).itemVisibilityChecked(),
          "elevation decoded from terrain tiles, and not drawn on the flat map")
    # (the 3D view itself can't be opened from a script without the QGIS window, so it isn't tested here)
    relief = by["Terrain relief"]
    check(relief.renderer().type() == "hillshade" and relief.maximumScale() == fk.RELIEF_TO_SCALE, "Dark basemap has shaded relief")

    roads = by["Roads and names"]
    check(isinstance(roads, QgsVectorTileLayer) and len(roads.renderer().styles()) == 8 and len(roads.labeling().styles()) == 2,
          "Hybrid: four road kinds with an edge and a surface, plus road and town names")
    check(proj.crs().authid() == "EPSG:3857", "project drawn in Web Mercator like FieldKey")


def main():
    online = "--online" in sys.argv
    app = QgsApplication([], False)
    app.initQgis()
    failures = []

    def check(cond, msg):
        print(("ok   " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    proj = QgsProject.instance()
    # a project made by the earlier version of the script has one OpenStreetMap layer at the bottom
    old = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0", "OpenStreetMap", "wms")
    proj.addMapLayer(old)
    fk.build(project=proj, make_layer=one_site, save_styles=False, save_project=False, reference_options=OFFLINE)
    check(fk.build.missing == [], "nothing reported missing")
    check(not any(l.name() == "OpenStreetMap" for l in proj.mapLayers().values()), "the old single OpenStreetMap layer is replaced")
    full = proj.viewSettings().presetFullExtent()
    site = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), proj.crs(), proj).transform(QgsPointXY(-122.39, 40.58))
    check(not full.isNull() and full.contains(site) and 1500 < full.width() < 50000, "Zoom Full goes to the FieldKey sites")
    path = os.path.join(tempfile.mkdtemp(), "fieldkey_test.qgs")
    check(proj.write(path), "project written to " + path)
    proj.clear()
    check(proj.read(path), "project read back")

    by = {l.name(): l for l in proj.mapLayers().values()}
    check(all(n in by for _t, n, _g in fk.LAYERS), "all six FieldKey layers present")
    group = proj.layerTreeRoot().findGroup(fk.GROUP_NAME)
    check(group is not None and [c.name() for c in group.children()][0] == "Assets", "FieldKey group with Assets on top")

    a = by["Assets"]
    f = a.fields()
    w = lambda lyr, name: lyr.editorWidgetSetup(lyr.fields().indexOf(name))
    check(w(a, "status").type() == "ValueMap", "assets.status is a value map")
    vm = {list(d.values())[0]: list(d.keys())[0] for d in w(a, "status").config()["map"]}
    check(vm.get("texted") == "Texted" and vm.get("enriched", "").startswith("New"), "status labels map to stored values")
    check(w(a, "deleted_at").type() == "Hidden", "deleted_at hidden")
    check(w(a, "owner_id").type() == "Hidden", "owner_id hidden")
    form = a.editFormConfig()
    check(all(form.readOnly(f.indexOf(n)) for n in fk.SYSTEM_READ_ONLY), "system fields read-only")
    check(form.readOnly(f.indexOf("phones")), "phones read-only JSON")
    check(w(a, "mission_id").type() == "ValueRelation" and w(a, "mission_id").config()["Value"] == "name",
          "mission_id picks from Missions by name")
    check("get_feature('Missions'" in a.defaultValueDefinition(f.indexOf("owner_id")).expression(),
          "owner_id defaults to the mission's owner")
    check(a.renderer().type() == "categorizedSymbol" and len(a.renderer().categories()) == 6, "assets styled by status")
    check(a.labelsEnabled(), "assets labelled")
    check(any(x.name().startswith("Soft delete") for x in a.actions().actions()), "soft delete action present")

    p = by["Pins"]
    check(w(p, "kind").type() == "ValueMap" and p.renderer().type() == "categorizedSymbol", "pins: kind value map + style")
    ph = by["Photos"]
    check(w(ph, "storage_path").type() == "ExternalResource" and w(ph, "storage_path").config().get("DocumentViewer") == 1,
          "photos.storage_path uses the Attachment widget as an image")
    m = by["Missions"]
    check("aggregate" in m.defaultValueDefinition(m.fields().indexOf("owner_id")).expression(), "mission owner default")
    check(w(by["Inspections"], "outcome").type() == "ValueMap", "inspections.outcome value map")

    uri = fk.project_uri()
    check(uri.startswith("postgresql://") and "schema=qgis" in uri and "sslmode=require" in uri and "authcfg=" in uri,
          "project URI targets schema qgis over SSL with an auth config")

    print("\n-- basemaps, terrain, airspace and protected areas (after saving and reopening)")
    check_reference_layers(proj, check)

    # Hybrid road widths follow FieldKey's: fixed at zoom 11, 16 and 19, growing 1.4x a zoom level between
    width = fk._zoom_mm(2.6, 10, 20)
    at = lambda z: evaluate(width, vector_tile_zoom=z) / fk.PX
    mid = 2.6 + (10 - 2.6) * (1.4 ** 2.5 - 1) / (1.4 ** 5 - 1)
    check(all(abs(a - b) < 1e-6 for a, b in ((at(9), 2.6), (at(11), 2.6), (at(16), 10), (at(19), 20), (at(21), 20), (at(13.5), mid))),
          "Hybrid road widths match FieldKey's at every zoom")
    st = QgsVectorTileBasicRendererStyle("park", "landuse")
    st.setFilterExpression("(\"\" IN ('MultiPolygon', 'Polygon')) AND (\"class\" IS 'park')")
    check(fk._without_geometry_tests([st])[0].filterExpression() == "(TRUE) AND (\"class\" IS 'park')",
          "Dark style: the geometry test QGIS can't convert is taken out")

    print("\n-- running the script again")
    base = proj.layerTreeRoot().findGroup(fk.BASEMAP_GROUP)
    [c for c in base.children() if c.name() == "Topo"][0].setItemVisibilityChecked(True)
    check(checked(base) == ["Topo"], "ticking Topo unticks Dark")
    before = len(proj.mapLayers())
    fk.build(project=proj, make_layer=one_site, save_styles=False, save_project=False, reference_options=OFFLINE)
    root = proj.layerTreeRoot()
    check(len(proj.mapLayers()) == before and [c.name() for c in root.children()].count(fk.BASEMAP_GROUP) == 1
          and [c.name() for c in root.children()].count(fk.AIRSPACE_GROUP) == 1, "no duplicate layers or groups")
    check(checked(root.findGroup(fk.BASEMAP_GROUP)) == ["Topo"], "the basemap you had on stays on")

    proj.clear()
    fk.build(project=proj, make_layer=memory_layer, save_styles=False, save_project=False, reference_layers=False)
    names = [l.name() for l in proj.mapLayers().values()]
    check(len(names) == 7 and "OpenStreetMap" in names and proj.layerTreeRoot().findGroup(fk.BASEMAP_GROUP) is None,
          "ADD_REFERENCE_LAYERS = False gives the six layers and OpenStreetMap only")
    check(proj.viewSettings().presetFullExtent().isNull(), "no sites yet: Zoom Full is left alone")

    if online:
        print("\n-- online: the real services")
        proj.clear()
        fk.build(project=proj, make_layer=one_site, save_styles=False, save_project=False)
        check(fk.build.missing == [], "every source answered" + (": missing " + ", ".join(fk.build.missing) if fk.build.missing else ""))
        check_reference_layers(proj, check)
        by = {l.name(): l for l in proj.mapLayers().values()}
        dark = by["Dark map"]
        filters = [s.filterExpression() for s in dark.renderer().styles()] + [s.filterExpression() for s in dark.labeling().styles()]
        check(len(dark.renderer().styles()) > 30 and len(dark.labeling().styles()) > 8 and not any('"" IN (' in x for x in filters),
              "Dark map: FieldKey's style loaded, with no filter left that hides everything")
        to = lambda lyr, x, y: QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), lyr.crs(), proj).transform(QgsPointXY(x, y))
        elev, ok = by["Terrain (elevation)"].dataProvider().sample(to(by["Terrain (elevation)"], -122.195, 41.409), 1)
        check(ok and 4100 < elev < 4400, "terrain: Mount Shasta's summit reads %.0f m" % elev)
        check(by["Close-ups (NAIP)"].isValid() and by["Close-ups (NAIP)"].minimumScale() == fk.NAIP_FROM_SCALE, "NAIP close-ups load below 1:7,000")

        def near(name, w, s, e, n):
            lyr = by[name]
            box = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), lyr.crs(), proj).transformBoundingBox(QgsRectangle(w, s, e, n))
            return list(lyr.getFeatures(QgsFeatureRequest().setFilterRect(box)))

        rdd = near("Controlled airspace", -122.35, 40.45, -122.25, 40.55)
        check(any(f["CLASS"] == "D" for f in rdd), "controlled airspace: Redding airport's Class D is there")
        check(len(near("LAANC grid", -122.31, 40.49, -122.28, 40.52)) > 0, "LAANC grid squares around Redding airport")
        parks = near(fk.PROTECTED_LAYER, -122.75, 40.5, -122.4, 40.75)
        check(any("Whiskeytown" in (f["Unit_Nm"] or "") for f in parks), "protected areas: Whiskeytown is there")
        check(by["Special use airspace"].featureCount() != 0 and by["National security restrictions"].featureCount() != 0,
              "special use airspace and national security restrictions have features")

    app.exitQgis()
    print("\n%d check(s) failed" % len(failures) if failures else "\nall checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
