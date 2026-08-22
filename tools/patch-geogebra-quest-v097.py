#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.7 stability patch.

Runs after the v0.9.6/v0.9.5 full-colour SBS source patch. This patch removes
transient projection-state dependencies from the WebGL backing-store layout so
UI relayouts (settings, axes/grid toggles, panels) cannot collapse the source
renderer from 2x-wide L|R SBS back to a single-width frame.
"""

from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-geogebra-quest-v097.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    text = web_path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\tif (isQuestStereo()) {\n"
        "\t\t\tbackingWidth *= 2;\n"
        "\t\t}\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "\t\t// GeoGebraForQuest v0.9.7: this build is permanently SBS.\n"
        "\t\t// Never let a transient UI/projection relayout collapse the WebGL\n"
        "\t\t// backing store to one eye; both halves always remain allocated.\n"
        "\t\tint backingWidth = (int) (w * ratio) * 2;\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "always keep 2x SBS backing width",
    )

    text = replace_once(
        text,
        "\tprivate boolean isQuestStereo() {\n"
        "\t\treturn view3D.getProjection()\n"
        "\t\t\t\t== EuclidianView3DInterface.PROJECTION_GLASSES;\n"
        "\t}\n\n"
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\treturn isQuestStereo() ? eye * getWidthInPixels() : 0;\n"
        "\t}",
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// This Quest build always owns a two-eye backing store.\n"
        "\t\treturn eye * getWidthInPixels();\n"
        "\t}",
        "always keep per-eye viewport offset",
    )

    web_path.write_text(text, encoding="utf-8")
    print(f"patched v0.9.7 stability: {web_rel}")

    stereo_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    stereo_path = root / stereo_rel
    stereo = stereo_path.read_text(encoding="utf-8")
    stereo = replace_once(
        stereo,
        "    public boolean isActive() {\n"
        "        return renderer.getView().getProjection()\n"
        "                == EuclidianView3DInterface.PROJECTION_GLASSES;\n"
        "    }",
        "    public boolean isActive() {\n"
        "        // v0.9.7: the Quest source build is permanently stereo.\n"
        "        // A transient UI relayout must never switch drawScene() back\n"
        "        // to the single-eye branch for even one persistent frame.\n"
        "        return true;\n"
        "    }",
        "keep Quest stereo draw path permanently active",
    )
    stereo_path.write_text(stereo, encoding="utf-8")
    print(f"patched v0.9.7 stability: {stereo_rel}")


if __name__ == "__main__":
    main()
