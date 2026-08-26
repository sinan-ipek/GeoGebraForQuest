#!/usr/bin/env python3
"""Exp16: always re-arm the embedded stereo layout after a 3D lifecycle gap.

When GeoGebra leaves the 3D view (for Browse/Login/material loading), Android is
correctly told that stereo is inactive. The old code kept the previous ACTIVE
layout payload for deduplication, though. If the newly loaded material recreated
3D in exactly the same rectangle, its ACTIVE payload compared equal to that old
payload and was suppressed forever, leaving the native B panel hidden.

Clear the dedup/canvas state on every active->inactive transition so a recreated
3D view is always announced again, even when its geometry is pixel-identical.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp16.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP16_MATERIAL_REACTIVATION" in text:
    print("[GGQ] exp16 material reactivation patch already present")
    raise SystemExit(0)

old = """  function reportStereoInactive() {
    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    restoreSelectiveHole();
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }
"""
new = """  function reportStereoInactive() {
    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;

    // EXP16_MATERIAL_REACTIVATION: the next 3D canvas may occupy the exact same
    // rectangle as the one that just disappeared. Forget the old ACTIVE payload
    // so sendLayout() cannot deduplicate that new lifecycle into silence.
    lastPayload = '';
    lastCanvas = null;

    restoreSelectiveHole();
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }
"""
if old not in text:
    raise RuntimeError("exp16 reportStereoInactive anchor not found")
text = text.replace(old, new, 1)

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
