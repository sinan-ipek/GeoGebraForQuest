#!/usr/bin/env python3
"""Exp11: small stereo FPS bump plus depth-pointer bridge.

Keep exp10's fixed 720px, demand-driven RIGHT-only renderer architecture.
- Increase maximum requested stereo cadence from 20 fps (50 ms) to ~24 fps (42 ms).
- Report when the Quest pointer is inside the transparent live 3D hole so Android
  can hide Meta's flat panel laser and leave GeoGebra's stereo 3D cursor/highlight
  as the visible depth cue.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp11.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP11_DEPTH_POINTER" in text:
    print("[GGQ] exp11 stereo cadence/depth-pointer patch already present")
    raise SystemExit(0)

if "  var CAPTURE_INTERVAL_MS = 50;\n" not in text:
    raise SystemExit("[GGQ] exp11 50ms capture interval anchor not found")
text = text.replace(
    "  var CAPTURE_INTERVAL_MS = 50;\n",
    "  // Exp11: ~24 fps maximum stereo-pair request cadence (1000/24 ~= 41.7ms).\n"
    "  var CAPTURE_INTERVAL_MS = 42;\n",
    1,
)

# Update the exp8 explanatory comment if it survived the scheduler patch.
text = text.replace(
    "  // Exp8: 20 fps is a maximum stereo-pair request cadence, not a demand\n",
    "  // Exp11: ~24 fps is a maximum stereo-pair request cadence, not a demand\n",
    1,
)

# Whenever the 3D hole disappears, restore the normal Meta laser immediately.
anchor_restore = "  function restoreSelectiveHole() {\n    holeApplyGeneration++;\n"
replacement_restore = (
    "  function restoreSelectiveHole() {\n"
    "    setDepthPointerActive(false);\n"
    "    holeApplyGeneration++;\n"
)
if anchor_restore not in text:
    raise SystemExit("[GGQ] exp11 restoreSelectiveHole anchor not found")
text = text.replace(anchor_restore, replacement_restore, 1)

anchor_bottom = "  addEventListener('resize', schedule, { passive: true });\n  addEventListener('scroll', schedule, true);\n\n  setInterval(schedule, 500);\n"
if anchor_bottom not in text:
    raise SystemExit("[GGQ] exp11 bottom listener anchor not found")

bridge_code = r'''  // EXP11_DEPTH_POINTER: Meta's system ray physically intersects the flat A panel.
  // Keep that input/raycast path intact, but hide its flat visual laser over the live 3D hole.
  // GeoGebra's own cursor/highlight is rendered independently in LEFT/RIGHT eye passes and
  // therefore appears at the actual picked 3D depth.
  var depthPointerActive = false;

  function setDepthPointerActive(active) {
    active = !!active;
    if (depthPointerActive === active) return;
    depthPointerActive = active;
    bridge('setDepthPointerActive', active ? '1' : '0');
  }

  function depthPointerUiOccluded(x, y) {
    var top = null;
    try { top = document.elementFromPoint(x, y); } catch (_) {}
    if (!top || typeof top.closest !== 'function') return false;
    try {
      return !!top.closest(
        '.gwt-PopupPanel,.contextMenu,.selectionMenu,.menuPanel,.matMenu,' +
        '.propertiesPanel,.dialog,.modal,[role="menu"],[role="dialog"],[aria-modal="true"]'
      );
    } catch (_) {
      return false;
    }
  }

  function updateDepthPointerAt(x, y) {
    if (typeof x !== 'number' || !isFinite(x) ||
        typeof y !== 'number' || !isFinite(y)) {
      setDepthPointerActive(false);
      return;
    }

    var canvas = holeCanvas && holeCanvas.isConnected ? holeCanvas : find3DCanvas();
    var r = rawRect(canvas);
    if (!r) {
      setDepthPointerActive(false);
      return;
    }

    var inside = x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    if (inside && depthPointerUiOccluded(x, y)) inside = false;
    setDepthPointerActive(inside);
  }

  function updateDepthPointerFromEvent(event) {
    if (!event) {
      setDepthPointerActive(false);
      return;
    }
    updateDepthPointerAt(Number(event.clientX), Number(event.clientY));
  }

  function updateDepthPointerFromTouch(event) {
    var touch = null;
    if (event && event.touches && event.touches.length) {
      touch = event.touches[0];
    } else if (event && event.changedTouches && event.changedTouches.length) {
      touch = event.changedTouches[0];
    }
    if (touch) {
      updateDepthPointerAt(Number(touch.clientX), Number(touch.clientY));
    } else {
      setDepthPointerActive(false);
    }
  }

  document.addEventListener('pointermove', updateDepthPointerFromEvent, true);
  document.addEventListener('pointerdown', updateDepthPointerFromEvent, true);
  document.addEventListener('mousemove', updateDepthPointerFromEvent, true);
  document.addEventListener('mousedown', updateDepthPointerFromEvent, true);
  document.addEventListener('touchstart', updateDepthPointerFromTouch,
      { capture: true, passive: true });
  document.addEventListener('touchmove', updateDepthPointerFromTouch,
      { capture: true, passive: true });
  document.addEventListener('touchend', updateDepthPointerFromTouch,
      { capture: true, passive: true });
  document.addEventListener('pointerleave', function () { setDepthPointerActive(false); }, true);
  document.addEventListener('mouseleave', function () { setDepthPointerActive(false); }, true);
  addEventListener('blur', function () { setDepthPointerActive(false); });

'''

text = text.replace(
    anchor_bottom,
    "  addEventListener('resize', schedule, { passive: true });\n"
    "  addEventListener('scroll', schedule, true);\n\n" +
    bridge_code +
    "  setInterval(schedule, 500);\n",
    1,
)

for forbidden in (
    "CAPTURE_ACTIVE_EYE_WIDTH",
    "CAPTURE_IDLE_EYE_WIDTH",
    "CAPTURE_IDLE_DELAY_MS",
    "540",
):
    if forbidden in text:
        raise RuntimeError(f"[GGQ] exp11 must retain exp10 fixed-720 policy; found {forbidden}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp11 ~24fps fixed-720 capture + stereo depth-pointer bridge")
