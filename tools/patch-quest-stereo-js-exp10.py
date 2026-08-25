#!/usr/bin/env python3
"""Exp10 capture policy: keep exp8 demand-driven stereo rendering at fixed 720px.

This removes the exp8 dynamic 540/720 resolution system entirely. There is no
motion-dependent capture size and no interaction tracking for resolution changes.
Exp9 UI-priority/adaptive scheduling is not applied.
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

old_constants = (
    "  var CAPTURE_ACTIVE_EYE_WIDTH = 540;\n"
    "  var CAPTURE_IDLE_EYE_WIDTH = 720;\n"
    "  var CAPTURE_IDLE_DELAY_MS = 300;\n"
)
new_constants = (
    "  // EXP10_FIXED_720: stereo capture resolution never changes during interaction.\n"
    "  var CAPTURE_MAX_EYE_WIDTH = 720;\n"
)
if old_constants not in text:
    raise SystemExit("[GGQ] exp10 fixed-720 constants anchor not found")
text = text.replace(old_constants, new_constants, 1)

if "  var lastStereoMotionAt = -100000;\n" not in text:
    raise SystemExit("[GGQ] exp10 motion-state anchor not found")
text = text.replace("  var lastStereoMotionAt = -100000;\n", "", 1)

old_motion_helpers = '''  function markStereoMotion() {
    try {
      lastStereoMotionAt = performance.now();
    } catch (_) {
      lastStereoMotionAt = Date.now();
    }
  }

  function markPointerMotion(event) {
    if (!event || event.buttons || Number(event.pressure || 0) > 0) {
      markStereoMotion();
    }
  }

  function captureEyeWidth(now) {
    return now - lastStereoMotionAt < CAPTURE_IDLE_DELAY_MS
      ? CAPTURE_ACTIVE_EYE_WIDTH
      : CAPTURE_IDLE_EYE_WIDTH;
  }

'''
if old_motion_helpers not in text:
    raise SystemExit("[GGQ] exp10 motion-helper anchor not found")
text = text.replace(old_motion_helpers, "", 1)

old_width = "      var maxEyeWidth = captureEyeWidth(now);\n"
new_width = "      var maxEyeWidth = CAPTURE_MAX_EYE_WIDTH;\n"
if old_width not in text:
    raise SystemExit("[GGQ] exp10 capture-width call anchor not found")
text = text.replace(old_width, new_width, 1)

old_listeners = '''
  // Dynamic capture resolution: keep full 720px quality at rest, but reduce
  // JPEG/decode traffic to 540px during active manipulation and for 300ms after.
  document.addEventListener('pointerdown', markStereoMotion, true);
  document.addEventListener('pointermove', markPointerMotion, true);
  document.addEventListener('pointerup', markStereoMotion, true);
  document.addEventListener('mousedown', markStereoMotion, true);
  document.addEventListener('mousemove', markPointerMotion, true);
  document.addEventListener('mouseup', markStereoMotion, true);
  document.addEventListener('touchstart', markStereoMotion, { capture: true, passive: true });
  document.addEventListener('touchmove', markStereoMotion, { capture: true, passive: true });
  document.addEventListener('touchend', markStereoMotion, { capture: true, passive: true });
  document.addEventListener('wheel', markStereoMotion, { capture: true, passive: true });
  document.addEventListener('keydown', markStereoMotion, true);
'''
if old_listeners not in text:
    raise SystemExit("[GGQ] exp10 interaction-listener anchor not found")
text = text.replace(old_listeners, "", 1)

for forbidden in (
    "CAPTURE_ACTIVE_EYE_WIDTH",
    "CAPTURE_IDLE_EYE_WIDTH",
    "CAPTURE_IDLE_DELAY_MS",
    "lastStereoMotionAt",
    "markStereoMotion",
    "markPointerMotion",
    "captureEyeWidth(",
    "540",
):
    if forbidden in text:
        raise RuntimeError(f"[GGQ] exp10 dynamic-resolution residue remains: {forbidden}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp10 fixed 720px capture; dynamic 540/motion tracking removed completely")
