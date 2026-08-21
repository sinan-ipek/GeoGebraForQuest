#!/usr/bin/env python3
"""Patch a pinned upstream GeoGebra checkout for GeoGebraForQuest v0.9.5.

This Quest build deliberately reuses GeoGebra's existing PROJECTION_GLASSES
camera, picking and cursor-depth mathematics, but completely removes the
anaglyph output policy. The two eyes are rendered as independent full-colour
RGB passes directly into the two halves of one 2x-wide WebGL drawing buffer.

Important consequences:
- no grayscale conversion
- no red/cyan color masks
- no readPixels / JPEG / Base64 / Bitmap pipeline
- no CPU-side L/R composition
- GeoGebra's ordinary 3D hit-test and cursor rendering stay intact
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re


QUEST_STEREO_CLASS = r'''/*
 * GeoGebraForQuest source extension.
 *
 * Full-colour SBS replacement for GeoGebra's anaglyph output. The existing
 * PROJECTION_GLASSES camera / hit-test / cursor-depth maths is intentionally
 * retained, but both eye passes keep all RGBA channels and render directly
 * into independent halves of one GPU drawing buffer.
 */
package org.geogebra.common.geogebra3D.euclidian3D.openGL;

import org.geogebra.common.euclidian3D.EuclidianView3DInterface;

/** Quest full-colour left/right renderer. */
public final class QuestStereoRenderer {

    private final Renderer renderer;

    /** @param renderer owning GeoGebra renderer */
    public QuestStereoRenderer(Renderer renderer) {
        this.renderer = renderer;
    }

    /** @return whether the Quest build's stereo projection is active */
    public boolean isActive() {
        return renderer.getView().getProjection()
                == EuclidianView3DInterface.PROJECTION_GLASSES;
    }

    /** Draw one complete full-colour SBS frame. */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();

        // Renderer.initRenderingValues() cleared the complete 2W x H colour
        // buffer once. Do not clear colour between the passes: glClear is not
        // clipped to a viewport and could erase the eye already rendered.
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        // Deterministic state for the next frame and any work following it.
        impl.setColorMask(ColorMask.ALL);
        renderer.eye = Renderer.EYE_LEFT;
        renderer.setView();
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


def patch_settings(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/main/settings/EuclidianSettings3D.java"
    text = read(root, rel)

    # The settings object starts in a projection GeoGebra already knows. The
    # view will receive it through its normal settingsChanged() path, which in
    # turn calls setProjectionGlasses() and initializes eye distance/matrices.
    text = replace_once(
        text,
        "\tprivate int projection;",
        "\tprivate int projection = EuclidianView3DInterface.PROJECTION_GLASSES;",
        "default glasses projection",
    )

    # This Quest-specific build has no projection selector. Any restored XML or
    # external request is folded back to the known GLASSES projection value.
    text = replace_regex_once(
        text,
        r"\tpublic void setProjection\(int projection\) \{\n\t\tif \(this\.projection != projection\) \{\n\t\t\tthis\.projection = projection;\n\t\t\tsettingChanged\(\);\n\t\t\}\n\t\}",
        "\tpublic void setProjection(int projection) {\n"
        "\t\tint questProjection = EuclidianView3DInterface.PROJECTION_GLASSES;\n"
        "\t\tif (this.projection != questProjection) {\n"
        "\t\t\tthis.projection = questProjection;\n"
        "\t\t\tsettingChanged();\n"
        "\t\t}\n"
        "\t}",
        "force built-in glasses projection",
    )
    write(root, rel, text)


def patch_view(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/EuclidianView3D.java"
    text = read(root, rel)

    # Do NOT change the projection field initializer. Starting the field as
    # GLASSES bypasses setProjectionGlasses(), which is responsible for setting
    # the perspective eye distance and updating left/right eye coordinates.
    # Instead the normal settings path selects GLASSES, and the Web constructor
    # below repeats setProjectionGlasses() after renderer.init() as a guarantee.

    text = replace_regex_once(
        text,
        r"\tpublic boolean isGrayScaled\(\) \{\n\t\treturn projection == PROJECTION_GLASSES\n\t\t\t\t&& !isXREnabled\(\)\n\t\t\t\t&& !getCompanion\(\)\.isStereoBuffered\(\)\n\t\t\t\t&& isGlassesGrayScaled\(\);\n\t\}",
        "\tpublic boolean isGrayScaled() {\n"
        "\t\t// Quest stereo keeps the original object colours.\n"
        "\t\treturn false;\n"
        "\t}",
        "disable anaglyph grayscale",
    )

    text = replace_once(
        text,
        "\tpublic boolean isShutDownGreen() {\n\t\treturn projection == PROJECTION_GLASSES && isGlassesShutDownGreen();\n\t}",
        "\tpublic boolean isShutDownGreen() {\n"
        "\t\t// Quest stereo never removes the green channel.\n"
        "\t\treturn false;\n"
        "\t}",
        "disable anaglyph green shutdown",
    )
    write(root, rel, text)


def patch_web_view_startup(root: Path) -> None:
    rel = "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/euclidian3D/EuclidianView3DW.java"
    text = read(root, rel)
    text = replace_once(
        text,
        "\t\tgetRenderer().init();\n\t\tinitAriaDefaults();",
        "\t\tgetRenderer().init();\n"
        "\t\t// Quest build: initialize the existing stereo camera through the\n"
        "\t\t// real GeoGebra path, after the renderer itself is initialized.\n"
        "\t\tsetProjectionGlasses();\n"
        "\t\tinitAriaDefaults();",
        "initialize glasses projection after renderer init",
    )
    write(root, rel, text)


def patch_renderer(root: Path) -> None:
    rel = "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/openGL/Renderer.java"
    text = read(root, rel)

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

    old_glasses_block = (
        "\t\tif (view3D\n"
        "\t\t\t\t.getProjection() == EuclidianView3DInterface.PROJECTION_GLASSES) {\n\n"
        "\t\t\t// left eye\n"
        "\t\t\tsetDrawLeft();\n"
        "\t\t\trendererImpl.clearDepthBuffer();\n"
        "\t\t\tsetView();\n"
        "\t\t\tdraw();\n\n"
        "\t\t\t// right eye\n"
        "\t\t\tsetDrawRight();\n"
        "\t\t\trendererImpl.clearDepthBufferForSecondAnaglyphFilter();\n"
        "\t\t\tsetView();\n"
        "\t\t\tdraw();\n\n"
        "\t\t} else {"
    )
    new_glasses_block = (
        "\t\tif (questStereoRenderer != null && questStereoRenderer.isActive()) {\n"
        "\t\t\tquestStereoRenderer.drawStereoFrame();\n\n"
        "\t\t} else {"
    )
    text = replace_once(
        text,
        old_glasses_block,
        new_glasses_block,
        "replace anaglyph draw loop with full-colour SBS",
    )

    # The ordinary draw pipeline calls setColorMask() again while rendering
    # hiding surfaces. Therefore changing only the outer eye loop is not enough:
    # the anaglyph red/cyan mask must be removed at the source.
    text = replace_regex_once(
        text,
        r"\tprotected void setColorMask\(\) \{\n\t\tif \(view3D.*?\n\t\}\n\n\t/\*\*\n\t \* export type",
        "\tprotected void setColorMask() {\n"
        "\t\t// Quest stereo renders both eyes in full RGBA.\n"
        "\t\trendererImpl.setColorMask(ColorMask.ALL);\n"
        "\t}\n\n"
        "\t/**\n\t * export type",
        "disable red/cyan color masks",
    )

    # The original Glasses background is grayscale (and may suppress green).
    # Keep the real GeoGebra background colour instead.
    text = replace_regex_once(
        text,
        r"\tprivate void updateClearColor\(\) \{\n\t\tif \(transparent\) \{.*?\n\t\trendererImpl\.setClearColor\(r, g, b, 1\.0f\);\n\t\}",
        "\tprivate void updateClearColor() {\n"
        "\t\tif (transparent) {\n"
        "\t\t\trendererImpl.setClearColor(0, 0, 0, 0f);\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\tGColor c = view3D.getAppliedBackground();\n"
        "\t\tfloat r = (float) c.getRed() / 255;\n"
        "\t\tfloat g = (float) c.getGreen() / 255;\n"
        "\t\tfloat b = (float) c.getBlue() / 255;\n"
        "\t\trendererImpl.setClearColor(r, g, b, 1.0f);\n"
        "\t}",
        "keep full-colour background",
    )

    write(root, rel, text)
    write(
        root,
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/euclidian3D/openGL/QuestStereoRenderer.java",
        QUEST_STEREO_CLASS,
    )


def patch_web_renderer(root: Path) -> None:
    rel = "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/euclidian3D/openGL/RendererWithImplW.java"
    text = read(root, rel)

    marker = "import org.geogebra.common.geogebra3D.euclidian3D.EuclidianView3D;"
    text = replace_once(
        text,
        marker,
        "import org.geogebra.common.euclidian3D.EuclidianView3DInterface;\n" + marker,
        "web renderer glasses import",
    )

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

    text = replace_once(
        text,
        "\t@Override\n\tpublic void setView(int x, int y, int w, int h) {",
        "\tprivate boolean isQuestStereo() {\n"
        "\t\treturn view3D.getProjection()\n"
        "\t\t\t\t== EuclidianView3DInterface.PROJECTION_GLASSES;\n"
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
    text = replace_regex_once(
        text,
        r"\t@Override\n\tprotected PopupMenuButtonW\[\] newPopupBtnList\(\) \{.*?\n\t\}",
        "\t@Override\n"
        "\tprotected PopupMenuButtonW[] newPopupBtnList() {\n"
        "\t\tPopupMenuButtonW[] superList = super.newPopupBtnList();\n"
        "\t\tPopupMenuButtonW[] ret = new PopupMenuButtonW[superList.length + 1];\n\n"
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

    patch_settings(root)
    patch_view(root)
    patch_web_view_startup(root)
    patch_renderer(root)
    patch_web_renderer(root)
    patch_stylebar(root)
    patch_context_menu(root)
    patch_settings_ui(root)
    print("GeoGebra Quest v0.9.5 full-colour SBS patch complete")


if __name__ == "__main__":
    main()
