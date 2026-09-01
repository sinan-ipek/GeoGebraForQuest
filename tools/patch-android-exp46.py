#!/usr/bin/env python3
"""Exp46: arm Move for the view selected by the synthetic Grip press."""

from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp46.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")

for required in (
    "EXP44_CSS_POINTER_TRANSPARENT_CANVAS_GATE",
    "EXP43_ISOLATED_GRIP_POINTER",
    "EXP41_GRIP_MODE_ONLY",
):
    if required not in panel:
        raise RuntimeError(f"exp46 baseline missing: {required}")

old_begin = r'''          window.__ggqBeginGripMoveModeAt = function (fallbackX, fallbackY) {
            var p = ggqGripCssPoint(fallbackX, fallbackY);
            if (!ggqGripCanvasAt(p) || !window.ggbApplet ||
                typeof window.ggbApplet.setMode !== 'function' ||
                typeof window.ggbApplet.getMode !== 'function') return false;
            if (window.__ggqGripMoveOldMode !== null) return true;
            var oldMode = Number(window.ggbApplet.getMode());
            if (!isFinite(oldMode)) return false;
            window.__ggqGripMoveOldMode = oldMode;
            try { window.ggbApplet.setMode(0); return true; }
            catch (_) { window.__ggqGripMoveOldMode = null; return false; }
          };
'''

new_begin = r'''          // EXP46_TARGET_VIEW_GRIP_FOCUS: do not select Move on the old
          // active view. Arm GeoGebra so the synthetic DOWN first focuses its real
          // 2D/3D ray target, then enters temporary Move before tool processing.
          window.__ggqBeginGripMoveModeAt = function (fallbackX, fallbackY) {
            var p = ggqGripCssPoint(fallbackX, fallbackY);
            if (!ggqGripCanvasAt(p) || !window.ggbApplet ||
                typeof window.ggbApplet.getMode !== 'function' ||
                typeof window.ggqArmGripMoveForNextPress !== 'function') return false;
            if (window.__ggqGripMoveOldMode !== null) return true;
            var oldMode = Number(window.ggbApplet.getMode());
            if (!isFinite(oldMode)) return false;
            try {
              if (window.ggqArmGripMoveForNextPress(oldMode) !== true) return false;
              window.__ggqGripMoveOldMode = oldMode;
              return true;
            } catch (_) {
              window.__ggqGripMoveOldMode = null;
              try { window.ggqEndGripMoveForTargetView(); } catch (_) {}
              return false;
            }
          };
'''
panel = replace_once(panel, old_begin, new_begin, "Exp46 target-view Grip begin")

old_end = r'''          window.__ggqEndGripMoveMode = function () {
            var oldMode = window.__ggqGripMoveOldMode;
            window.__ggqGripMoveOldMode = null;
            if (oldMode === null || !window.ggbApplet ||
                typeof window.ggbApplet.setMode !== 'function') return false;
            try { window.ggbApplet.setMode(oldMode); return true; }
            catch (_) { return false; }
          };
'''
new_end = r'''          window.__ggqEndGripMoveMode = function () {
            var hadGrip = window.__ggqGripMoveOldMode !== null;
            window.__ggqGripMoveOldMode = null;
            if (typeof window.ggqEndGripMoveForTargetView !== 'function') return false;
            try { return window.ggqEndGripMoveForTargetView() === true || hadGrip; }
            catch (_) { return false; }
          };
'''
panel = replace_once(panel, old_end, new_end, "Exp46 target-view Grip end")

old_callback = '''            if (result == "true" && gripGestureRequested &&
                dispatchGripTouch(main, MotionEvent.ACTION_DOWN)) {
                gripGestureActive = true
                lastGripX = panelPointerX
                lastGripY = panelPointerY
            } else if (result != "true") {
                gripGestureRequested = false
            }
'''
new_callback = '''            if (result == "true" && gripGestureRequested &&
                dispatchGripTouch(main, MotionEvent.ACTION_DOWN)) {
                gripGestureActive = true
                lastGripX = panelPointerX
                lastGripY = panelPointerY
            } else {
                // EXP46_ARM_FAILURE_CLEANUP: an armed press must never leak into
                // the next real Trigger when Grip was released or dispatch failed.
                gripGestureRequested = false
                main.evaluateJavascript(
                    "if(window.__ggqEndGripMoveMode){window.__ggqEndGripMoveMode();}",
                    null,
                )
            }
'''
panel = replace_once(panel, old_callback, new_callback, "Exp46 armed press cleanup")

for required in (
    "EXP46_TARGET_VIEW_GRIP_FOCUS",
    "ggqArmGripMoveForNextPress(oldMode)",
    "ggqEndGripMoveForTargetView",
    "EXP46_ARM_FAILURE_CLEANUP",
):
    if required not in panel:
        raise RuntimeError(f"exp46 Android requirement missing: {required}")

begin_at = panel.index("window.__ggqBeginGripMoveModeAt")
end_at = panel.index("window.__ggqEndGripMoveMode", begin_at)
if "ggbApplet.setMode(0)" in panel[begin_at:end_at]:
    raise RuntimeError("exp46 still sets Move on the previously active view")

panel_path.write_text(panel, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "right_grip=exp46 ray-target view focused before temporary Move/tool processing\n"
        "trigger=exp46 unchanged ordinary pointer; no preliminary click needed for Grip\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp46 target-view Grip focus bridge installed")
