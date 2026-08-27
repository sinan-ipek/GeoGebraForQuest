#!/usr/bin/env python3
"""Exp19: make stereo layout recovery file-load-safe.

When GeoGebra opens another construction it temporarily destroys the current 3D
canvas. quest-stereo-layout.js reports {active:false}, but both the JS bridge and
Android activity used to keep their previous layout de-duplication state. If the
new file recreates a 3D view at the exact same rectangle, the identical active
payload is suppressed and the native stereo surface remains hidden forever.

Reset the JS layout/canvas de-duplication state whenever 3D becomes inactive so
an identical geometry from a newly loaded file is treated as a fresh activation.
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

anchor = '''  function reportStereoInactive() {
    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    restoreSelectiveHole();
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }
'''
replacement = '''  function reportStereoInactive() {
    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    restoreSelectiveHole();

    // EXP19_FILE_LOAD_LAYOUT_REARM: opening a GGB destroys the old 3D canvas
    // before creating the new one. The replacement often has the exact same
    // rectangle, so retaining lastPayload would suppress the fresh active
    // message and leave the native stereo VideoSurface hidden.
    lastPayload = '';
    lastCanvas = null;
    lastCaptureAt = 0;

    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }
'''

if anchor not in text:
    raise RuntimeError("exp19 reportStereoInactive anchor not found")
text = text.replace(anchor, replacement, 1)

for required in (
    "EXP19_FILE_LOAD_LAYOUT_REARM",
    "lastPayload = '';",
    "lastCanvas = null;",
    "lastCaptureAt = 0;",
    "bridge('updateStereoLayout', JSON.stringify({ active: false }))",
):
    if required not in text:
        raise RuntimeError(f"exp19 stereo rearm requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp19 stereo layout de-duplication rearmed across file loads")
