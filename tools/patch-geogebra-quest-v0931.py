#!/usr/bin/env python3
"""Exp13/15: native temporary right-grip rotate hooks only.

The exp13 experimental stereo ray continuation was removed in exp15 because the
thin white segment between Meta's native endpoint and GeoGebra's 3D cursor was
visually distracting. Grip temporary-mode behavior is retained unchanged.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0931.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()

controller_path = root / (
    "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
    "euclidian3D/EuclidianController3DW.java"
)
controller = controller_path.read_text(encoding="utf-8")

if "ggqBeginGripRotate" not in controller:
    import_anchor = "import org.jspecify.annotations.NonNull;\n\nimport elemental2.dom.WheelEvent;\n"
    import_insert = (
        "import org.jspecify.annotations.NonNull;\n"
        "import jsinterop.annotations.JsMethod;\n"
        "import jsinterop.annotations.JsPackage;\n\n"
        "import elemental2.dom.WheelEvent;\n"
    )
    if import_anchor not in controller:
        raise RuntimeError("exp13 3DW JsInterop import anchor not found")
    controller = controller.replace(import_anchor, import_insert, 1)

    field_anchor = "\tprivate MouseTouchGestureControllerW mtg;\n"
    field_insert = (
        "\tprivate MouseTouchGestureControllerW mtg;\n"
        "\tprivate static EuclidianController3DW ggqLastQuest3DController;\n"
        "\tprivate static boolean ggqGripRotateActive;\n"
    )
    if field_anchor not in controller:
        raise RuntimeError("exp13 3DW field anchor not found")
    controller = controller.replace(field_anchor, field_insert, 1)

    ctor_old = """\tpublic EuclidianController3DW(Kernel kernel) {\n\t\tsuper(kernel.getApplication());\n\t\tsetKernel(kernel);\n\t}\n"""
    hooks = r'''\tpublic EuclidianController3DW(Kernel kernel) {
\t\tsuper(kernel.getApplication());
\t\tsetKernel(kernel);
\t\tggqLastQuest3DController = this;
\t}

\t/** Begin a Quest right-grip temporary rotate without changing the toolbar tool permanently. */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqBeginGripRotate")
\tpublic static boolean ggqBeginGripRotate(double x, double y) {
\t\tEuclidianController3DW controller = ggqLastQuest3DController;
\t\tif (controller == null || controller.getView() == null) {
\t\t\treturn false;
\t\t}
\t\tcontroller.setMouseLocation(false, (int) Math.round(x), (int) Math.round(y));
\t\tif (!ggqGripRotateActive) {
\t\t\tcontroller.temporaryMode = true;
\t\t\tcontroller.oldMode = controller.mode;
\t\t\tcontroller.getView().setMode(EuclidianConstants.MODE_ROTATEVIEW);
\t\t\tcontroller.moveMode = MoveMode.ROTATE_VIEW;
\t\t\tcontroller.processPressForRotate3D(PointerEventType.MOUSE);
\t\t\tcontroller.startLoc = controller.mouseLoc;
\t\t\tcontroller.getView().rememberOrigins();
\t\t\tggqGripRotateActive = true;
\t\t}
\t\treturn true;
\t}

\t/** Update the temporary Quest right-grip rotation from the current panel pointer. */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqUpdateGripRotate")
\tpublic static boolean ggqUpdateGripRotate(double x, double y) {
\t\tEuclidianController3DW controller = ggqLastQuest3DController;
\t\tif (controller == null || controller.getView() == null || !ggqGripRotateActive) {
\t\t\treturn false;
\t\t}
\t\tcontroller.setMouseLocation(false, (int) Math.round(x), (int) Math.round(y));
\t\tcontroller.getView().setCoordSystemFromMouseMove(
\t\t\t\tcontroller.mouseLoc.x - controller.startLoc.x,
\t\t\t\tcontroller.mouseLoc.y - controller.startLoc.y,
\t\t\t\tMoveMode.ROTATE_VIEW);
\t\tcontroller.viewRotationOccurred = true;
\t\tcontroller.getView().repaintView();
\t\treturn true;
\t}

\t/** Release Quest right Grip and restore the exact tool that was active before the grip. */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqEndGripRotate")
\tpublic static boolean ggqEndGripRotate() {
\t\tEuclidianController3DW controller = ggqLastQuest3DController;
\t\tif (controller == null || controller.getView() == null) {
\t\t\tggqGripRotateActive = false;
\t\t\treturn false;
\t\t}
\t\tif (ggqGripRotateActive && controller.temporaryMode) {
\t\t\tcontroller.getView().setMode(
\t\t\t\t\tcontroller.oldMode, ModeSetter.EXIT_TEMPORARY_MODE);
\t\t\tcontroller.temporaryMode = false;
\t\t}
\t\tcontroller.moveMode = MoveMode.NONE;
\t\tcontroller.getView().repaintView();
\t\tggqGripRotateActive = false;
\t\treturn true;
\t}
'''
    if ctor_old not in controller:
        raise RuntimeError("exp13 3DW constructor anchor not found")
    controller = controller.replace(ctor_old, hooks, 1)
    controller_path.write_text(controller, encoding="utf-8")
    print("[GGQ] native right-grip temporary rotate hooks exported")
else:
    print("[GGQ] grip rotate hooks already present")

# Exp15 guard: the experimental white stereo continuation must not return.
renderer = (root / (
    "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
    "euclidian3D/openGL/Renderer.java"
)).read_text(encoding="utf-8")
view = (root / (
    "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
    "euclidian3D/EuclidianView3D.java"
)).read_text(encoding="utf-8")
for forbidden in (
    "EXP13_QUEST_MOUSE_RAY",
    "questMouseRayIndex",
    "questMouseRayEnd",
    "setQuestMouseRayEnd",
    "EXP13_DEPTH_RAY_CONTINUATION",
):
    if forbidden in renderer or forbidden in view:
        raise RuntimeError(f"exp15 white ray continuation residue must not exist: {forbidden}")
