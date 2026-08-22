#!/usr/bin/env python3
"""GeoGebraForQuest v0.9.13 live-frame capture patch.

The Quest renderer already draws full-colour L|R SBS into one 2x-wide WebGL
canvas. v0.9.13 mirrors that live canvas into a registered VideoSurface panel.
WebGL normally allows the drawing buffer to be discarded after presentation,
which makes canvas drawImage()/toDataURL() unreliable. This patch keeps the
buffer readable while preserving GeoGebra's normal renderer initialization.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-geogebra-quest-v0913.py <geogebra-root>")

    root = Path(sys.argv[1]).resolve()
    rel = (
        "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
        "euclidian3D/openGL/RendererWithImplW.java"
    )
    path = root / rel
    text = path.read_text(encoding="utf-8")

    old = (
        "\t\tJsPropertyMap<Object> options = JsPropertyMap.of();\n"
        "\t\tif (transparent) {"
    )
    new = (
        "\t\tJsPropertyMap<Object> options = JsPropertyMap.of();\n"
        "\t\t// GeoGebraForQuest v0.9.13: the live Quest stereo panel copies\n"
        "\t\t// the completed 2x-wide SBS canvas after presentation. Keep the\n"
        "\t\t// WebGL drawing buffer readable for drawImage()/toDataURL().\n"
        "\t\toptions.set(\"preserveDrawingBuffer\", true);\n"
        "\t\tif (transparent) {"
    )

    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"preserveDrawingBuffer patch: expected exactly one match, found {count}"
        )

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched v0.9.13 live capture: {rel}")


if __name__ == "__main__":
    main()
