#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.21 demand-driven stereo-pair patch.

Normal GeoGebra repaint frames render only RIGHT_EYE. JavaScript explicitly
requests a full stereo pair when the VideoSurface needs a new frame. The next
renderer pass then snapshots LEFT_EYE, renders RIGHT_EYE into the main WebGL
canvas, increments a completed-pair serial, and returns to right-only rendering.

This keeps GeoGebra's existing stereo camera / picking mathematics while
avoiding unused LEFT_EYE scene renders and gl.finish() snapshots.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-geogebra-quest-v0921.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    renderer_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/Renderer.java"
    )
    renderer_path = root / renderer_rel
    renderer = renderer_path.read_text(encoding="utf-8")
    renderer = replace_once(
        renderer,
        "\tprivate QuestStereoRenderer questStereoRenderer;\n",
        "\tprivate QuestStereoRenderer questStereoRenderer;\n\n"
        "\t/** Request one full Quest stereo pair on the next renderer pass. */\n"
        "\tpublic void requestQuestStereoFrame() {\n"
        "\t\tif (questStereoRenderer != null) {\n"
        "\t\t\tquestStereoRenderer.requestStereoFrame();\n"
        "\t\t}\n"
        "\t}\n\n"
        "\t/** @return serial of the last completed Quest stereo pair. */\n"
        "\tpublic int getQuestStereoFrameSerial() {\n"
        "\t\treturn questStereoRenderer == null ? -1\n"
        "\t\t\t\t: questStereoRenderer.getStereoFrameSerial();\n"
        "\t}\n",
        "add demand-driven stereo request API",
    )
    renderer_path.write_text(renderer, encoding="utf-8")
    print(f"patched v0.9.21 request API: {renderer_rel}")

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    replacement = r'''    private boolean stereoPairRequested = true;
    private int stereoFrameSerial;

    /** Ask the next renderer pass to produce a complete LEFT/RIGHT pair. */
    public void requestStereoFrame() {
        stereoPairRequested = true;
    }

    /** @return serial incremented after each completed requested stereo pair. */
    public int getStereoFrameSerial() {
        return stereoFrameSerial;
    }

    /**
     * Draw a Quest frame. Ordinary repaints draw only RIGHT_EYE; a requested
     * VideoSurface update first draws and snapshots LEFT_EYE, then finishes
     * with RIGHT_EYE in the shared WebGL canvas.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();
        boolean renderStereoPair = stereoPairRequested;
        stereoPairRequested = false;

        impl.setColorMask(ColorMask.ALL);

        if (renderStereoPair) {
            renderer.eye = Renderer.EYE_LEFT;
            impl.clearDepthBuffer();
            renderer.setView();
            renderer.draw();
            renderer.captureQuestEye(Renderer.EYE_LEFT);

            // LEFT_EYE and RIGHT_EYE reuse the same W x H viewport.
            renderer.clearColorBuffer();
        }

        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        if (renderStereoPair) {
            stereoFrameSerial++;
        }

        // Keep picking/cursor state deterministic between render passes.
        impl.setColorMask(ColorMask.ALL);
        renderer.eye = Renderer.EYE_LEFT;
        renderer.setView();
    }
}'''

    quest, count = re.subn(
        r"    /\*\* Draw one complete full-colour SBS frame\. \*/\n"
        r"    public void drawStereoFrame\(\) \{.*?\n    \}\n\}",
        replacement,
        quest,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(
            f"replace stereo draw loop: expected exactly one match, found {count}"
        )
    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.9.21 demand-driven eye rendering: {quest_rel}")

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    if "import jsinterop.annotations.JsMethod;" not in web:
        web = replace_once(
            web,
            "import jsinterop.base.Js;\n",
            "import jsinterop.annotations.JsMethod;\n"
            "import jsinterop.annotations.JsPackage;\n"
            "import jsinterop.base.Js;\n",
            "add JsInterop annotations",
        )

    web = replace_once(
        web,
        "\tprivate CanvasRenderingContext2D questRightEyeContext;\n"
        "\tprivate double ratio = 1;",
        "\tprivate CanvasRenderingContext2D questRightEyeContext;\n"
        "\tprivate static RendererWithImplW ggqLastQuestRenderer;\n"
        "\tprivate double ratio = 1;",
        "track active Quest web renderer",
    )

    web = replace_once(
        web,
        "\t\twebGLCanvas = c;\n\n\t\tsetRendererImpl",
        "\t\twebGLCanvas = c;\n"
        "\t\tggqLastQuestRenderer = this;\n\n"
        "\t\tsetRendererImpl",
        "remember active Quest renderer",
    )

    hook = r'''	/**
	 * Request one complete Quest stereo pair. The normal render loop remains
	 * RIGHT_EYE-only until this is called again.
	 * @return serial before the requested pair is rendered, or -1 if unavailable
	 */
	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqRequestStereoFrame")
	public static int ggqRequestStereoFrame() {
		RendererWithImplW renderer = ggqLastQuestRenderer;
		if (renderer == null || renderer.getView() == null) {
			return -1;
		}
		int serial = renderer.getQuestStereoFrameSerial();
		renderer.requestQuestStereoFrame();
		renderer.getView().repaintView();
		return serial;
	}

	/** @return serial of the last completed requested stereo pair. */
	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGetStereoFrameSerial")
	public static int ggqGetStereoFrameSerial() {
		RendererWithImplW renderer = ggqLastQuestRenderer;
		return renderer == null ? -1 : renderer.getQuestStereoFrameSerial();
	}

'''
    web = replace_once(
        web,
        "\t@Override\n\tpublic void dispose() {",
        hook + "\t@Override\n\tpublic void dispose() {",
        "export stereo request and serial hooks",
    )

    web = replace_once(
        web,
        "\tpublic void dispose() {\n\t\treadyToRender = false;",
        "\tpublic void dispose() {\n"
        "\t\tif (ggqLastQuestRenderer == this) {\n"
        "\t\t\tggqLastQuestRenderer = null;\n"
        "\t\t}\n"
        "\t\treadyToRender = false;",
        "clear stale active renderer",
    )

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.9.21 JS request hooks: {web_rel}")


if __name__ == "__main__":
    main()
