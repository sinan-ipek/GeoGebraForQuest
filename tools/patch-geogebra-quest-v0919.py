#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.19 single-viewport stereo patch.

Render LEFT_EYE and RIGHT_EYE sequentially into the same W x H WebGL viewport.
Each completed pass is copied to its dedicated eye canvas at x=0. This removes
all dependence on a 2W backing store, right-half source coordinates, SBS crop
math, or quarter diagnostics.
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
        raise SystemExit("usage: patch-geogebra-quest-v0919.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    web = replace_once(
        web,
        "\t\t// GeoGebraForQuest v0.9.7: this build is permanently SBS.\n"
        "\t\t// Never let a transient UI/projection relayout collapse the WebGL\n"
        "\t\t// backing store to one eye; both halves always remain allocated.\n"
        "\t\tint backingWidth = (int) (w * ratio) * 2;\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "\t\t// GeoGebraForQuest v0.9.19: both stereo eyes render sequentially\n"
        "\t\t// into this same single-eye W x H viewport.\n"
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "restore single-eye WebGL backing width",
    )

    web = replace_once(
        web,
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// This Quest build always owns a two-eye backing store.\n"
        "\t\treturn eye * getWidthInPixels();\n"
        "\t}",
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// v0.9.19: LEFT_EYE and RIGHT_EYE both render at x=0.\n"
        "\t\treturn 0;\n"
        "\t}",
        "render both eyes into x=0 viewport",
    )

    web = replace_once(
        web,
        "\t\tint sourceX = eye == EYE_RIGHT ? eyeWidth : 0;\n"
        "\t\tglContext.flush();\n"
        "\t\tcontext.clearRect(0, 0, eyeWidth, eyeHeight);\n"
        "\t\tcontext.drawImage(source, sourceX, 0, eyeWidth, eyeHeight,",
        "\t\t// Both eye passes occupy the same viewport; no right-half crop.\n"
        "\t\tint sourceX = 0;\n"
        "\t\tglContext.finish();\n"
        "\t\tcontext.clearRect(0, 0, eyeWidth, eyeHeight);\n"
        "\t\tcontext.drawImage(source, sourceX, 0, eyeWidth, eyeHeight,",
        "capture both eye passes from x=0 after GPU completion",
    )

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.9.19 single viewport: {web_rel}")

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    quest = replace_once(
        quest,
        "        renderer.captureQuestEye(Renderer.EYE_LEFT);\n\n"
        "        renderer.eye = Renderer.EYE_RIGHT;\n"
        "        impl.clearDepthBuffer();",
        "        renderer.captureQuestEye(Renderer.EYE_LEFT);\n\n"
        "        // The right eye reuses the same W x H viewport. Clear the\n"
        "        // previous left-eye colour and depth before drawing it.\n"
        "        renderer.clearColorBuffer();\n"
        "        renderer.eye = Renderer.EYE_RIGHT;\n"
        "        impl.clearDepthBuffer();",
        "clear shared viewport before right eye",
    )

    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.9.19 single viewport: {quest_rel}")


if __name__ == "__main__":
    main()
