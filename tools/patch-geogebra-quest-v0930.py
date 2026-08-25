#!/usr/bin/env python3
from pathlib import Path
import sys

# Applied after v0.9.29. Make Quest A deterministic for 3D:
# 1) anchor GeoGebra mouseLoc to the exact Quest pointer x/y passed by JS,
# 2) prefer the existing selected GeoElement(s),
# 3) if selection was lost, run GeoGebra's native view hit-test at the same x/y,
#    select the top hit, and open that object's popup directly.
if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0930.py <geogebra-source-root>")

root = Path(sys.argv[1])
path = root / "source/web/web-common/src/main/java/org/geogebra/web/html5/euclidian/EuclidianControllerW.java"
text = path.read_text(encoding="utf-8")

if "v0.9.30 Quest-pointer anchored context menu" in text:
    print("[GGQ] v0.9.30 Quest-pointer context menu already present")
    raise SystemExit(0)

old = """\t\t// v0.9.29 selected-first pointer fallback: prefer GeoGebra's current\n\t\t// selection, but if UI/render latency cleared it before A is handled,\n\t\t// fall back to GeoGebra's native long-touch hit-test at the last pointer.\n\t\tArrayList<GeoElement> selectedGeos = controller.getAppSelectedGeos();\n\t\tif (selectedGeos != null && !selectedGeos.isEmpty()\n\t\t\t\t&& controller.app.getGuiManager() != null) {\n\t\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\t\tselectedGeos, controller.getView(), controller.mouseLoc);\n\t\t\treturn true;\n\t\t}\n\n\t\tcontroller.handleLongTouch(x, y);\n\t\treturn true;\n"""
new = """\t\t// v0.9.30 Quest-pointer anchored context menu. The x/y received from JS\n\t\t// are authoritative for both popup placement and fallback 3D hit-testing.\n\t\tint questX = (int) Math.round(x);\n\t\tint questY = (int) Math.round(y);\n\t\tcontroller.setMouseLocation(false, questX, questY);\n\n\t\tArrayList<GeoElement> selectedGeos = controller.getAppSelectedGeos();\n\t\tif (selectedGeos != null && !selectedGeos.isEmpty()\n\t\t\t\t&& controller.app.getGuiManager() != null) {\n\t\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\t\tselectedGeos, controller.getView(), controller.mouseLoc);\n\t\t\treturn true;\n\t\t}\n\n\t\t// Selection can disappear between the pointer event and controller A. Re-run\n\t\t// GeoGebra's own hit-test at the exact same view-local Quest coordinate.\n\t\tcontroller.getView().setHits(controller.mouseLoc, PointerEventType.MOUSE);\n\t\tHits pointerHits = controller.getView().getHits().getTopHits();\n\t\tif (pointerHits != null && !pointerHits.isEmpty()\n\t\t\t\t&& controller.app.getGuiManager() != null) {\n\t\t\tGeoElement pointerGeo = pointerHits.get(0);\n\t\t\tif (pointerGeo != null) {\n\t\t\t\tArrayList<GeoElement> pointerSelection = new ArrayList<>();\n\t\t\t\tpointerSelection.add(pointerGeo);\n\t\t\t\tcontroller.app.getSelectionManager().setSelectedGeos(pointerSelection);\n\t\t\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\t\tpointerSelection, controller.getView(), controller.mouseLoc);\n\t\t\t\treturn true;\n\t\t\t}\n\t\t}\n\n\t\t// No object at the Quest pointer: do not manufacture a background popup.\n\t\treturn false;\n"""

if old not in text:
    raise SystemExit("[GGQ] v0.9.30 v0.9.29 context-menu anchor not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("[GGQ] v0.9.30 A context menu anchored to Quest pointer with native 3D hit fallback")
