#!/usr/bin/env python3
"""Exp10 capture policy: keep exp8 demand-driven stereo rendering, fixed at 720px.

This intentionally does NOT apply exp9 UI-priority/adaptive scheduling. Both active
manipulation and idle stereo captures stay at 720px so scene rotation never trades
stereo resolution for UI responsiveness.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp10.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP10_FIXED_720" in text:
    print("[GGQ] exp10 fixed-720 scheduler already patched")
    raise SystemExit(0)

old = "  var CAPTURE_ACTIVE_EYE_WIDTH = 540;\n  var CAPTURE_IDLE_EYE_WIDTH = 720;\n"
new = (
    "  // EXP10_FIXED_720: no resolution reduction during rotation/manipulation.\n"
    "  var CAPTURE_ACTIVE_EYE_WIDTH = 720;\n"
    "  var CAPTURE_IDLE_EYE_WIDTH = 720;\n"
)
if old not in text:
    raise SystemExit("[GGQ] exp10 fixed-720 exp8 constants anchor not found")
text = text.replace(old, new, 1)

text = text.replace(
    "  // Dynamic capture resolution: keep full 720px quality at rest, but reduce\n"
    "  // JPEG/decode traffic to 540px during active manipulation and for 300ms after.\n",
    "  // Exp10 keeps interaction tracking only for compatibility; both active and idle\n"
    "  // capture widths are 720px, so manipulation never lowers stereo resolution.\n",
    1,
)

path.write_text(text, encoding="utf-8")
print("[GGQ] exp10 fixed 720px capture; exp8 demand-driven renderer cadence preserved")
