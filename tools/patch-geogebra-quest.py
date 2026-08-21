#!/usr/bin/env python3
"""Patch a pinned upstream GeoGebra checkout for GeoGebraForQuest v0.9.3.

The Quest build deliberately reuses GeoGebra's *existing* GLASSES projection
identifier and stereo camera mathematics, but replaces the anaglyph output path
with two independent full-colour RGB eye passes written directly into a 2x-wide
SBS WebGL drawing buffer.

Why reuse PROJECTION_GLASSES instead of inventing a new projection enum?
GeoGebra has many internal branches that already understand GLASSES (picking,
cursor depth, eye distance, perspective setup, XML/settings). Reusing the known
projection keeps those paths intact and only swaps the final rendering policy.

No readPixels, JPEG, Base64, Bitmap or CPU eye-composition exists here.
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

        // Renderer.initRenderingValues() has already cleared the complete
        // 2W x H colour buffer once. Do NOT clear colour between eye passes:
        // glClear is not clipped by the viewport and would erase the left eye.
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        // Leave a deterministic state for the next frame / any following work.
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

    # Use a projection value GeoGebra already supports everywhere. This avoids
    # early-startup code encountering an unknown custom enum value.
    text = replace_once(
        text,
        "\tprivate int projection;",
        "\tprivate int projection = EuclidianView3DInterface.PROJECTION_GLASSES;",
        "default glasses projection",
    )

    # This Quest-specific build exposes no projection selector, so any XML or
    # restored setting that tries to change projection is folded back to the
    # built-in GLASSES value. The renderer below changes GLASSES *output* from
    # anaglyph to full-colour SBS.
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
    text = replace_once(
        text,
        "\tprivate int projection = PROJECTION_ORTHOGRAPHIC;",
        "\tprivate int projection = PROJECTION_GLASSES;",
        "view default glasses projection",
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
    patch_renderer(root)
    patch_web_renderer(root)
    patch_stylebar(root)
    patch_context_menu(root)
    patch_settings_ui(root)
    print("GeoGebra Quest full-colour SBS patch complete (built-in GLASSES projection reused)")


if __name__ == "__main__":
    main()
