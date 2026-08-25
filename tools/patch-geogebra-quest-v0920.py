#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.20 right-eye snapshot reuse patch.

After the v0.9.19 single-viewport stereo renderer finishes a frame, the shared
WebGL canvas contains the completed RIGHT_EYE image because RIGHT_EYE is the
second and final draw pass. The left eye must still be snapshotted before that
shared viewport is cleared, but taking a second renderer-level RIGHT_EYE
snapshot only adds another gl.finish() and WebGL-to-2D-canvas copy.

This patch removes only that redundant RIGHT_EYE capture hook. JavaScript uses
the main WebGL canvas directly as the right-eye source while preserving the
existing left-eye snapshot, 20 fps JPEG/Base64 bridge, and Android Surface path.
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


if __name__ == "__main__":
    main()
