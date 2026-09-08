#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.33 — atomic GPU stereo packing.

Keep the proven v0.9.19/v0.13.31 stereo geometry: LEFT_EYE and RIGHT_EYE are
rendered sequentially into the SAME W x H viewport at x=0.  The completed eye
passes are copied with WebGL copyTexSubImage2D into two GPU textures.  Only after
both eyes are complete does a one-draw GPU compositor publish [L|R] into the
2W x H main WebGL backing store consumed by CEF.

This deliberately avoids the v0.13.32 mistake of rendering scene geometry
straight into two halves of a 2W default framebuffer.  No getImageData, JPEG,
Base64, pixel ArrayBuffer or CPU stereo copy is used.
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
        raise SystemExit("usage: patch-geogebra-pc-v01333.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

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
        raise RuntimeError("v0.13.33 Renderer capture hook missing")
    renderer = renderer.replace(
        capture_hook,
        capture_hook
        + "\n\t/** Publish the completed GPU-resident Quest stereo pair. */\n"
        + "\tpublic void composeQuestStereoFrame() {\n"
        + "\t\t// Web implementation overrides.\n"
        + "\t}\n",
        1,
    )
    renderer_path.write_text(renderer, encoding="utf-8")
    print(f"patched v0.13.33 compose hook: {renderer_rel}")

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    replacement = r'''    // GGQ_PC_V01333_GPU_ATOMIC_SBS
    private int stereoFrameSerial;

    /** Requests are unnecessary in the continuous GPU path. */
    public void requestStereoFrame() {
        // Every repaint already produces a complete pair.
    }

    /** @return serial incremented after every completed GPU stereo pair. */
    public int getStereoFrameSerial() {
        return stereoFrameSerial;
    }

    /**
     * Render a coherent pair using the proven single W x H viewport. Each eye
     * is copied to a GPU texture before the viewport is reused. The final L|R
     * backing-store update happens only after both eye passes have completed.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();
        renderer.captureQuestEye(Renderer.EYE_LEFT);

        // Reuse exactly the same viewport for RIGHT_EYE, as in the known-good
        // v0.9.19/v0.13.31 stereo path.
        renderer.clearColorBuffer();
        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();
        renderer.captureQuestEye(Renderer.EYE_RIGHT);

        // One GPU fullscreen draw publishes the complete pair to CEF.
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
        raise RuntimeError(f"v0.13.33 replace demand-driven draw loop: found {count}")
    quest_path.write_text(quest, encoding="utf-8")
    print(f"patched v0.13.33 continuous atomic pair loop: {quest_rel}")

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    # The final canvas stores two W-wide eye textures, but GeoGebra itself keeps
    # rendering with its original logical W x H camera/frustum dimensions.
    web = replace_once(
        web,
        "\t\t// GeoGebraForQuest v0.9.19: both stereo eyes render sequentially\n"
        "\t\t// into this same single-eye W x H viewport.\n"
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "\t\t// GGQ_PC_V01333_GPU_ATOMIC_SBS: geometry still renders at W x H,\n"
        "\t\t// while the final compositor owns a 2W x H backing store.\n"
        "\t\tint backingWidth = (int) (w * ratio) * 2;\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);",
        "allocate 2W final GPU backing",
    )

    # Bind Java calls to the small GPU compositor installed in index.html.
    dispose_marker = "\t@Override\n\tpublic void dispose() {"
    if dispose_marker not in web:
        raise RuntimeError("v0.13.33 RendererWithImplW dispose marker missing")

    gpu_methods = r'''	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuCaptureEye")
	private static native void ggqGpuCaptureEye(
			WebGLRenderingContext gl, int eye, int width, int height);

	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuComposeStereo")
	private static native void ggqGpuComposeStereo(
			WebGLRenderingContext gl, int width, int height);

	@Override
	public void captureQuestEye(int eye) {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		int eyeWidth = getWidthInPixels();
		int eyeHeight = getHeightInPixels();
		if (eyeWidth <= 0 || eyeHeight <= 0) {
			return;
		}
		ggqGpuCaptureEye(glContext, eye, eyeWidth, eyeHeight);
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
		ggqGpuComposeStereo(glContext, eyeWidth, eyeHeight);
	}

'''

    # Replace the existing renderer-level 2D capture method (plus only that
    # method) with the WebGL GPU copy hooks. Hidden legacy canvases can remain
    # allocated in the class but are no longer touched by the active path.
    pattern = re.compile(
        r"\t@Override\n\tpublic void captureQuestEye\(int eye\) \{.*?\n\t}\n\n(?=\t@Override\n\tpublic void dispose\(\) \{)",
        re.S,
    )
    web, count = pattern.subn(gpu_methods, web, count=1)
    if count != 1:
        raise RuntimeError(f"v0.13.33 replace Web eye capture: found {count}")

    # Keep both eye passes at x=0. This is a hard correctness invariant: it is
    # the exact camera/aspect geometry that produced correct depth in v0.13.31.
    expected_viewport = (
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// v0.9.19: LEFT_EYE and RIGHT_EYE both render at x=0.\n"
        "\t\treturn 0;\n"
        "\t}"
    )
    if expected_viewport not in web:
        raise RuntimeError("v0.13.33 single-viewport invariant missing")

    web_path.write_text(web, encoding="utf-8")
    print(f"patched v0.13.33 GPU copy/compose web renderer: {web_rel}")


if __name__ == "__main__":
    main()
