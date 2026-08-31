#!/usr/bin/env python3
"""Exp43: isolate Grip from Trigger/UI and gate Grip to graph canvases."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp43.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")

for required in ("EXP42_SMOOTH_NATIVE_GRIP_MOVE", "EXP41_GRIP_MODE_ONLY",
                 "EXP40_PASSWORD_IME_COMMIT", "EXP39_RIGHT_THUMB_2D_3D_ZOOM"):
    if required not in panel:
        raise RuntimeError(f"exp43 baseline missing: {required}")

start = panel.find("    // EXP42_SMOOTH_NATIVE_GRIP_MOVE:")
end = panel.find("    // EXP35_RIGHT_THUMB_ZOOM_BRIDGE:", start)
if start < 0 or end < 0:
    raise RuntimeError("exp43 Exp42 bridge boundaries missing")

isolated_bridge = r'''    // EXP43_ISOLATED_GRIP_POINTER: Grip starts only after a fresh ray
    // sample over a graph canvas. Trigger cancels the synthetic Grip stream first.
    private var gripGestureRequested = false
    private var gripBeginInFlight = false
    private var gripGestureActive = false
    private var gripDownTime = 0L
    private var panelPointerX = Float.NaN
    private var panelPointerY = Float.NaN
    private var panelPointerSource = 0
    private var panelPointerSerial = 0L
    private var gripRequestPointerSerial = 0L
    private var lastGripX = Float.NaN
    private var lastGripY = Float.NaN
    private var gripMovePosted = false
    private var dispatchingGripTouch = false
    private const val GRIP_MOVE_EPSILON_PX = 0.75f
    private const val GRIP_FRESH_RAY_FALLBACK_MS = 48L

    fun isDispatchingGripTouch(): Boolean = dispatchingGripTouch

    fun rememberPanelPointer(event: MotionEvent) {
        if (dispatchingGripTouch || !event.x.isFinite() || !event.y.isFinite()) return
        panelPointerX = event.x
        panelPointerY = event.y
        panelPointerSerial += 1L
        if (event.source != 0) panelPointerSource = event.source
        if (gripGestureRequested && !gripGestureActive && !gripBeginInFlight &&
            panelPointerSerial > gripRequestPointerSerial) {
            beginGripAtFreshPointer()
        } else if (gripGestureActive) {
            scheduleGripMove()
        }
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

    private fun beginGripAtFreshPointer() {
        val main = mainWebView.get() ?: return
        if (!gripGestureRequested || gripGestureActive || gripBeginInFlight ||
            !panelPointerX.isFinite() || !panelPointerY.isFinite()) return
        gripBeginInFlight = true
        val x = panelPointerX
        val y = panelPointerY
        main.evaluateJavascript(
            "if(window.__ggqBeginGripMoveModeAt){" +
                "window.__ggqBeginGripMoveModeAt($x,$y);" +
                "}else{false;}",
        ) { result ->
            gripBeginInFlight = false
            if (result == "true" && gripGestureRequested &&
                dispatchGripTouch(main, MotionEvent.ACTION_DOWN)) {
                gripGestureActive = true
                lastGripX = panelPointerX
                lastGripY = panelPointerY
            } else if (result != "true") {
                gripGestureRequested = false
            }
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

    private fun finishGripGesture(view: WebView, cancel: Boolean) {
        gripGestureRequested = false
        gripBeginInFlight = false
        gripMovePosted = false
        if (gripGestureActive) {
            dispatchGripTouch(
                view,
                if (cancel) MotionEvent.ACTION_CANCEL else MotionEvent.ACTION_UP,
            )
        }
        gripGestureActive = false
        lastGripX = Float.NaN
        lastGripY = Float.NaN
        view.evaluateJavascript(
            "if(window.__ggqEndGripMoveMode){window.__ggqEndGripMoveMode();}",
            null,
        )
    }

    fun cancelGripForRealTrigger(view: WebView) {
        if (!gripGestureRequested && !gripGestureActive && !gripBeginInFlight) return
        finishGripGesture(view, true)
    }

    fun setGripMove(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            if (active) {
                if (gripGestureRequested || gripGestureActive || gripBeginInFlight ||
                    !panelPointerX.isFinite() || !panelPointerY.isFinite()) return@post
                gripGestureRequested = true
                gripRequestPointerSerial = panelPointerSerial
                // A stationary ray may not produce another sample; use its current
                // coordinate after three display frames, still subject to canvas gating.
                main.postDelayed({
                    if (gripGestureRequested && !gripGestureActive && !gripBeginInFlight) {
                        beginGripAtFreshPointer()
                    }
                }, GRIP_FRESH_RAY_FALLBACK_MS)
            } else {
                finishGripGesture(main, false)
            }
        }
        return true
    }

'''
panel = panel[:start] + isolated_bridge + panel[end:]

old_js = r'''          window.__ggqBeginGripMoveMode = function () {
            if (!window.ggbApplet || typeof window.ggbApplet.setMode !== 'function' ||
                typeof window.ggbApplet.getMode !== 'function') return false;
            if (window.__ggqGripMoveOldMode !== null) return true;
            var oldMode = Number(window.ggbApplet.getMode());
            if (!isFinite(oldMode)) return false;
            window.__ggqGripMoveOldMode = oldMode;
            try { window.ggbApplet.setMode(0); return true; }
            catch (_) { window.__ggqGripMoveOldMode = null; return false; }
          };
'''
new_js = r'''          // EXP43_GRAPH_CANVAS_GRIP_GATE: never start Grip on menus,
          // toolbars, dialogs or the Open screen.
          function ggqGripCanvasAt(x, y) {
            var elements = document.elementsFromPoint(Number(x), Number(y));
            for (var i = 0; i < elements.length; i++) {
              var el = elements[i];
              if (!el || String(el.tagName).toLowerCase() !== 'canvas') continue;
              var rect = el.getBoundingClientRect();
              var style = window.getComputedStyle(el);
              if (rect.width >= 100 && rect.height >= 100 &&
                  style.display !== 'none' && style.visibility !== 'hidden' &&
                  Number(style.opacity || 1) > 0) return el;
            }
            return null;
          }

          window.__ggqBeginGripMoveModeAt = function (x, y) {
            if (!ggqGripCanvasAt(x, y) || !window.ggbApplet ||
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
if old_js not in panel:
    raise RuntimeError("exp43 Exp41 JS start anchor missing")
panel = panel.replace(old_js, new_js, 1)

old_touch = '''        setOnTouchListener { touchedView, event ->
            val gripTouch = registerAsMain && GeoGebraWebNavigation.isDispatchingGripTouch()
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            if (event.actionMasked == MotionEvent.ACTION_DOWN && !gripTouch) {
                refreshImeConnection(touchedView)
            }
            false
        }
'''
new_touch = '''        setOnTouchListener { touchedView, event ->
            val gripTouch = registerAsMain && GeoGebraWebNavigation.isDispatchingGripTouch()
            if (registerAsMain && event.actionMasked == MotionEvent.ACTION_DOWN && !gripTouch) {
                GeoGebraWebNavigation.cancelGripForRealTrigger(touchedView as WebView)
            }
            if (registerAsMain) GeoGebraWebNavigation.rememberPanelPointer(event)
            if (event.actionMasked == MotionEvent.ACTION_DOWN && !gripTouch) {
                refreshImeConnection(touchedView)
            }
            false
        }
'''
if old_touch not in panel:
    raise RuntimeError("exp43 Exp42 touch arbitration anchor missing")
panel = panel.replace(old_touch, new_touch, 1)

for required in ("EXP43_ISOLATED_GRIP_POINTER", "EXP43_GRAPH_CANVAS_GRIP_GATE",
                 "cancelGripForRealTrigger", "MotionEvent.ACTION_CANCEL",
                 "gripRequestPointerSerial", "__ggqBeginGripMoveModeAt"):
    if required not in panel:
        raise RuntimeError(f"exp43 requirement missing: {required}")
for forbidden in ("window.__ggqBeginGripMoveMode = function", "fun updateGripMove()"):
    if forbidden in panel:
        raise RuntimeError(f"exp43 obsolete behavior remains: {forbidden}")

panel_path.write_text(panel, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += ("right_grip=exp43 fresh-ray graph-canvas-only native Move; Trigger cancels Grip\n"
              "ui_input=exp43 menus/Open never receive synthetic Grip pointer\n"
              "startup_splash=exp43 lossless 1254px-class L1/R1 sources\n")
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp43 isolated Grip/Trigger and graph-canvas gate installed")
