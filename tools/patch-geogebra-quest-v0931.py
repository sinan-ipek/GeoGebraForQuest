#!/usr/bin/env python3
"""Exp13: stereo ray continuation + native temporary grip rotate hooks.

1. Draw a thin stereo ray continuation from the flat panel intersection to
   GeoGebra's existing glasses mouse cursor when that cursor has real 3D depth.
2. Export native begin/update/end hooks for a right-grip temporary rotate mode.
   The previous GeoGebra tool is restored with EXIT_TEMPORARY_MODE on release.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0931.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()

# ---------------------------------------------------------------------------
# Renderer: reusable screen-space tube drawn with the same glasses transform
# as GeoGebra's mouse cursor.
# ---------------------------------------------------------------------------
renderer_path = root / (
    "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
    "euclidian3D/openGL/Renderer.java"
)
renderer = renderer_path.read_text(encoding="utf-8")

if "EXP13_QUEST_MOUSE_RAY" not in renderer:
    field_anchor = "\tprivate Hitting hitting;\n"
    field_insert = (
        "\tprivate Hitting hitting;\n"
        "\n"
        "\t// EXP13_QUEST_MOUSE_RAY: continuation from A's flat hit plane to the\n"
        "\t// stereoscopic GeoGebra mouse cursor at the actual picked depth.\n"
        "\tprivate int questMouseRayIndex = -1;\n"
        "\tprivate Coords questMouseRayEnd;\n"
        "\tprivate final Coords questMouseRayOrigin = new Coords(0, 0, 0, 1);\n"
    )
    if field_anchor not in renderer:
        raise RuntimeError("exp13 renderer field anchor not found")
    renderer = renderer.replace(field_anchor, field_insert, 1)

    method_anchor = """\t/**\n\t * draws mouse cursor\n\t */\n\tpublic void drawMouseCursor() {\n"""
    method_insert = """\t/**\n\t * Set the local screen-space endpoint for the Quest stereo ray continuation.\n\t * Null disables the continuation for the current cursor draw.\n\t * @param end endpoint relative to the depth-correct mouse cursor\n\t */\n\tpublic void setQuestMouseRayEnd(Coords end) {\n\t\tquestMouseRayEnd = end;\n\t}\n\n\t/**\n\t * draws mouse cursor\n\t */\n\tpublic void drawMouseCursor() {\n"""
    if method_anchor not in renderer:
        raise RuntimeError("exp13 renderer drawMouseCursor anchor not found")
    renderer = renderer.replace(method_anchor, method_insert, 1)

    draw_anchor = "\t\tgeometryManager.draw(geometryManager.getMouseCursor().getIndex());\n"
    draw_insert = """\t\tif (questMouseRayEnd != null) {\n\t\t\tPlotterBrush brush = geometryManager.getBrush();\n\t\t\tgeometryManager.setScalerIdentity();\n\t\t\tbrush.start(questMouseRayIndex);\n\t\t\tbrush.setThickness(1.35f);\n\t\t\tbrush.segment(questMouseRayOrigin, questMouseRayEnd);\n\t\t\tquestMouseRayIndex = brush.end();\n\t\t\tgeometryManager.setScalerView();\n\t\t\trendererImpl.setColor(1f, 1f, 1f, 0.92f);\n\t\t\tgeometryManager.draw(questMouseRayIndex);\n\t\t}\n\t\tgeometryManager.draw(geometryManager.getMouseCursor().getIndex());\n"""
    if draw_anchor not in renderer:
        raise RuntimeError("exp13 renderer cursor geometry anchor not found")
    renderer = renderer.replace(draw_anchor, draw_insert, 1)
    renderer_path.write_text(renderer, encoding="utf-8")
    print("[GGQ] exp13 stereo mouse-ray continuation installed in Renderer")
else:
    print("[GGQ] exp13 Renderer ray continuation already present")

# ---------------------------------------------------------------------------
# EuclidianView3D: calculate the flat-panel point and depth-correct cursor point
# in the same per-eye screen coordinate system. The ray geometry is expressed
# relative to v because Renderer.drawMouseCursor() already draws face-to-screen
# geometry with its matrix origin at v.
# ---------------------------------------------------------------------------
view_path = root / (
    "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
    "euclidian3D/EuclidianView3D.java"
)
view = view_path.read_text(encoding="utf-8")
if "EXP13_DEPTH_RAY_CONTINUATION" not in view:
    old = """\tpublic void drawMouseCursor(Renderer renderer1, Coords v) {\n\t\tCoordMatrix4x4.identity(tmpMatrix4x4_3);\n\n\t\ttmpMatrix4x4_3.setOrigin(v);\n\t\trenderer1.setMatrix(tmpMatrix4x4_3);\n\t\trenderer1.drawMouseCursor();\n\t}\n"""
    new = """\tpublic void drawMouseCursor(Renderer renderer1, Coords v) {\n\t\tCoordMatrix4x4.identity(tmpMatrix4x4_3);\n\n\t\ttmpMatrix4x4_3.setOrigin(v);\n\t\trenderer1.setMatrix(tmpMatrix4x4_3);\n\n\t\t// EXP13_DEPTH_RAY_CONTINUATION: Meta's native beam physically ends on A,\n\t\t// but in the stereo image continue it from that z=0 screen point to the\n\t\t// same depth-correct GeoGebra cursor that already sticks to the picked 3D object.\n\t\tGPoint mouseLoc = getEuclidianController().getMouseLoc();\n\t\tif (mouseLoc != null && getCursor3DType() != CURSOR_DEFAULT) {\n\t\t\tCoords panelPoint = new Coords(\n\t\t\t\t\tmouseLoc.x + renderer1.getLeft(),\n\t\t\t\t\t-mouseLoc.y + renderer1.getTop(), 0, 1);\n\t\t\tCoords localRayEnd = panelPoint.sub(v);\n\t\t\tlocalRayEnd.setW(0);\n\t\t\trenderer1.setQuestMouseRayEnd(localRayEnd);\n\t\t} else {\n\t\t\trenderer1.setQuestMouseRayEnd(null);\n\t\t}\n\n\t\trenderer1.drawMouseCursor();\n\t}\n"""
    if old not in view:
        raise RuntimeError("exp13 EuclidianView3D mouse cursor anchor not found")
    view = view.replace(old, new, 1)
    view_path.write_text(view, encoding="utf-8")
    print("[GGQ] exp13 depth-correct ray continuation wired to glasses cursor")
else:
    print("[GGQ] exp13 EuclidianView3D ray continuation already present")

# ---------------------------------------------------------------------------
# Web 3D controller: native temporary-mode hooks for right Grip.
# ---------------------------------------------------------------------------
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
    hooks = r'''	public EuclidianController3DW(Kernel kernel) {
		super(kernel.getApplication());
		setKernel(kernel);
		ggqLastQuest3DController = this;
	}

	/** Begin a Quest right-grip temporary rotate without changing the toolbar tool permanently. */
	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqBeginGripRotate")
	public static boolean ggqBeginGripRotate(double x, double y) {
		EuclidianController3DW controller = ggqLastQuest3DController;
		if (controller == null || controller.getView() == null) {
			return false;
		}
		controller.setMouseLocation(false, (int) Math.round(x), (int) Math.round(y));
		if (!ggqGripRotateActive) {
			controller.temporaryMode = true;
			controller.oldMode = controller.mode;
			controller.getView().setMode(EuclidianConstants.MODE_ROTATEVIEW);
			controller.moveMode = MoveMode.ROTATE_VIEW;
			controller.processPressForRotate3D(PointerEventType.MOUSE);
			controller.startLoc = controller.mouseLoc;
			controller.getView().rememberOrigins();
			ggqGripRotateActive = true;
		}
		return true;
	}

	/** Update the temporary Quest right-grip rotation from the current panel pointer. */
	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqUpdateGripRotate")
	public static boolean ggqUpdateGripRotate(double x, double y) {
		EuclidianController3DW controller = ggqLastQuest3DController;
		if (controller == null || controller.getView() == null || !ggqGripRotateActive) {
			return false;
		}
		controller.setMouseLocation(false, (int) Math.round(x), (int) Math.round(y));
		controller.getView().setCoordSystemFromMouseMove(
				controller.mouseLoc.x - controller.startLoc.x,
				controller.mouseLoc.y - controller.startLoc.y,
				MoveMode.ROTATE_VIEW);
		controller.viewRotationOccurred = true;
		controller.getView().repaintView();
		return true;
	}

	/** Release Quest right Grip and restore the exact tool that was active before the grip. */
	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqEndGripRotate")
	public static boolean ggqEndGripRotate() {
		EuclidianController3DW controller = ggqLastQuest3DController;
		if (controller == null || controller.getView() == null) {
			ggqGripRotateActive = false;
			return false;
		}
		if (ggqGripRotateActive && controller.temporaryMode) {
			controller.getView().setMode(
					controller.oldMode, ModeSetter.EXIT_TEMPORARY_MODE);
			controller.temporaryMode = false;
		}
		controller.moveMode = MoveMode.NONE;
		controller.getView().repaintView();
		ggqGripRotateActive = false;
		return true;
	}
'''
    if ctor_old not in controller:
        raise RuntimeError("exp13 3DW constructor anchor not found")
    controller = controller.replace(ctor_old, hooks, 1)
    controller_path.write_text(controller, encoding="utf-8")
    print("[GGQ] exp13 native right-grip temporary rotate hooks exported")
else:
    print("[GGQ] exp13 grip rotate hooks already present")
