#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.39 — GPU full-frame A_L/A_R source renderer.

Key invariants:
- Keep the proven PROJECTION_GLASSES camera mathematics.
- Keep the visible/default WebGL canvas at exactly W x H; never create a 2W
  visible/backing canvas.
- Render LEFT and RIGHT into two independent W x H GPU FBOs, both at x=0.
- No captureQuestEye(), gl.finish(), 2D canvas snapshot, readPixels or CPU pixel
  path is used by the active renderer.
- Freeze the completed FBO pair while the native host exports full-window A_L
  and A_R through CEF accelerated paint. If GeoGebra repaints while frozen, the
  attempt is marked deferred and one repaint is requested after release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-geogebra-pc-v01339.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()

    # ------------------------------------------------------------------
    # Renderer base: generic hooks implemented by RendererWithImplW.
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
    require(renderer, capture_hook, "v0.13.39 Renderer capture hook missing")

    hooks = r'''
	/** @return whether the last completed Quest eye pair may be replaced. */
	public boolean canBeginQuestStereoPair() {
		return true;
	}

	/** Bind the GPU FBO for one Quest eye. */
	public void beginQuestEyeRender(int eye) {
		// Web implementation overrides.
	}

	/** Finish timing/state bookkeeping for one Quest eye FBO. */
	public void endQuestEyeRender(int eye) {
		// Web implementation overrides.
	}

	/** Freeze/publish the completed eye pair for native full-window export. */
	public void finishQuestStereoPair(int serial) {
		// Web implementation overrides.
	}
'''
    renderer = renderer.replace(capture_hook, capture_hook + hooks, 1)
    renderer_path.write_text(renderer, encoding="utf-8")

    # ------------------------------------------------------------------
    # QuestStereoRenderer: one model state, two eye draws, no CPU capture.
    # A draw attempt while the current pair is frozen is intentionally skipped;
    # the JS GPU bridge remembers it as deferred and requests one repaint when
    # native releases the pair.
    # ------------------------------------------------------------------
    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    replacement = r'''    // GGQ_PC_V01339_GPU_FULLFRAME_SBS
    private int stereoFrameSerial;

    /** Compatibility request hook; forcing a repaint is enough in v0.13.39. */
    public void requestStereoFrame() {
        // RendererWithImplW.ggqRequestStereoFrame() already calls repaintView().
    }

    /** @return serial incremented after each completed GPU eye-FBO pair. */
    public int getStereoFrameSerial() {
        return stereoFrameSerial;
    }

    /**
     * One GeoGebra repaint represents one dirty 3D scene state. The scene/model
     * state is not advanced between eye draws: we only switch the proven glasses
     * eye camera and render that same state into two W x H FBOs.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();

        if (!renderer.canBeginQuestStereoPair()) {
            return;
        }

        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        renderer.beginQuestEyeRender(Renderer.EYE_LEFT);
        renderer.clearColorBuffer();
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();
        renderer.endQuestEyeRender(Renderer.EYE_LEFT);

        renderer.eye = Renderer.EYE_RIGHT;
        renderer.beginQuestEyeRender(Renderer.EYE_RIGHT);
        renderer.clearColorBuffer();
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();
        renderer.endQuestEyeRender(Renderer.EYE_RIGHT);

        stereoFrameSerial++;
        renderer.finishQuestStereoPair(stereoFrameSerial);

        // Preserve the same deterministic post-render eye state used by the
        // proven v0.9.21/v0.13.35 path.
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
        raise RuntimeError(f"v0.13.39 QuestStereoRenderer replacement count={count}")
    quest_path.write_text(quest, encoding="utf-8")

    # ------------------------------------------------------------------
    # Web renderer: call the page-level WebGL FBO bridge. The visible canvas
    # remains W x H from v0.9.19. No 2W backing store is introduced here.
    # ------------------------------------------------------------------
    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    require(web, "int backingWidth = (int) (w * ratio);",
            "v0.13.39 requires the proven W x H backing store")
    require(web, "return 0;", "v0.13.39 requires x=0 eye viewport geometry")
    require(web, "import jsinterop.annotations.JsMethod;",
            "v0.13.39 JsMethod import missing")
    require(web, "import jsinterop.annotations.JsPackage;",
            "v0.13.39 JsPackage import missing")

    # Active path must never execute the historical 2D snapshot/readback.
    capture_pattern = re.compile(
        r"\t@Override\n\tpublic void captureQuestEye\(int eye\) \{.*?\n\t\}\n\n(?=\t@Override\n\tpublic void dispose\(\) \{)",
        re.S,
    )
    capture_replacement = (
        "\t@Override\n"
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\t// GGQ_PC_V01339: deliberately unused; eye pixels never leave GPU.\n"
        "\t}\n\n"
    )
    web, count = capture_pattern.subn(capture_replacement, web, count=1)
    if count != 1:
        raise RuntimeError(f"v0.13.39 captureQuestEye no-op replacement count={count}")

    gpu_methods = r'''	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuCanBeginStereoPair")
	private static native boolean ggqGpuCanBeginStereoPair(
			WebGLRenderingContext gl, int width, int height);

	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuBindEyeFramebuffer")
	private static native void ggqGpuBindEyeFramebuffer(
			WebGLRenderingContext gl, int eye, int width, int height);

	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuEndEyeFramebuffer")
	private static native void ggqGpuEndEyeFramebuffer(
			WebGLRenderingContext gl, int eye, int width, int height);

	@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqGpuFinishStereoPair")
	private static native void ggqGpuFinishStereoPair(
			WebGLRenderingContext gl, int width, int height, int serial);

	@Override
	public boolean canBeginQuestStereoPair() {
		if (webGLCanvas == null || glContext == null) {
			return false;
		}
		return ggqGpuCanBeginStereoPair(
				glContext, getWidthInPixels(), getHeightInPixels());
	}

	@Override
	public void beginQuestEyeRender(int eye) {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		ggqGpuBindEyeFramebuffer(
				glContext, eye, getWidthInPixels(), getHeightInPixels());
	}

	@Override
	public void endQuestEyeRender(int eye) {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		ggqGpuEndEyeFramebuffer(
				glContext, eye, getWidthInPixels(), getHeightInPixels());
	}

	@Override
	public void finishQuestStereoPair(int serial) {
		if (webGLCanvas == null || glContext == null) {
			return;
		}
		ggqGpuFinishStereoPair(
				glContext, getWidthInPixels(), getHeightInPixels(), serial);
	}

