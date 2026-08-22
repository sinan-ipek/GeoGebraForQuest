#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.18 renderer-pass eye capture patch.

The earlier live-stereo experiments tried to rediscover left/right eye images by
splitting the final WebGL canvas after rendering. That is unnecessary and can be
wrong because the renderer itself already knows exactly when LEFT_EYE and
RIGHT_EYE have finished drawing.

This patch adds a renderer hook that snapshots each completed eye viewport into
its own hidden HTML canvas immediately after that eye pass. The Android/WebView
bridge can then encode those two explicit canvases and send exactly one L and
one R image to Meta StereoMode.LeftRight.
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
        raise SystemExit("usage: patch-geogebra-quest-v0918.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    renderer_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/Renderer.java"
    )
    renderer_path = root / renderer_rel
    renderer = renderer_path.read_text(encoding="utf-8")
    renderer = replace_once(
        renderer,
        "\tpublic int getViewportHorizontalOffset() {\n\t\treturn 0;\n\t}\n",
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\treturn 0;\n"
        "\t}\n\n"
        "\t/**\n"
        "\t * Quest build hook called immediately after one stereo eye pass.\n"
        "\t * Desktop/common renderers intentionally do nothing; the WebGL\n"
        "\t * renderer overrides this and snapshots the completed viewport.\n"
        "\t * @param eye EYE_LEFT or EYE_RIGHT\n"
        "\t */\n"
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\t// Web implementation overrides.\n"
        "\t}\n",
        "add renderer eye-capture hook",
    )
    renderer_path.write_text(renderer, encoding="utf-8")
    print(f"patched v0.9.18 eye hook: {renderer_rel}")

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")
    quest = replace_once(
        quest,
        "        renderer.eye = Renderer.EYE_LEFT;\n"
        "        impl.clearDepthBuffer();\n"
        "        renderer.setView();\n"
        "        renderer.draw();\n\n"
        "        renderer.eye = Renderer.EYE_RIGHT;",
        "        renderer.eye = Renderer.EYE_LEFT;\n"
        "        impl.clearDepthBuffer();\n"
        "        renderer.setView();\n"
        "        renderer.draw();\n"
        "        renderer.captureQuestEye(Renderer.EYE_LEFT);\n\n"
        "        renderer.eye = Renderer.EYE_RIGHT;",
        "capture completed left-eye pass",
    )
    quest = replace_once(
        quest,
        "        renderer.eye = Renderer.EYE_RIGHT;\n"
        "        impl.clearDepthBuffer();\n"
        "        renderer.setView();\n"
        "        renderer.draw();\n\n"
        "        // Deterministic state for the next frame and any work following it.",
        "        renderer.eye = Renderer.EYE_RIGHT;\n"
        "        impl.clearDepthBuffer();\n"
        "        renderer.setView();\n"
        "        renderer.draw();\n"
        "        renderer.captureQuestEye(Renderer.EYE_RIGHT);\n\n"
        "        // Deterministic state for the next frame and any work following it.",
        "capture completed right-eye pass",
    )
    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.9.18 eye hook: {quest_rel}")

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    web = replace_once(
        web,
        "import elemental2.dom.DomGlobal;\nimport elemental2.dom.HTMLCanvasElement;",
        "import elemental2.dom.CanvasRenderingContext2D;\n"
        "import elemental2.dom.DomGlobal;\n"
        "import elemental2.dom.HTMLCanvasElement;",
        "import 2D canvas context",
    )

    web = replace_once(
        web,
        "\tprotected WebGLRenderingContext glContext;\n\tprivate double ratio = 1;",
        "\tprotected WebGLRenderingContext glContext;\n"
        "\tprivate HTMLCanvasElement questLeftEyeCanvas;\n"
        "\tprivate HTMLCanvasElement questRightEyeCanvas;\n"
        "\tprivate CanvasRenderingContext2D questLeftEyeContext;\n"
        "\tprivate CanvasRenderingContext2D questRightEyeContext;\n"
        "\tprivate double ratio = 1;",
        "add explicit Quest eye canvases",
    )

    web = replace_once(
        web,
        "\t@Override\n\tpublic void dispose() {",
        "\tprivate HTMLCanvasElement createQuestEyeCanvas(String id) {\n"
        "\t\tHTMLCanvasElement canvas = (HTMLCanvasElement) DomGlobal.document.createElement(\"canvas\");\n"
        "\t\tcanvas.id = id;\n"
        "\t\tcanvas.style.display = \"none\";\n"
        "\t\tDomGlobal.document.body.appendChild(canvas);\n"
        "\t\treturn canvas;\n"
        "\t}\n\n"
        "\tprivate void ensureQuestEyeCanvases() {\n"
        "\t\tif (questLeftEyeCanvas == null) {\n"
        "\t\t\tquestLeftEyeCanvas = createQuestEyeCanvas(\"ggq-renderer-left-eye\");\n"
        "\t\t\tquestLeftEyeContext = Js.uncheckedCast(questLeftEyeCanvas.getContext(\"2d\"));\n"
        "\t\t}\n"
        "\t\tif (questRightEyeCanvas == null) {\n"
        "\t\t\tquestRightEyeCanvas = createQuestEyeCanvas(\"ggq-renderer-right-eye\");\n"
        "\t\t\tquestRightEyeContext = Js.uncheckedCast(questRightEyeCanvas.getContext(\"2d\"));\n"
        "\t\t}\n"
        "\t}\n\n"
        "\t@Override\n"
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\tif (webGLCanvas == null || glContext == null) {\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\tensureQuestEyeCanvases();\n"
        "\t\tint eyeWidth = getWidthInPixels();\n"
        "\t\tint eyeHeight = getHeightInPixels();\n"
        "\t\tif (eyeWidth <= 0 || eyeHeight <= 0) {\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\tHTMLCanvasElement target = eye == EYE_RIGHT\n"
        "\t\t\t\t? questRightEyeCanvas : questLeftEyeCanvas;\n"
        "\t\tCanvasRenderingContext2D context = eye == EYE_RIGHT\n"
        "\t\t\t\t? questRightEyeContext : questLeftEyeContext;\n"
        "\t\tif (target.width != eyeWidth) {\n"
        "\t\t\ttarget.width = eyeWidth;\n"
        "\t\t}\n"
        "\t\tif (target.height != eyeHeight) {\n"
        "\t\t\ttarget.height = eyeHeight;\n"
        "\t\t}\n"
        "\t\tHTMLCanvasElement source = Js.uncheckedCast(webGLCanvas.getElement());\n"
        "\t\tint sourceX = eye == EYE_RIGHT ? eyeWidth : 0;\n"
        "\t\tglContext.flush();\n"
        "\t\tcontext.clearRect(0, 0, eyeWidth, eyeHeight);\n"
        "\t\tcontext.drawImage(source, sourceX, 0, eyeWidth, eyeHeight,\n"
        "\t\t\t\t0, 0, eyeWidth, eyeHeight);\n"
        "\t}\n\n"
        "\t@Override\n\tpublic void dispose() {",
        "add renderer-pass canvas snapshots",
    )

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.9.18 eye hook: {web_rel}")


if __name__ == "__main__":
    main()
