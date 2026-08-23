#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0928.py <geogebra-source-root>")

root = Path(sys.argv[1])
path = root / "source/web/web-common/src/main/java/org/geogebra/web/html5/euclidian/EuclidianControllerW.java"
text = path.read_text(encoding="utf-8")

if "v0.9.28 selected-object menu" in text:
    print("[GGQ] v0.9.28 selected-object context-menu hook already present")
    raise SystemExit(0)

old = """\t\tcontroller.handleLongTouch(x, y);\n\t\treturn true;\n\t}\n\n\t/**\n\t * Quest-only bridge: close the active GeoGebra popup/context menu.\n"""
new = """\t\t// v0.9.28 selected-object menu: A must act on the object already selected\n\t\t// by the Quest pointer, not perform a new hit-test on the background.\n\t\tArrayList<GeoElement> selectedGeos = controller.getAppSelectedGeos();\n\t\tif (selectedGeos == null || selectedGeos.isEmpty()\n\t\t\t\t|| controller.app.getGuiManager() == null) {\n\t\t\treturn false;\n\t\t}\n\n\t\tcontroller.app.getGuiManager().showPopupMenu(\n\t\t\t\tselectedGeos, controller.getView(), controller.mouseLoc);\n\t\treturn true;\n\t}\n\n\t/**\n\t * Quest-only bridge: close the active GeoGebra popup/context menu.\n"""

if old not in text:
    raise SystemExit("[GGQ] v0.9.28 v0.9.27 hook body anchor not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("[GGQ] v0.9.28 A-button hook now opens the selected GeoElement popup menu")