'''

    dispose_marker = "\t@Override\n\tpublic void dispose() {"
    require(web, dispose_marker, "v0.13.39 RendererWithImplW dispose marker missing")
    web = web.replace(dispose_marker, gpu_methods + dispose_marker, 1)
    web_path.write_text(web, encoding="utf-8")

    # Hard source invariants: these catch the exact family of mistakes made by
    # v0.13.32/v0.13.34 before we spend time compiling Web3D.
    combined = renderer + quest + web
    required = (
        "GGQ_PC_V01339_GPU_FULLFRAME_SBS",
        "ggqGpuCanBeginStereoPair",
        "ggqGpuBindEyeFramebuffer",
        "ggqGpuEndEyeFramebuffer",
        "ggqGpuFinishStereoPair",
        "renderer.beginQuestEyeRender(Renderer.EYE_LEFT)",
        "renderer.beginQuestEyeRender(Renderer.EYE_RIGHT)",
        "renderer.finishQuestStereoPair(stereoFrameSerial)",
        "int backingWidth = (int) (w * ratio);",
        "return 0;",
    )
    for needle in required:
        require(combined, needle, f"v0.13.39 source invariant missing: {needle}")

    forbidden = (
        "int backingWidth = (int) (w * ratio) * 2;",
        "return eye * getWidthInPixels();",
        "renderer.captureQuestEye(Renderer.EYE_LEFT)",
        "renderer.captureQuestEye(Renderer.EYE_RIGHT)",
    )
    for needle in forbidden:
        if needle in combined:
            raise RuntimeError(f"v0.13.39 forbidden source architecture present: {needle}")

    print("[GGQ] v0.13.39 source: W x H L/R FBOs + frozen GPU export pair installed")


if __name__ == "__main__":
    main()
