#!/usr/bin/env python3
from pathlib import Path
import sys

# Applied after v0.9.28: keep selected-object-first behavior, but restore the
# native pointer hit-test as a fallback when GeoGebra's selection vanished
# before the Quest A-button command reaches the WebView/UI thread.
if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0929.py <geogebra-source-root>")

root = Path(sys.argv[1])
path = root / "source/web/web-common/src/main/java/org/geogebra/web/html5/euclidian/EuclidianControllerW.java"
text = path.read_text(encoding="utf-8")

if "v0.9.29 selected-first pointer fallback" in text:
    print("[GGQ] v0.9.29 A-button fallback already present")
    raise SystemExit(0)

old = """\t\tArrayList<GeoElement> selectedGeos = controller.getAppSelectedGeos();\n\t\tif (selectedGeos == null || selectedGeos.isEmpty()\n\t\t\t\t|| controller.app.getGuiManager() == null) {\n\t\t\treturn false;\n\t\t}\n\n\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\tselectedGeos, controller.getView(), controller.mouseLoc);\n\t\treturn true;\n"""
new = """\t\t// v0.9.29 selected-first pointer fallback: prefer GeoGebra's current\n\t\t// selection, but if UI/render latency cleared it before A is handled,\n\t\t// fall back to GeoGebra's native long-touch hit-test at the last pointer.\n\t\tArrayList<GeoElement> selectedGeos = controller.getAppSelectedGeos();\n\t\tif (selectedGeos != null && !selectedGeos.isEmpty()\n\t\t\t\t&& controller.app.getGuiManager() != null) {\n\t\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\t\tselectedGeos, controller.getView(), controller.mouseLoc);\n\t\t\treturn true;\n\t\t}\n\n\t\tcontroller.handleLongTouch(x, y);\n\t\treturn true;\n"""

if old not in text:
    raise SystemExit("[GGQ] v0.9.29 v0.9.28 selected-menu anchor not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("[GGQ] v0.9.29 A-button uses selection first, native pointer hit-test fallback second")
