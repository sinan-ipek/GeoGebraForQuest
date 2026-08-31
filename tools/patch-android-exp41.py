#!/usr/bin/env python3
"""Exp41: native WebView pointer gesture for physical-Grip temporary Move."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp41.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
panel = panel_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")

for required in ("EXP40_PASSWORD_IME_COMMIT", "EXP40_PHYSICAL_GRIP_LATCH",
                 "EXP39_RIGHT_THUMB_2D_3D_ZOOM"):
    if required not in panel + shortcut:
        raise RuntimeError(f"exp41 baseline missing: {required}")

anchor = "import android.os.Message\n"
if anchor not in panel:
    raise RuntimeError("exp41 SystemClock import anchor missing")
panel = panel.replace(anchor, anchor + "import android.os.SystemClock\n", 1)

start = panel.find("    // EXP39_GRIP_TEMPORARY_MOVE:")
end = panel.find("    // EXP39_RIGHT_THUMB_2D_3D_ZOOM:", start)
if start < 0 or end < 0:
    raise RuntimeError("exp41 Grip bridge boundaries missing")

native_bridge = r'''    // EXP41_NATIVE_GRIP_MOVE: use the same WebView touch channel as Trigger.
    // JavaScript changes/restores the tool; Android owns DOWN/MOVE/UP.
    private var gripGestureActive = false
    private var gripDownTime = 0L
    private var panelPointerX = Float.NaN
    private var panelPointerY = Float.NaN

    fun rememberPanelPointer(event: MotionEvent) {
        if (!event.x.isFinite() || !event.y.isFinite()) return
        panelPointerX = event.x
        panelPointerY = event.y
    }

    private fun dispatchGripTouch(view: WebView, action: Int): Boolean {
        if (!panelPointerX.isFinite() || !panelPointerY.isFinite()) return false
        val now = SystemClock.uptimeMillis()
        if (action == MotionEvent.ACTION_DOWN) gripDownTime = now
        val event = MotionEvent.obtain(
            gripDownTime.takeIf { it > 0L } ?: now,
            now,
            action,
            panelPointerX,
            panelPointerY,
            0,
        )
        return try {
            view.dispatchTouchEvent(event)
        } finally {
            event.recycle()
        }
    }

    fun setGripMove(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            if (active) {
                if (gripGestureActive || !panelPointerX.isFinite() || !panelPointerY.isFinite()) {
                    return@post
                }
                main.evaluateJavascript(
                    "if(window.__ggqBeginGripMoveMode){window.__ggqBeginGripMoveMode();}else{false;}",
                ) { result ->
                    if (result == "true" && dispatchGripTouch(main, MotionEvent.ACTION_DOWN)) {
                        gripGestureActive = true
                    }
                }
            } else {
                if (gripGestureActive) {
                    dispatchGripTouch(main, MotionEvent.ACTION_UP)
                    gripGestureActive = false
                }
                main.evaluateJavascript(
                    "if(window.__ggqEndGripMoveMode){window.__ggqEndGripMoveMode();}",
                    null,
                )
            }
        }
        return true
    }

    fun updateGripMove(): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            if (gripGestureActive) dispatchGripTouch(main, MotionEvent.ACTION_MOVE)
        }
        return true
    }

'''
panel = panel[:start] + native_bridge + panel[end:]

old_state = ("          window.__ggqGripMoveState = null;\n"
             "          window.__ggqGripMoveDispatching = false;\n")
if old_state not in panel:
    raise RuntimeError("exp41 DOM Grip state anchor missing")
panel = panel.replace(old_state, "          window.__ggqGripMoveOldMode = null;\n", 1)

js_start = panel.find("          // EXP39_GRIP_MOVE_DOM_DRAG:")
js_end_marker = "          document.addEventListener('pointermove', updateGripMove, true);\n"
js_end = panel.find(js_end_marker, js_start)
if js_start < 0 or js_end < 0:
    raise RuntimeError("exp41 DOM Grip implementation missing")
js_end += len(js_end_marker)
mode_js = r'''          // EXP41_GRIP_MODE_ONLY: native MotionEvents perform the drag.
          window.__ggqBeginGripMoveMode = function () {
            if (!window.ggbApplet || typeof window.ggbApplet.setMode !== 'function' ||
                typeof window.ggbApplet.getMode !== 'function') return false;
            if (window.__ggqGripMoveOldMode !== null) return true;
            var oldMode = Number(window.ggbApplet.getMode());
            if (!isFinite(oldMode)) return false;
            window.__ggqGripMoveOldMode = oldMode;
            try { window.ggbApplet.setMode(0); return true; }
            catch (_) { window.__ggqGripMoveOldMode = null; return false; }
          };

          window.__ggqEndGripMoveMode = function () {
            var oldMode = window.__ggqGripMoveOldMode;
            window.__ggqGripMoveOldMode = null;
            if (oldMode === null || !window.ggbApplet ||
                typeof window.ggbApplet.setMode !== 'function') return false;
            try { window.ggbApplet.setMode(oldMode); return true; }
            catch (_) { return false; }
          };
'''
panel = panel[:js_start] + mode_js + panel[js_end:]

touch_anchor = '''        setOnTouchListener { touchedView, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }
'''
touch_new = '''        setOnTouchListener { touchedView, event ->
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }

        // EXP41_PANEL_HOVER_TRACKING: observe ray motion without consuming it.
        // Trigger remains the ordinary panel mouse button.
        setOnGenericMotionListener { _, event ->
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            false
        }
'''
if touch_anchor not in panel:
    raise RuntimeError("exp41 touch listener anchor missing")
panel = panel.replace(touch_anchor, touch_new, 1)

grip = '''        if (physicalGripDown && !rightGripMoveActive) {
            rightGripMoveActive = activity.onQuestGripMovePressed()
        } else if (!physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveReleased()
            rightGripMoveActive = false
        }
'''
grip_new = '''        if (physicalGripDown && !rightGripMoveActive) {
            rightGripMoveActive = activity.onQuestGripMovePressed()
        } else if (physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveUpdated()
        } else if (!physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveReleased()
            rightGripMoveActive = false
        }
'''
if grip not in shortcut:
    raise RuntimeError("exp41 Grip latch anchor missing")
shortcut = shortcut.replace(grip, grip_new, 1)

activity_anchor = '''    internal fun onQuestGripMoveReleased() {
        GeoGebraWebNavigation.setGripMove(false)
    }

'''
activity_new = '''    internal fun onQuestGripMoveUpdated() {
        GeoGebraWebNavigation.updateGripMove()
    }

    internal fun onQuestGripMoveReleased() {
        GeoGebraWebNavigation.setGripMove(false)
    }

'''
if activity_anchor not in activity:
    raise RuntimeError("exp41 Activity Grip anchor missing")
activity = activity.replace(activity_anchor, activity_new, 1)

for required in ("EXP41_NATIVE_GRIP_MOVE", "MotionEvent.ACTION_DOWN",
                 "MotionEvent.ACTION_MOVE", "MotionEvent.ACTION_UP",
                 "EXP41_GRIP_MODE_ONLY", "EXP41_PANEL_HOVER_TRACKING"):
    if required not in panel:
        raise RuntimeError(f"exp41 panel requirement missing: {required}")
for forbidden in ("dispatchGripMouse(", "__ggqGripMoveDispatching",
                  "document.addEventListener('pointermove', updateGripMove"):
    if forbidden in panel:
        raise RuntimeError(f"exp41 obsolete DOM Grip remains: {forbidden}")
if "activity.onQuestGripMoveUpdated()" not in shortcut:
    raise RuntimeError("exp41 continuous update missing")
if "GeoGebraWebNavigation.updateGripMove()" not in activity:
    raise RuntimeError("exp41 Activity update bridge missing")

panel_path.write_text(panel, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += ("right_grip=exp41 physical squeeze -> native WebView DOWN/MOVE/UP temporary Move\n"
              "trigger=exp41 unchanged Meta panel pointer click and drag\n")
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp41 native Grip Move + unchanged Trigger + cross-view zoom installed")
