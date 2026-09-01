#!/usr/bin/env python3
"""Exp11+: fixed-720 ~24fps depth-pointer bridge plus exp16 lifecycle re-arm."""

from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-quest-stereo-js-exp11.py <quest-stereo-layout.js>")

path = Path(sys.argv[1]).resolve()
text = path.read_text(encoding="utf-8")

if "EXP11_DEPTH_POINTER" not in text:
    if "  var CAPTURE_INTERVAL_MS = 50;\n" not in text:
        raise SystemExit("[GGQ] exp11 50ms capture interval anchor not found")
    text = text.replace(
        "  var CAPTURE_INTERVAL_MS = 50;\n",
        "  // Exp11: ~24 fps maximum stereo-pair request cadence (1000/24 ~= 41.7ms).\n"
        "  var CAPTURE_INTERVAL_MS = 42;\n",
        1,
    )

    text = text.replace(
        "  // Exp8: 20 fps is a maximum stereo-pair request cadence, not a demand\n",
        "  // Exp11: ~24 fps is a maximum stereo-pair request cadence, not a demand\n",
        1,
    )

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
  // Keep that input/raycast path intact. GeoGebra's own cursor/highlight is rendered
  // independently in LEFT/RIGHT eye passes and therefore remains the depth cue.
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
else:
    print("[GGQ] exp11 stereo cadence/depth-pointer patch already present")

# Exp16 must be part of the actual build chain, not merely checked into tools/.
exp16 = Path(__file__).with_name("patch-quest-stereo-js-exp16.py")
subprocess.run([sys.executable, str(exp16), str(path)], check=True)
