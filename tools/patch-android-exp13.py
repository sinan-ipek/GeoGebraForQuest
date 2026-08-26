#!/usr/bin/env python3
"""Exp13 Android/WebView bridge for right-grip temporary 3D rotation."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp13.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

if "EXP13_GRIP_ROTATE_BRIDGE" in text:
    print("[GGQ] exp13 grip rotate WebView bridge already present")
    raise SystemExit(0)

# Native Android -> WebView command.
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

          // EXP13_GRIP_ROTATE_BRIDGE: use the same transparent 3D-hole coordinates as
          // normal Quest input, but route motion into GeoGebra's native temporary rotate mode.
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
