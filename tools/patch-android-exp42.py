#!/usr/bin/env python3
"""Exp42: frame-coalesced, jitter-filtered physical-Grip Move."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp42.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
panel = panel_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")

for required in ("EXP41_NATIVE_GRIP_MOVE", "EXP41_PANEL_HOVER_TRACKING",
                 "EXP40_PASSWORD_IME_COMMIT", "EXP39_RIGHT_THUMB_2D_3D_ZOOM"):
    if required not in panel + shortcut:
        raise RuntimeError(f"exp42 baseline missing: {required}")

start = panel.find("    // EXP41_NATIVE_GRIP_MOVE:")
end = panel.find("    // EXP35_RIGHT_THUMB_ZOOM_BRIDGE:", start)
if start < 0 or end < 0:
    raise RuntimeError("exp42 native Grip bridge boundaries missing")

smooth_bridge = r'''    // EXP42_SMOOTH_NATIVE_GRIP_MOVE: ray updates, not controller ticks,
    // drive a maximum of one native MOVE per display frame. Tiny ray jitter is ignored.
    private var gripGestureRequested = false
    private var gripGestureActive = false
    private var gripDownTime = 0L
    private var panelPointerX = Float.NaN
    private var panelPointerY = Float.NaN
    private var panelPointerSource = 0
    private var lastGripX = Float.NaN
    private var lastGripY = Float.NaN
    private var gripMovePosted = false
    private var dispatchingGripTouch = false
    private const val GRIP_MOVE_EPSILON_PX = 0.75f

    fun isDispatchingGripTouch(): Boolean = dispatchingGripTouch

    fun rememberPanelPointer(event: MotionEvent) {
        if (dispatchingGripTouch || !event.x.isFinite() || !event.y.isFinite()) return
        panelPointerX = event.x
        panelPointerY = event.y
        if (event.source != 0) panelPointerSource = event.source
        if (gripGestureActive) scheduleGripMove()
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
        if (panelPointerSource != 0) event.source = panelPointerSource
        dispatchingGripTouch = true
        return try {
            view.dispatchTouchEvent(event)
        } finally {
            dispatchingGripTouch = false
            event.recycle()
        }
    }

    private fun scheduleGripMove() {
        val main = mainWebView.get() ?: return
        if (gripMovePosted) return
        gripMovePosted = true
        main.postOnAnimation {
            gripMovePosted = false
            if (!gripGestureActive || !panelPointerX.isFinite() ||
                !panelPointerY.isFinite()) return@postOnAnimation
            val dx = panelPointerX - lastGripX
            val dy = panelPointerY - lastGripY
            if (lastGripX.isFinite() && lastGripY.isFinite() &&
                dx * dx + dy * dy < GRIP_MOVE_EPSILON_PX * GRIP_MOVE_EPSILON_PX) {
                return@postOnAnimation
            }
            if (dispatchGripTouch(main, MotionEvent.ACTION_MOVE)) {
                lastGripX = panelPointerX
                lastGripY = panelPointerY
            }
        }
    }

    fun setGripMove(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            if (active) {
                if (gripGestureRequested || gripGestureActive ||
                    !panelPointerX.isFinite() || !panelPointerY.isFinite()) return@post
                gripGestureRequested = true
                main.evaluateJavascript(
                    "if(window.__ggqBeginGripMoveMode){window.__ggqBeginGripMoveMode();}else{false;}",
                ) { result ->
                    if (result == "true" && gripGestureRequested &&
                        dispatchGripTouch(main, MotionEvent.ACTION_DOWN)) {
                        gripGestureActive = true
                        lastGripX = panelPointerX
                        lastGripY = panelPointerY
                    } else if (result != "true") {
                        gripGestureRequested = false
                    }
                }
            } else {
                gripGestureRequested = false
                gripMovePosted = false
                if (gripGestureActive) dispatchGripTouch(main, MotionEvent.ACTION_UP)
                gripGestureActive = false
                lastGripX = Float.NaN
                lastGripY = Float.NaN
                main.evaluateJavascript(
                    "if(window.__ggqEndGripMoveMode){window.__ggqEndGripMoveMode();}",
                    null,
                )
            }
        }
        return true
    }

'''
panel = panel[:start] + smooth_bridge + panel[end:]

# A synthetic Grip DOWN must not restart the IME/focus connection.
old_touch = '''        setOnTouchListener { touchedView, event ->
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }
'''
new_touch = '''        setOnTouchListener { touchedView, event ->
            val gripTouch = registerAsMain && GeoGebraWebNavigation.isDispatchingGripTouch()
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            if (event.actionMasked == MotionEvent.ACTION_DOWN && !gripTouch) {
                refreshImeConnection(touchedView)
            }
            false
        }
'''
if old_touch not in panel:
    raise RuntimeError("exp42 Exp41 touch listener anchor missing")
panel = panel.replace(old_touch, new_touch, 1)

# Remove tick-driven MOVE flooding. New Meta ray coordinates schedule moves directly.
old_latch = '''        if (physicalGripDown && !rightGripMoveActive) {
            rightGripMoveActive = activity.onQuestGripMovePressed()
        } else if (physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveUpdated()
        } else if (!physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveReleased()
            rightGripMoveActive = false
        }
'''
new_latch = '''        if (physicalGripDown && !rightGripMoveActive) {
            rightGripMoveActive = activity.onQuestGripMovePressed()
        } else if (!physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveReleased()
            rightGripMoveActive = false
        }
'''
if old_latch not in shortcut:
    raise RuntimeError("exp42 tick-driven Grip latch anchor missing")
shortcut = shortcut.replace(old_latch, new_latch, 1)

old_activity = '''    internal fun onQuestGripMoveUpdated() {
        GeoGebraWebNavigation.updateGripMove()
    }

'''
if old_activity not in activity:
    raise RuntimeError("exp42 Activity update bridge missing")
activity = activity.replace(old_activity, "", 1)

for required in ("EXP42_SMOOTH_NATIVE_GRIP_MOVE", "postOnAnimation",
                 "GRIP_MOVE_EPSILON_PX", "isDispatchingGripTouch",
                 "if (event.source != 0) panelPointerSource = event.source"):
    if required not in panel:
        raise RuntimeError(f"exp42 panel requirement missing: {required}")
for forbidden in ("fun updateGripMove()", "activity.onQuestGripMoveUpdated()"):
    if forbidden in panel + shortcut + activity:
        raise RuntimeError(f"exp42 tick-driven residue remains: {forbidden}")

panel_path.write_text(panel, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += ("right_grip=exp42 ray-driven frame-coalesced native Move; 0.75px jitter filter\n"
              "trigger=exp42 unchanged Meta panel pointer; Grip skips IME refresh\n")
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp42 smooth coalesced Grip Move installed")
