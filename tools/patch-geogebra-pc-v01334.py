#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.34 — GPU FBO stereo renderer.

This experiment starts from the known-good v0.13.31 eye geometry. Both eyes keep
exactly the same logical W x H viewport at x=0. Instead of copying the completed
default framebuffer (v0.13.33), each eye is rendered directly into its own
GPU-resident framebuffer/texture. After both eye passes are complete, a single
GPU compositor draw publishes coherent [L|R] into the 2W x H main WebGL backing
store consumed by Chromium/CEF.

No getImageData, readPixels, JPEG, Base64 or pixel ArrayBuffer path is used.
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
        raise SystemExit("usage: patch-geogebra-pc-v01334.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    # ------------------------------------------------------------------
    # Renderer base hooks.
    # ------------------------------------------------------------------
    renderer_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/Renderer.java"
    )
    renderer_path = root / renderer_rel
    renderer = renderer_path.read_text(encoding="utf-8")

    capture_hook = (
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\t// Web implementation overrides.\n"
        "\t}\n"
    )
    if capture_hook not in renderer:
        raise RuntimeError("v0.13.34 Renderer capture hook missing")

    extra_hooks = (
        "\n\t/** Bind the GPU render target for one Quest eye. */\n"
        "\tpublic void beginQuestEyeRender(int eye) {\n"
        "\t\t// Web implementation overrides.\n"
        "\t}\n\n"
        "\t/** Publish the completed GPU-resident Quest stereo pair. */\n"
        "\tpublic void composeQuestStereoFrame() {\n"
        "\t\t// Web implementation overrides.\n"
        "\t}\n"
    )
    renderer = renderer.replace(capture_hook, capture_hook + extra_hooks, 1)
    renderer_path.write_text(renderer, encoding="utf-8")
    print(f"patched v0.13.34 renderer hooks: {renderer_rel}")

    # ------------------------------------------------------------------
    # Continuous stereo draw loop. Each eye is rendered into its own FBO.
    # ------------------------------------------------------------------
    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    replacement = r'''    // GGQ_PC_V01334_GPU_FBO_SBS
    private int stereoFrameSerial;

    /** Continuous GPU path: every repaint produces a complete pair. */
    public void requestStereoFrame() {
        // No request gate in v0.13.34.
    }

    /** @return serial incremented after every completed GPU stereo pair. */
    public int getStereoFrameSerial() {
        return stereoFrameSerial;
    }

    /**
     * Render LEFT and RIGHT using the exact proven W x H geometry. The web
     * implementation binds a dedicated colour+depth FBO before each pass.
     * Only after both passes finish is [L|R] drawn to the visible 2W backing.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        renderer.beginQuestEyeRender(Renderer.EYE_LEFT);
        renderer.clearColorBuffer();
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.eye = Renderer.EYE_RIGHT;
        renderer.beginQuestEyeRender(Renderer.EYE_RIGHT);
        renderer.clearColorBuffer();
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.composeQuestStereoFrame();
        stereoFrameSerial++;

        impl.setColorMask(ColorMask.ALL);
        renderer.eye = Renderer.EYE_LEFT;
        renderer.setView();
    }
}'''

    quest, count = re.subn(
        r"    private boolean stereoPairRequested = true;.*?\n}\s*$",
        replacement,
        quest,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(f"v0.13.34 replace stereo loop: found {count}")
    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.13.34 FBO stereo loop: {quest_rel}")

    # ------------------------------------------------------------------
    # Web renderer: 2W final backing; scene viewport remains W at x=0.
    # ------------------------------------------------------------------
    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    web = replace_once(
        web,
        "\t\t// GeoGebraForQuest v0.9.19: both stereo eyes render sequentially\n"
        "\t\t// into this same single-eye W x H viewport.\n"
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "\t\t// GGQ_PC_V01334_GPU_FBO_SBS: eye geometry remains W x H,\n"
        "\t\t// while only the final published canvas is 2W x H.\n"
        "\t\tint backingWidth = (int) (w * ratio) * 2;\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "allocate 2W final backing",
    )

    # JsInterop imports are already installed by v0.9.21. Verify rather than
    # inserting duplicates.
    if "import jsinterop.annotations.JsMethod;" not in web or \
            "import jsinterop.annotations.JsPackage;" not in web:
        raise RuntimeError("v0.13.34 JsInterop imports missing")

    gpu_methods = r'''	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuBindEyeFramebuffer")
	private static native void ggqGpuBindEyeFramebuffer(
			WebGLRenderingContext gl, int eye, int width, int height);

	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuComposeStereoFbo")
	private static native void ggqGpuComposeStereoFbo(
			WebGLRenderingContext gl, int width, int height);

	@Override
	public void beginQuestEyeRender(int eye) {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		int eyeWidth = getWidthInPixels();
		int eyeHeight = getHeightInPixels();
		if (eyeWidth <= 0 || eyeHeight <= 0) {
			return;
		}
		ggqGpuBindEyeFramebuffer(glContext, eye, eyeWidth, eyeHeight);
	}

	@Override
	public void composeQuestStereoFrame() {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		int eyeWidth = getWidthInPixels();
		int eyeHeight = getHeightInPixels();
		if (eyeWidth <= 0 || eyeHeight <= 0) {
			return;
		}
		ggqGpuComposeStereoFbo(glContext, eyeWidth, eyeHeight);
	}

'''

    dispose_marker = "\t@Override\n\tpublic void dispose() {"
    if dispose_marker not in web:
        raise RuntimeError("v0.13.34 dispose marker missing")
    web = web.replace(dispose_marker, gpu_methods + dispose_marker, 1)

    expected_viewport = (
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// v0.9.19: LEFT_EYE and RIGHT_EYE both render at x=0.\n"
        "\t\treturn 0;\n"
        "\t}"
    )
    if expected_viewport not in web:
        raise RuntimeError("v0.13.34 single-viewport invariant missing")

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.13.34 web FBO hooks: {web_rel}")


if __name__ == "__main__":
    main()
