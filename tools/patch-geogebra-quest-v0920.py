#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.20 right-eye snapshot reuse patch.

After the v0.9.19 single-viewport stereo renderer finishes a frame, the shared
WebGL canvas contains the completed RIGHT_EYE image because RIGHT_EYE is the
second and final draw pass. The left eye must still be snapshotted before that
shared viewport is cleared, but taking a second renderer-level RIGHT_EYE
snapshot only adds another gl.finish() and WebGL-to-2D-canvas copy.

This patch removes that redundant RIGHT_EYE capture hook and makes the existing
`ggq-renderer-right-eye` DOM lookup resolve to GeoGebra's main WebGL canvas.
The JavaScript capture path therefore needs no architectural change: it still
sees one left and one right source, while the right source is now the already
rendered GeoGebra canvas itself.
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
        raise SystemExit("usage: patch-geogebra-quest-v0920.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")
    quest = replace_once(
        quest,
        "        renderer.draw();\n"
        "        renderer.captureQuestEye(Renderer.EYE_RIGHT);\n\n"
        "        // Deterministic state for the next frame and any work following it.",
        "        renderer.draw();\n"
        "        // v0.9.20: RIGHT_EYE is the final pass and remains in the shared\n"
        "        // WebGL canvas. JavaScript reuses that canvas directly, avoiding a\n"
        "        // second gl.finish() plus WebGL-to-hidden-canvas snapshot.\n\n"
        "        // Deterministic state for the next frame and any work following it.",
        "remove redundant right-eye renderer snapshot",
    )
    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.9.20 right-eye reuse: {quest_rel}")

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    web = replace_once(
        web,
        "\t\tif (questRightEyeCanvas == null) {\n"
        "\t\t\tquestRightEyeCanvas = createQuestEyeCanvas(\"ggq-renderer-right-eye\");\n"
        "\t\t\tquestRightEyeContext = Js.uncheckedCast(questRightEyeCanvas.getContext(\"2d\"));\n"
        "\t\t}",
        "\t\tif (questRightEyeCanvas == null && webGLCanvas != null) {\n"
        "\t\t\t// v0.9.20: the final RIGHT_EYE pass already lives in the main WebGL canvas.\n"
        "\t\t\tquestRightEyeCanvas = Js.uncheckedCast(webGLCanvas.getElement());\n"
        "\t\t\tquestRightEyeCanvas.id = \"ggq-renderer-right-eye\";\n"
        "\t\t}",
        "alias right-eye DOM source to main WebGL canvas",
    )

    web = replace_once(
        web,
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\tif (webGLCanvas == null || glContext == null) {",
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\t// v0.9.20: only LEFT_EYE needs a renderer-level snapshot.\n"
        "\t\tif (eye == EYE_RIGHT) {\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\tif (webGLCanvas == null || glContext == null) {",
        "skip any accidental right-eye snapshot",
    )

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.9.20 right-eye WebGL alias: {web_rel}")


if __name__ == "__main__":
    main()
