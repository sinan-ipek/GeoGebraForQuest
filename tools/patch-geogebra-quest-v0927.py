#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0927.py <geogebra-source-root>")

root = Path(sys.argv[1])
path = root / "source/web/web-common/src/main/java/org/geogebra/web/html5/euclidian/EuclidianControllerW.java"
text = path.read_text(encoding="utf-8")

if "ggqOpenContextMenu" in text:
    print("[GGQ] v0.9.27 context-menu hook already present")
    raise SystemExit(0)

imports_anchor = "import elemental2.dom.WheelEvent;\n"
if imports_anchor not in text:
    raise SystemExit("[GGQ] v0.9.27 imports anchor not found")
text = text.replace(
    imports_anchor,
    imports_anchor + "import jsinterop.annotations.JsMethod;\nimport jsinterop.annotations.JsPackage;\n",
    1,
)

field_anchor = "\tprivate MouseTouchGestureControllerW mtg;\n"
if field_anchor not in text:
    raise SystemExit("[GGQ] v0.9.27 field anchor not found")
text = text.replace(
    field_anchor,
    field_anchor + "\tprivate static EuclidianControllerW ggqLastController;\n",
    1,
)

ctor_old = """\tpublic EuclidianControllerW(Kernel kernel) {\n\t\tsuper(kernel.getApplication());\n\t\tsetKernel(kernel);\n\t}\n"""
ctor_new = """\tpublic EuclidianControllerW(Kernel kernel) {\n\t\tsuper(kernel.getApplication());\n\t\tsetKernel(kernel);\n\t\tggqLastController = this;\n\t}\n\n\t/**\n\t * Quest-only bridge: invoke GeoGebra's own long-touch/right-click path.\n\t * Coordinates are relative to the active Euclidian view.\n\t *\n\t * @param x view-local x coordinate\n\t * @param y view-local y coordinate\n\t * @return whether a controller was available\n\t */\n\t@JsMethod(namespace = JsPackage.GLOBAL, name = \"ggqOpenContextMenu\")\n\tpublic static boolean ggqOpenContextMenu(double x, double y) {\n\t\tEuclidianControllerW controller = ggqLastController;\n\t\tif (controller == null || controller.app == null) {\n\t\t\treturn false;\n\t\t}\n\n\t\tEuclidianView activeView = controller.app.getActiveEuclidianView();\n\t\tif (activeView != null\n\t\t\t\t&& activeView.getEuclidianController() instanceof EuclidianControllerW) {\n\t\t\tcontroller = (EuclidianControllerW) activeView.getEuclidianController();\n\t\t}\n\n\t\tcontroller.handleLongTouch(x, y);\n\t\treturn true;\n\t}\n\n\t/**\n\t * Quest-only bridge: close the active GeoGebra popup/context menu.\n\t *\n\t * @return whether the close request was handled\n\t */\n\t@JsMethod(namespace = JsPackage.GLOBAL, name = \"ggqCloseContextMenu\")\n\tpublic static boolean ggqCloseContextMenu() {\n\t\tEuclidianControllerW controller = ggqLastController;\n\t\tif (controller == null || controller.app == null) {\n\t\t\treturn false;\n\t\t}\n\n\t\tAppW appW = (AppW) controller.app;\n\t\tif (appW.getGuiManager() == null) {\n\t\t\treturn false;\n\t\t}\n\n\t\tappW.getGuiManager().removePopup();\n\t\treturn true;\n\t}\n"""
if ctor_old not in text:
    raise SystemExit("[GGQ] v0.9.27 constructor anchor not found")
text = text.replace(ctor_old, ctor_new, 1)

path.write_text(text, encoding="utf-8")
print("[GGQ] v0.9.27 exported native GeoGebra context-menu hooks")
