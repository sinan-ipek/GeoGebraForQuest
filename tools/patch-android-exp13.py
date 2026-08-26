#!/usr/bin/env python3
"""Exp13 Android/WebView bridge for right-grip temporary 3D rotation."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp13.py <repo-root>")

root = Path(sys.argv[1]).resolve()

# ---------------------------------------------------------------------------
# WebView navigation + JS pointer routing.
# ---------------------------------------------------------------------------
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

if "EXP13_GRIP_ROTATE_BRIDGE" not in text:
    nav_anchor = '''    fun toggleContextMenu(): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            main.evaluateJavascript(
                "if(window.__ggqToggleContextMenu){window.__ggqToggleContextMenu();}",
                null,
            )
        }
        return true
    }
'''
    nav_insert = nav_anchor + '''
    // EXP13_GRIP_ROTATE_BRIDGE: right Grip is a momentary modifier, not a permanent tool change.
    fun setGripRotate(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        val jsActive = if (active) "true" else "false"
        main.post {
            main.evaluateJavascript(
                "if(window.__ggqSetGripRotate){window.__ggqSetGripRotate($jsActive);}",
                null,
            )
        }
        return true
    }
'''
    if nav_anchor not in text:
        raise RuntimeError("exp13 navigation toggleContextMenu anchor not found")
    text = text.replace(nav_anchor, nav_insert, 1)

    state_anchor = '''          window.__ggqContextSupportInstalled = true;
          window.__ggqContextMenuVisible = false;
          window.__ggqLastPointer = {
'''
    state_insert = '''          window.__ggqContextSupportInstalled = true;
          window.__ggqContextMenuVisible = false;
          window.__ggqGripRotateActive = false;
          window.__ggqLastPointer = {
'''
    if state_anchor not in text:
        raise RuntimeError("exp13 JS context state anchor not found")
    text = text.replace(state_anchor, state_insert, 1)

    helper_anchor = '''            return { x: p.x, y: p.y };
          }

          function sendEscape(target) {
'''
    helper_insert = '''            return { x: p.x, y: p.y };
          }

          // EXP13_GRIP_ROTATE_BRIDGE: route hover motion into GeoGebra's native
          // temporary rotate mode while right Grip is held.
          window.__ggqSetGripRotate = function (active) {
            var p = window.__ggqLastPointer || { x: 1, y: 1 };
            var local = findViewCoordinates(p);

            if (active) {
              var started = false;
              try {
                if (typeof window.ggqBeginGripRotate === 'function') {
                  started = !!window.ggqBeginGripRotate(local.x, local.y);
                }
              } catch (e) {}
              window.__ggqGripRotateActive = started;
              return started;
            }

            var ended = false;
            try {
              if (typeof window.ggqEndGripRotate === 'function') {
                ended = !!window.ggqEndGripRotate();
              }
            } catch (e) {}
            window.__ggqGripRotateActive = false;
            return ended;
          };

          function updateGripRotate(event) {
            if (!window.__ggqGripRotateActive) return;
            setPointer(event.clientX, event.clientY);
            var local = findViewCoordinates(window.__ggqLastPointer);
            try {
              if (typeof window.ggqUpdateGripRotate === 'function') {
                window.ggqUpdateGripRotate(local.x, local.y);
              }
            } catch (e) {}
          }
          document.addEventListener('pointermove', updateGripRotate, true);

          function sendEscape(target) {
'''
    if helper_anchor not in text:
        raise RuntimeError("exp13 JS findViewCoordinates closing anchor not found")
    text = text.replace(helper_anchor, helper_insert, 1)

    path.write_text(text, encoding="utf-8")
    print("[GGQ] exp13 right-grip WebView bridge + pointer motion routing installed")
else:
    print("[GGQ] exp13 grip rotate WebView bridge already present")

# ---------------------------------------------------------------------------
# Activity: reserve right Grip for rotation, keep left Grip for normal panel
# grabbing, and expose press/release commands to the controller shortcut system.
# ---------------------------------------------------------------------------
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
activity = activity_path.read_text(encoding="utf-8")

if "EXP13_RIGHT_GRIP_ROTATE" not in activity:
    import_anchor = "import com.meta.spatial.toolkit.Grabbable\n"
    if import_anchor not in activity:
        raise RuntimeError("exp13 activity Grabbable import anchor not found")
    activity = activity.replace(
        import_anchor,
        import_anchor + "import com.meta.spatial.toolkit.GrabbableSystem\n",
        1,
    )

    action_anchor = '''    internal fun onQuestAButtonPressed() {
        GeoGebraWebNavigation.toggleContextMenu()
    }
'''
    action_insert = action_anchor + '''
    // EXP13_RIGHT_GRIP_ROTATE: momentary rotate modifier; release restores the old tool natively.
    internal fun onQuestGripRotatePressed(): Boolean =
        GeoGebraWebNavigation.setGripRotate(true)

    internal fun onQuestGripRotateReleased() {
        GeoGebraWebNavigation.setGripRotate(false)
    }
'''
    if action_anchor not in activity:
        raise RuntimeError("exp13 activity A-button anchor not found")
    activity = activity.replace(action_anchor, action_insert, 1)

    vr_anchor = '''        if (vrReady) return
        vrReady = true

        val geoPanel = Entity(R.id.geogebra_panel)
'''
    vr_insert = '''        if (vrReady) return
        vrReady = true

        // Right Grip belongs to temporary 3D rotation. Keep left Grip available for moving
        // Grabbable panels so the existing spatial-panel positioning workflow is preserved.
        systemManager.findSystem<GrabbableSystem>().grabButtons = ButtonBits.ButtonSqueezeL

        val geoPanel = Entity(R.id.geogebra_panel)
'''
    if vr_anchor not in activity:
        raise RuntimeError("exp13 activity onVRReady anchor not found")
    activity = activity.replace(vr_anchor, vr_insert, 1)

    activity_path.write_text(activity, encoding="utf-8")
    print("[GGQ] exp13 activity reserves right Grip for rotation and left Grip for panel grab")
else:
    print("[GGQ] exp13 activity grip routing already present")
