#!/usr/bin/env python3
"""Exp19: verify/rearm the JS side of file-load stereo lifecycle.

Exp16 is already wired into patch-quest-stereo-js-exp11.py and performs the JS
half of the required fix: after a 3D lifecycle gap it clears lastPayload and
lastCanvas, while exp8 resets pending stereo request/serial state. Exp19's new
work is therefore primarily the missing Android-side layout reset.

This script keeps the build explicit: if exp16 is present it verifies those
invariants and leaves the proven JS untouched. A small fallback is retained for
older trees that do not yet contain exp16.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp19.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

required_common = (
    "lastPayload = '';",
    "lastCanvas = null;",
    "pendingStereoSerial = null;",
    "lastDeliveredStereoSerial = -1;",
    "bridge('updateStereoLayout', JSON.stringify({ active: false }))",
)

if "EXP16_MATERIAL_REACTIVATION" in text:
    for required in required_common:
        if required not in text:
            raise RuntimeError(f"exp19 expected exp16 invariant missing: {required}")
    print("[GGQ] exp19 JS check: existing exp16 lifecycle re-arm is correct; no duplicate patch applied")
    raise SystemExit(0)

if "EXP19_FILE_LOAD_LAYOUT_REARM" not in text:
    pattern = re.compile(
        r"(    if \(!hasSeenActive3D \|\| inactiveReported\) return;\n"
        r"    inactiveReported = true;\n)"
    )
    insert = (
        r"\1\n"
        "    // EXP19_FILE_LOAD_LAYOUT_REARM: older-tree fallback. A replacement\n"
        "    // 3D canvas may reuse the exact rectangle, so forget layout identity.\n"
        "    lastPayload = '';\n"
        "    lastCanvas = null;\n"
    )
    text, count = pattern.subn(insert, text, count=1)
    if count != 1:
        raise RuntimeError(f"exp19 fallback reportStereoInactive anchor count={count}")

for required in ("EXP19_FILE_LOAD_LAYOUT_REARM",) + required_common:
    if required not in text:
        raise RuntimeError(f"exp19 JS fallback invariant missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp19 JS fallback lifecycle re-arm installed")
