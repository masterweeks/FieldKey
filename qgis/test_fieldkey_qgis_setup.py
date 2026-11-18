"""Offline test of fieldkey_qgis_setup.py: same configuration, applied to in-memory layers
with the real FieldKey columns, written to a .qgs file and read back.

  "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" qgis\\test_fieldkey_qgis_setup.py
"""
import os
import sys
import tempfile

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer

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


def memory_layer(table, name):
    fields = "&".join("field=" + f for f in COMMON[:1] + COLUMNS[table] + COMMON[1:])
    return QgsVectorLayer(f"{GEOM[table]}?crs=EPSG:4326&{fields}", name, "memory")


def main():
    app = QgsApplication([], False)
    app.initQgis()
    failures = []

    def check(cond, msg):
        print(("ok   " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    proj = QgsProject.instance()
    fk.build(project=proj, make_layer=memory_layer, save_styles=False, save_project=False)
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

    app.exitQgis()
    print("\n%d check(s) failed" % len(failures) if failures else "\nall checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
