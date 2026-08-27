#!/usr/bin/env python3
"""Exp19: make stereo layout recovery file-load-safe.

The exp8 capture scheduler already resets pending stereo request/serial state when
3D becomes inactive. The remaining bug is layout de-duplication: lastPayload and
lastCanvas survive the inactive transition. If a newly loaded construction
recreates the 3D view at the exact same rectangle, that active payload is dropped
and Android never makes the native stereo surface visible again.

This patch is intentionally applied AFTER exp8/10/11 and only rearms the layout
identity state; it does not touch the proven capture scheduler.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp19.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP19_FILE_LOAD_LAYOUT_REARM" in text:
    print("[GGQ] exp19 stereo layout rearm already present")
    raise SystemExit(0)

anchor = '''    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    restoreSelectiveHole();
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
'''
replacement = '''    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    restoreSelectiveHole();

    // EXP19_FILE_LOAD_LAYOUT_REARM: opening a GGB destroys the old 3D canvas
    // before creating the new one. The replacement often has the exact same
    // rectangle, so retaining lastPayload would suppress the fresh active
    // message and leave the native stereo VideoSurface hidden.
    lastPayload = '';
    lastCanvas = null;

    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
'''

if anchor not in text:
    raise RuntimeError("exp19 post-exp8 reportStereoInactive anchor not found")
text = text.replace(anchor, replacement, 1)

for required in (
    "EXP19_FILE_LOAD_LAYOUT_REARM",
    "lastPayload = '';",
    "lastCanvas = null;",
    "pendingStereoSerial = null;",
    "lastDeliveredStereoSerial = -1;",
    "bridge('updateStereoLayout', JSON.stringify({ active: false }))",
):
    if required not in text:
        raise RuntimeError(f"exp19 stereo rearm requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp19 layout identity rearmed; exp8 serial reset preserved")
