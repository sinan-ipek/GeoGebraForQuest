#!/usr/bin/env python3
"""Exp46: arm temporary Move on the Euclidian view hit by Grip.

GeoGebra normally changes the active Euclidian dock panel inside
``wrapMousePressed``.  Exp44 selected Move before that press, so the mode was
applied to the previously active view.  The first Grip press on another view
could consequently execute that view's old tool.

This patch arms the synthetic Grip press first.  Immediately after GeoGebra
focuses the actual pointer target, and before hit/tool processing, that exact
controller enters temporary Move.  Mouse release (or the explicit cancel
bridge) restores the mode that was active before Grip.
"""

from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0937.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
controller_path = root / (
    "source/shared/common/src/main/java/org/geogebra/common/euclidian/"
    "EuclidianController.java"
)
web_controller_path = root / (
    "source/web/web-common/src/main/java/org/geogebra/web/html5/euclidian/"
    "EuclidianControllerW.java"
)

controller = controller_path.read_text(encoding="utf-8")
web_controller = web_controller_path.read_text(encoding="utf-8")

if "GGQ_EXP46_TARGET_VIEW_GRIP_MOVE" in controller:
    print("[GGQ] exp46 target-view Grip focus already present")
    raise SystemExit(0)

field_anchor = "\tprotected boolean temporaryMode = false;\n"
field_insert = """\tprotected boolean temporaryMode = false;

\t// GGQ_EXP46_TARGET_VIEW_GRIP_MOVE: state shared only for the single
\t// synthetic Quest Grip pointer stream.
\tprivate static boolean ggqGripMoveArmed;
\tprivate static int ggqGripMoveOldMode = EuclidianConstants.MODE_MOVE;
\tprivate static EuclidianController ggqGripMoveController;
"""
controller = replace_once(
    controller, field_anchor, field_insert, "Exp46 Grip state fields"
)

method_anchor = """\t/**
\t * Handle pointer down event.
\t *
\t * @param event
\t *            pointer event
\t */
\tpublic void wrapMousePressed(AbstractEvent event) {
"""
method_insert = """\t/** Arm the next Euclidian press as a Quest temporary Move. */
\tpublic static boolean armQuestGripMove(int previousMode) {
\t\tendQuestGripMove();
\t\tggqGripMoveOldMode = previousMode;
\t\tggqGripMoveArmed = true;
\t\treturn true;
\t}

\t/** Restore a Quest Grip mode even when Android cancelled the pointer. */
\tpublic static boolean endQuestGripMove() {
\t\tggqGripMoveArmed = false;
\t\tEuclidianController controller = ggqGripMoveController;
\t\tggqGripMoveController = null;
\t\tif (controller == null || controller.getView() == null) {
\t\t\treturn false;
\t\t}
\t\t// Mouse-release may already have exited temporary mode, and GeoGebra's
\t\t// own background-drag logic may also have overwritten controller.oldMode.
\t\t// Always restore our separately captured pre-Grip tool.
\t\tcontroller.getView().setMode(
\t\t\t\tggqGripMoveOldMode, ModeSetter.EXIT_TEMPORARY_MODE);
\t\tcontroller.temporaryMode = false;
\t\tcontroller.moveMode = MoveMode.NONE;
\t\tcontroller.getView().repaintView();
\t\treturn true;
\t}

\tprivate void activateArmedQuestGripMove() {
\t\tif (!ggqGripMoveArmed) {
\t\t\treturn;
\t\t}
\t\tggqGripMoveArmed = false;
\t\tggqGripMoveController = this;
\t\ttemporaryMode = true;
\t\toldMode = ggqGripMoveOldMode;
\t\tview.setMode(EuclidianConstants.MODE_MOVE, ModeSetter.DOCK_PANEL);
\t}

\t/**
\t * Handle pointer down event.
\t *
\t * @param event
\t *            pointer event
\t */
\tpublic void wrapMousePressed(AbstractEvent event) {
"""
controller = replace_once(
    controller, method_anchor, method_insert, "Exp46 Grip lifecycle methods"
)

focus_anchor = """\t\tsetMouseLocation(event);
\t\tupdateFocusedPanel(event);

\t\tupdateHits(event);
"""
focus_insert = """\t\tsetMouseLocation(event);
\t\tupdateFocusedPanel(event);
\t\t// Exp46: focus has identified the ray target. Switch that controller
\t\t// before updateHits/switchModeForMousePressed can execute its old tool.
\t\tactivateArmedQuestGripMove();

\t\tupdateHits(event);
"""
controller = replace_once(
    controller, focus_anchor, focus_insert, "Exp46 post-focus Move activation"
)

export_anchor = """\t/**
\t * Quest-only bridge: invoke GeoGebra's own long-touch/right-click path.
"""
export_insert = """\t/** Arm the next native WebView press for target-view temporary Move. */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqArmGripMoveForNextPress")
\tpublic static boolean ggqArmGripMoveForNextPress(double previousMode) {
\t\tEuclidianControllerW controller = ggqLastController;
\t\tif (controller == null || controller.app == null
\t\t\t\t|| !Double.isFinite(previousMode)) {
\t\t\treturn false;
\t\t}
\t\treturn EuclidianController.armQuestGripMove((int) Math.round(previousMode));
\t}

\t/** Cancel or finish the target-view temporary Move. */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqEndGripMoveForTargetView")
\tpublic static boolean ggqEndGripMoveForTargetView() {
\t\treturn EuclidianController.endQuestGripMove();
\t}

\t/**
\t * Quest-only bridge: invoke GeoGebra's own long-touch/right-click path.
"""
web_controller = replace_once(
    web_controller, export_anchor, export_insert, "Exp46 global Grip bridge"
)

for required in (
    "GGQ_EXP46_TARGET_VIEW_GRIP_MOVE",
    "activateArmedQuestGripMove();",
    "view.setMode(EuclidianConstants.MODE_MOVE, ModeSetter.DOCK_PANEL)",
    "ggqArmGripMoveForNextPress",
    "ggqEndGripMoveForTargetView",
):
    if required not in controller + web_controller:
        raise RuntimeError(f"exp46 source requirement missing: {required}")

controller_path.write_text(controller, encoding="utf-8")
web_controller_path.write_text(web_controller, encoding="utf-8")
print("[GGQ] exp46 target-view Grip focus/temporary Move bridge installed")
