#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.32: continuous GPU-native SBS renderer.

The current Exp46 source intentionally renders ordinary frames as RIGHT_EYE only
and snapshots LEFT_EYE into a hidden 2D canvas on demand.  That was correct for
the old JPEG/raw transport, but it forces a GPU->CPU readback before PC OpenXR
can receive the left image.

For the new PC-only GPU architecture we instead keep both eyes in GeoGebra's
main WebGL backing store at all times:

    main WebGL canvas = [ LEFT_EYE | RIGHT_EYE ]

The canvas backing store is 2W x H while its CSS rectangle remains W x H.  CEF
therefore exports one accelerated shared texture containing the full application
UI plus a horizontally-compressed SBS image inside the 3D canvas rectangle.
The native PC/OpenXR compositors split/stretch those two halves entirely on the
GPU.  No hidden-eye canvas, JPEG, getImageData, ArrayBuffer pixel IPC, CPU pixel
swizzle or stereo texture upload is required by the active runtime.
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
        raise SystemExit("usage: patch-geogebra-pc-v01332.py <geogebra-source-root>")

    root = Path(sys.argv[1]).resolve()

    web_rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    web_path = root / web_rel
    web = web_path.read_text(encoding="utf-8")

    # v0.9.19 collapsed the backing width to W.  Restore the original two-eye
    # backing store while keeping the DOM/CSS size unchanged.
    old_backing = (
        "\t\t// GeoGebraForQuest v0.9.19: both stereo eyes render sequentially\n"
        "\t\t// into this same single-eye W x H viewport.\n"
        "\t\tint backingWidth = (int) (w * ratio);\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);"
    )
    new_backing = (
        "\t\t// GGQ_PC_V01332_GPU_NATIVE_SBS: CEF exports this WebGL surface\n"
        "\t\t// directly as a shared D3D11 texture. Keep both full-colour eyes\n"
        "\t\t// resident side-by-side in one 2W x H GPU backing store.\n"
        "\t\tint backingWidth = (int) (w * ratio) * 2;\n"
        "\t\twebGLCanvas.setCoordinateSpaceWidth(backingWidth);"
    )
    web = replace_once(web, old_backing, new_backing, "restore 2W WebGL backing")

    old_offset = (
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// v0.9.19: LEFT_EYE and RIGHT_EYE both render at x=0.\n"
        "\t\treturn 0;\n"
        "\t}"
    )
    new_offset = (
        "\t@Override\n"
        "\tpublic int getViewportHorizontalOffset() {\n"
        "\t\t// GGQ_PC_V01332_GPU_NATIVE_SBS: eye 0 occupies the left W pixels\n"
        "\t\t// and eye 1 the right W pixels of the same WebGL backing store.\n"
        "\t\treturn eye * getWidthInPixels();\n"
        "\t}"
    )
    web = replace_once(web, old_offset, new_offset, "restore per-eye viewport offset")

    # The demand-driven hidden LEFT snapshot is no longer part of the active
    # architecture. Leave the method available for compatibility, but make it a
    # no-op so no gl.finish()/2D canvas copy can accidentally re-enter the path.
    capture_pattern = re.compile(
        r"\t@Override\n\tpublic void captureQuestEye\(int eye\) \{.*?\n\t\}\n\n(?=\t@Override\n\tpublic void dispose\(\) \{)",
        re.S,
    )
    capture_replacement = (
        "\t@Override\n"
        "\tpublic void captureQuestEye(int eye) {\n"
        "\t\t// GGQ_PC_V01332_GPU_NATIVE_SBS: no renderer readback/snapshot.\n"
        "\t\t// Both completed eyes remain in the main WebGL texture.\n"
        "\t}\n\n"
    )
    web, count = capture_pattern.subn(capture_replacement, web, count=1)
    if count != 1:
        raise RuntimeError(f"disable hidden eye capture: expected one method, found {count}")

    web_path.write_text(web, encoding="utf-8")

    quest_rel = (
        "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
        "euclidian3D/openGL/QuestStereoRenderer.java"
    )
    quest_path = root / quest_rel
    quest = quest_path.read_text(encoding="utf-8")

    # Replace v0.9.21's requested-left/right-only scheduler.  Every GeoGebra
    # repaint now draws one complete GPU SBS pair.  The old request API remains
    # source-compatible but is irrelevant to PC v0.13.32.
    method_pattern = re.compile(
        r"    /\*\*\n"
        r"     \* Draw a Quest frame\. Ordinary repaints draw only RIGHT_EYE; a requested\n"
        r"     \* VideoSurface update first draws and snapshots LEFT_EYE, then finishes\n"
        r"     \* with RIGHT_EYE in the shared WebGL canvas\.\n"
        r"     \*/\n"
        r"    public void drawStereoFrame\(\) \{.*?\n    \}\n",
        re.S,
    )
    method_replacement = r'''    /**
     * GGQ_PC_V01332_GPU_NATIVE_SBS: every repaint produces a complete
     * full-colour L|R pair in the main 2W x H WebGL backing store.
     */
    public void drawStereoFrame() {
        RendererImpl impl = renderer.getRendererImpl();
        stereoPairRequested = false;
        impl.setColorMask(ColorMask.ALL);

        renderer.eye = Renderer.EYE_LEFT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        renderer.eye = Renderer.EYE_RIGHT;
        impl.clearDepthBuffer();
        renderer.setView();
        renderer.draw();

        stereoFrameSerial++;

        // Keep GeoGebra picking/cursor mathematics in the deterministic state
        // used by the proven Exp46 build after rendering.
        impl.setColorMask(ColorMask.ALL);
        renderer.eye = Renderer.EYE_LEFT;
        renderer.setView();
    }
'''
    quest, count = method_pattern.subn(method_replacement, quest, count=1)
    if count != 1:
        raise RuntimeError(f"continuous SBS draw loop: expected one method, found {count}")

    quest_path.write_text(quest, encoding="utf-8")

    combined = web + quest
    required = (
        "GGQ_PC_V01332_GPU_NATIVE_SBS",
        "int backingWidth = (int) (w * ratio) * 2;",
        "return eye * getWidthInPixels();",
        "public void captureQuestEye(int eye)",
        "stereoFrameSerial++;",
        "renderer.eye = Renderer.EYE_LEFT;",
        "renderer.eye = Renderer.EYE_RIGHT;",
    )
    for needle in required:
        if needle not in combined:
            raise RuntimeError(f"v0.13.32 source invariant missing: {needle}")

    # Active renderer must not snapshot either eye to a 2D canvas.
    capture_pos = web.index("public void captureQuestEye(int eye)")
    dispose_pos = web.index("public void dispose()", capture_pos)
    capture_body = web[capture_pos:dispose_pos]
    for forbidden in ("glContext.finish()", "context.drawImage(", "context.clearRect("):
        if forbidden in capture_body:
            raise RuntimeError(f"v0.13.32 capture no-op contaminated by {forbidden}")

    print("[GGQ] PC v0.13.32 continuous GPU-native 2W SBS renderer installed")


if __name__ == "__main__":
    main()
