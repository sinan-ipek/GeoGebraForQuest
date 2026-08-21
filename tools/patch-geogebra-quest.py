#!/usr/bin/env python3
"""Patch an upstream GeoGebra source checkout for GeoGebraForQuest.

The Quest build gets a dedicated full-colour stereo projection.  It reuses
GeoGebra's proven left/right eye camera mathematics, but does *not* reuse the
anaglyph colour-mask path.  The WebGL drawing buffer is widened to SBS and the
left/right passes render directly into the two GPU viewports.

This file intentionally patches a pinned upstream revision rather than keeping
an entire fork of GeoGebra in this repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re


QUEST_STEREO_CLASS = r'''/*
 * GeoGebraForQuest source extension.
 *
 * This renderer is deliberately separate from GeoGebra's anaglyph branch.
 * The scene is rendered twice using GeoGebra's existing glasses camera math,
 * but both passes keep all RGBA colour channels and land in separate SBS
 * viewports in the same WebGL drawing buffer.
 */
package org.geogebra.common.geogebra3D.euclidian3D.openGL;

import org.geogebra.common.euclidian3D.EuclidianView3DInterface;

/** Full-colour left/right renderer used by the Quest build. */
public final class QuestStereoRenderer {

    private final Renderer renderer;

    /** @param renderer owning GeoGebra renderer */
    public QuestStereoRenderer(Renderer renderer) {
        this.renderer = renderer;
    }

    /** @return whether the dedicated Quest projection is active */
    public boolean isActive() {
        return renderer.getView().getProjection()
                == EuclidianView3DInterface.PROJECTION_QUEST_STEREO;
    }

    /**
     * Draw one complete stereo frame.
     *
     * No readPixels(), bitmap, JPEG, Base64 or CPU-side eye composition is
     * involved. RendererWithImplW supplies a 2x-wide GPU drawing buffer and
     * offsets the viewport according to renderer.eye.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();

        // Full colour for both eyes. This is the key difference from anaglyph.
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        // Leave renderer state predictable for picking / the following frame.
        impl.setColorMask(ColorMask.ALL);
        renderer.eye = Renderer.EYE_LEFT;
    }
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return out


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"patched: {rel}")


def patch_interface(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/euclidian3D/EuclidianView3DInterface.java"
    text = read(root, rel)
    text = replace_once(
        text,
        "    int PROJECTION_OBLIQUE = 3;",
        "    int PROJECTION_OBLIQUE = 3;\n"
        "    /** GeoGebraForQuest: full-colour SBS stereo projection. */\n"
        "    int PROJECTION_QUEST_STEREO = 4;",
        "projection constant",
    )
    write(root, rel, text)


def patch_settings(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/main/settings/EuclidianSettings3D.java"
    text = read(root, rel)
    text = replace_once(
        text,
        "\tprivate int projection;",
        "\tprivate int projection = EuclidianView3DInterface.PROJECTION_QUEST_STEREO;",
        "default Quest projection",
    )
    text = replace_regex_once(
        text,
        r"\tpublic void setProjection\(int projection\) \{\n\t\tif \(this\.projection != projection\) \{\n\t\t\tthis\.projection = projection;\n\t\t\tsettingChanged\(\);\n\t\t\}\n\t\}",
        "\tpublic void setProjection(int projection) {\n"
        "\t\t// Quest build has one projection: native full-colour stereo.\n"
        "\t\tint questProjection = EuclidianView3DInterface.PROJECTION_QUEST_STEREO;\n"
        "\t\tif (this.projection != questProjection) {\n"
        "\t\t\tthis.projection = questProjection;\n"
        "\t\t\tsettingChanged();\n"
        "\t\t}\n"
        "\t}",
        "force Quest projection in settings",
    )
    write(root, rel, text)


def patch_view(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/EuclidianView3D.java"
    text = read(root, rel)
    text = replace_once(
        text,
        "\tprivate int projection = PROJECTION_ORTHOGRAPHIC;",
        "\tprivate int projection = PROJECTION_QUEST_STEREO;",
        "view default projection",
    )
    text = replace_once(
        text,
        "\t\tcase PROJECTION_GLASSES:\n\t\t\tsetProjectionGlasses();\n\t\t\tbreak;\n\t\tcase PROJECTION_OBLIQUE:",
        "\t\tcase PROJECTION_GLASSES:\n\t\t\tsetProjectionGlasses();\n\t\t\tbreak;\n"
        "\t\tcase PROJECTION_QUEST_STEREO:\n\t\t\tsetProjectionQuestStereo();\n\t\t\tbreak;\n"
        "\t\tcase PROJECTION_OBLIQUE:",
        "Quest projection switch",
    )
    text = replace_once(
        text,
        "\tpublic void setProjectionGlasses() {\n"
        "\t\tupdateProjectionPerspectiveEyeDistance();\n"
        "\t\trenderer.updateGlassesValues();\n"
        "\t\tsetProjectionValues(PROJECTION_GLASSES);\n"
        "\t\tsetCursor(EuclidianCursor.TRANSPARENT);\n"
        "\t}",
        "\tpublic void setProjectionGlasses() {\n"
        "\t\tupdateProjectionPerspectiveEyeDistance();\n"
        "\t\trenderer.updateGlassesValues();\n"
        "\t\tsetProjectionValues(PROJECTION_GLASSES);\n"
        "\t\tsetCursor(EuclidianCursor.TRANSPARENT);\n"
        "\t}\n\n"
        "\t/** Set the GeoGebraForQuest full-colour stereo projection. */\n"
        "\tpublic void setProjectionQuestStereo() {\n"
        "\t\tupdateProjectionPerspectiveEyeDistance();\n"
        "\t\trenderer.updateGlassesValues();\n"
        "\t\tsetProjectionValues(PROJECTION_QUEST_STEREO);\n"
        "\t\tsetCursor(EuclidianCursor.TRANSPARENT);\n"
        "\t}",
        "Quest projection setter",
    )

    # Picking uses the same perspective eye model as glasses.
    text = text.replace(
        "projection == PROJECTION_PERSPECTIVE\n\t\t\t\t|| projection == PROJECTION_GLASSES",
        "projection == PROJECTION_PERSPECTIVE\n\t\t\t\t|| projection == PROJECTION_GLASSES\n"
        "\t\t\t\t|| projection == PROJECTION_QUEST_STEREO",
    )
    text = text.replace(
        "getProjection() == PROJECTION_GLASSES) {\n\t\t\tsetCursor(EuclidianCursor.TRANSPARENT)",
        "(getProjection() == PROJECTION_GLASSES\n"
        "\t\t\t\t|| getProjection() == PROJECTION_QUEST_STEREO)) {\n"
        "\t\t\tsetCursor(EuclidianCursor.TRANSPARENT)",
    )
    text = text.replace(
        "projection != PROJECTION_PERSPECTIVE\n\t\t\t\t&& projection != PROJECTION_GLASSES",
        "projection != PROJECTION_PERSPECTIVE\n\t\t\t\t&& projection != PROJECTION_GLASSES\n"
        "\t\t\t\t&& projection != PROJECTION_QUEST_STEREO",
    )
    text = text.replace(
        "if (projection == PROJECTION_GLASSES) { // also update",
        "if (projection == PROJECTION_GLASSES\n"
        "\t\t\t\t|| projection == PROJECTION_QUEST_STEREO) { // also update",
    )
    write(root, rel, text)


def patch_renderer(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/openGL/Renderer.java"
    text = read(root, rel)

    # One persistent module, no per-frame allocations.
    text = replace_once(
        text,
        "\tprivate RendererImpl rendererImpl;",
        "\tprivate RendererImpl rendererImpl;\n\tprivate QuestStereoRenderer questStereoRenderer;",
        "Quest renderer field",
    )
    text = replace_once(
        text,
        "\t\tthis.view3D = view;\n\t\tthis.type = type;\n\t\thitting = new Hitting(view3D);",
        "\t\tthis.view3D = view;\n\t\tthis.type = type;\n\t\thitting = new Hitting(view3D);\n"
        "\t\tquestStereoRenderer = new QuestStereoRenderer(this);",
        "Quest renderer construction",
    )

    text = replace_once(
        text,
        "\t\tif (view3D\n\t\t\t\t.getProjection() == EuclidianView3DInterface.PROJECTION_GLASSES) {",
        "\t\tif (questStereoRenderer != null && questStereoRenderer.isActive()) {\n"
        "\t\t\tquestStereoRenderer.drawStereoFrame();\n\n"
        "\t\t} else if (view3D\n\t\t\t\t.getProjection() == EuclidianView3DInterface.PROJECTION_GLASSES) {",
        "drawScene Quest branch",
    )
    text = replace_once(
        text,
        "\t\t\tcase EuclidianView3DInterface.PROJECTION_GLASSES:\n\t\t\t\trendererImpl.viewGlasses();\n\t\t\t\tbreak;",
        "\t\t\tcase EuclidianView3DInterface.PROJECTION_GLASSES:\n"
        "\t\t\tcase EuclidianView3DInterface.PROJECTION_QUEST_STEREO:\n"
        "\t\t\t\trendererImpl.viewGlasses();\n\t\t\t\tbreak;",
        "projection matrix Quest glasses math",
    )
    write(root, rel, text)

    class_rel = "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/openGL/QuestStereoRenderer.java"
    write(root, class_rel, QUEST_STEREO_CLASS)


def patch_web_renderer(root: Path) -> None:
    rel = "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/euclidian3D/openGL/RendererWithImplW.java"
    text = read(root, rel)

    # Add import only if the file does not already have it.
    marker = "import org.geogebra.common.geogebra3D.euclidian3D.EuclidianView3D;"
    text = replace_once(
        text,
        marker,
        marker + "\nimport org.geogebra.common.euclidian3D.EuclidianView3DInterface;",
        "web renderer Quest import",
    )

    # Keep the logical GeoGebra view W x H, but allocate a 2W x H WebGL
    # backing store for Quest. CSS size remains W x H.
    text = replace_once(
        text,
        "\t\twebGLCanvas.setCoordinateSpaceWidth((int) (w * ratio));",
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\tif (isQuestStereo()) {\n"
        "\t\t\tbackingWidth *= 2;\n"
        "\t\t}\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "double WebGL backing width",
    )

    # Insert the helpers immediately before the existing setView override.
    text = replace_once(
        text,
        "\t@Override\n\tpublic void setView(int x, int y, int w, int h) {",
        "\tprivate boolean isQuestStereo() {\n"
        "\t\treturn view3D.getProjection()\n"
        "\t\t\t\t== EuclidianView3DInterface.PROJECTION_QUEST_STEREO;\n"
        "\t}\n\n"
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\treturn isQuestStereo() ? eye * getWidthInPixels() : 0;\n"
        "\t}\n\n"
        "\t@Override\n\tpublic void setView(int x, int y, int w, int h) {",
        "Quest viewport offset helper",
    )
    write(root, rel, text)


def patch_stylebar(root: Path) -> None:
    rel = "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/euclidian3D/EuclidianStyleBar3DW.java"
    text = read(root, rel)

    text = text.replace("import java.util.ArrayList;\n\n", "")
    text = text.replace("import org.geogebra.common.main.settings.EuclidianSettings3D;\n", "")
    text = text.replace("import org.geogebra.web.resources.SVGResource;\n", "import org.geogebra.web.resources.SVGResource;\n")
    text = text.replace("\tprivate PopupMenuButtonW btnViewProjection;\n", "")

    text = replace_regex_once(
        text,
        r"\n\t\tImageOrText\[\] projectionIcons = ImageOrText\.convert\(.*?\n\t\tsetPopupHandlerWithUndoPoint\(btnViewProjection, this::updateProjection\);",
        "",
        "remove projection popup creation",
    )
    text = replace_regex_once(
        text,
        r"\n\tprivate boolean updateProjection\(ArrayList<GeoElement> ignored\) \{.*?\n\t\}",
        "",
        "remove projection popup handler",
    )
    text = replace_once(
        text,
        "\tprotected void addBtnRotateView() {\n\t\tadd(btnViewProjection);\n\t\tadd(btnRotateView);\n\t}",
        "\tprotected void addBtnRotateView() {\n\t\tadd(btnRotateView);\n\t}",
        "remove toolbar projection cube without gap",
    )
    text = text.replace(
        "\n\t\tbtnViewProjection.setTitle(loc\n\t\t\t\t.getPlainTooltip(\"stylebar.ViewProjection\"));",
        "",
    )

    # Replace the 3D popup tracking list; compact array means no invisible gap.
    text = replace_regex_once(
        text,
        r"\t@Override\n\tprotected PopupMenuButtonW\[\] newPopupBtnList\(\) \{.*?\n\t\}",
        "\t@Override\n"
        "\tprotected PopupMenuButtonW[] newPopupBtnList() {\n"
        "\t\tPopupMenuButtonW[] superList = super.newPopupBtnList();\n"
        "\t\tPopupMenuButtonW[] ret = new PopupMenuButtonW[superList.length + 1];\n\n"
        "\t\t// Base list ends with change-view; place rotate directly before it.\n"
        "\t\tfor (int i = 0; i < superList.length - 1; i++) {\n"
        "\t\t\tret[i] = superList[i];\n"
        "\t\t}\n"
        "\t\tint index = superList.length - 1;\n"
        "\t\tret[index++] = btnRotateView;\n"
        "\t\tret[index] = btnChangeView;\n"
        "\t\treturn ret;\n"
        "\t}",
        "compact 3D popup list",
    )
    write(root, rel, text)


def patch_context_menu(root: Path) -> None:
    rel = "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/gui/ContextMenuGraphicsWindow3DW.java"
    text = read(root, rel)
    text = text.replace("import static org.geogebra.common.properties.PropertyView.*;\n\n", "")
    text = text.replace("import org.geogebra.common.properties.impl.graphics.ProjectionsProperty;\n", "")
    text = text.replace("import org.geogebra.web.full.gui.properties.ui.panel.IconButtonPanel;\n", "")
    text = text.replace("import org.geogebra.web.html5.gui.menu.AriaMenuItem;\n", "")
    text = text.replace("\t\taddProjectionMenuItem();\n", "")
    text = replace_regex_once(
        text,
        r"\n\tprivate void addProjectionMenuItem\(\) \{.*?\n\t\}",
        "",
        "remove context projection menu",
    )
    write(root, rel, text)


def patch_settings_ui(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/properties/factory/DefaultPropertiesFactory.java"
    text = read(root, rel)
    text = text.replace("import org.geogebra.common.properties.impl.graphics.ProjectionPropertyCollection;\n", "")
    text = replace_once(
        text,
        "\t\t\t\t\t\tnew ProjectionPropertyCollection(app, localization,\n"
        "\t\t\t\t\t\t\t\t(EuclidianSettings3D) euclidianSettings),\n",
        "",
        "remove projection settings collection",
    )
    write(root, rel, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("geogebra_root", type=Path)
    args = parser.parse_args()
    root = args.geogebra_root.resolve()

    if not (root / "source" / "web").is_dir():
        raise SystemExit(f"Not a GeoGebra checkout: {root}")

    patch_interface(root)
    patch_settings(root)
    patch_view(root)
    patch_renderer(root)
    patch_web_renderer(root)
    patch_stylebar(root)
    patch_context_menu(root)
    patch_settings_ui(root)
    print("GeoGebra Quest source patch complete")


if __name__ == "__main__":
    main()
