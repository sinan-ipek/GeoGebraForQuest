#!/usr/bin/env python3
"""Exp16: always re-arm the embedded stereo layout after a 3D lifecycle gap.

Exp8 adds request-state resets at the start of reportStereoInactive(), so this
patch deliberately anchors only to that function's stable guard +
inactiveReported assignment rather than to the entire function body.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp16.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP16_MATERIAL_REACTIVATION" in text:
    print("[GGQ] exp16 material reactivation patch already present")
    raise SystemExit(0)

pattern = re.compile(
    r"(  function reportStereoInactive\(\) \{\n"
    r"(?:    [^\n]*\n)*?"
    r"    if \(!hasSeenActive3D \|\| inactiveReported\) return;\n"
    r"    inactiveReported = true;\n)"
)
insert = (
    r"\1\n"
    "    // EXP16_MATERIAL_REACTIVATION: the next 3D canvas may occupy the exact same\n"
    "    // rectangle as the one that just disappeared. Forget the old ACTIVE payload\n"
    "    // and canvas so the next lifecycle must announce itself to Android again.\n"
    "    lastPayload = '';\n"
    "    lastCanvas = null;\n"
)
text, count = pattern.subn(insert, text, count=1)
if count != 1:
    raise RuntimeError(f"exp16 reportStereoInactive scheduler-safe anchor count={count}")

for required in (
    "EXP16_MATERIAL_REACTIVATION",
    "lastPayload = '';",
    "lastCanvas = null;",
    "bridge('updateStereoLayout', JSON.stringify({ active: false }))",
):
    if required not in text:
        raise RuntimeError(f"exp16 reactivation requirement missing: {required}")

for forbidden in (
    "CAPTURE_ACTIVE_EYE_WIDTH",
    "CAPTURE_IDLE_EYE_WIDTH",
    "CAPTURE_IDLE_DELAY_MS",
    "540",
):
    if forbidden in text:
        raise RuntimeError(f"exp16 must retain fixed-720 policy; found {forbidden}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp16 stereo layout re-arms after Browse/Login/material lifecycle gaps")
