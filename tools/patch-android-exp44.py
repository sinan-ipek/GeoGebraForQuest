#!/usr/bin/env python3
"""Exp44: reliable Grip gate, controller-palette aspect, and direct L/R splash."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp44.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
sink_path = root / "app/src/main/java/com/sinan/geogebraforquest/LiveStereoFrameSink.kt"
panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
sink = sink_path.read_text(encoding="utf-8")

for required in ("EXP43_ISOLATED_GRIP_POINTER", "EXP43_GRAPH_CANVAS_GRIP_GATE",
                 "EXP42_SMOOTH_NATIVE_GRIP_MOVE"):
    if required not in panel:
        raise RuntimeError(f"exp44 panel baseline missing: {required}")

old_gate = r'''          // EXP43_GRAPH_CANVAS_GRIP_GATE: never start Grip on menus,
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

new_gate = r'''          // EXP44_CSS_POINTER_TRANSPARENT_CANVAS_GATE: use the CSS-space
          // pointer already maintained by real WebView hover events. The stereo 3D canvas
          // is intentionally opacity:0, so opacity must never disqualify it.
          function ggqGripBlockingUi(el) {
            if (!el || !el.closest) return false;
            return !!el.closest(
              'button,input,textarea,select,a,[role="button"],[role="menu"],' +
              '[role="menuitem"],[role="dialog"],[aria-modal="true"],' +
              '.dialog,.popupPanel,.menuView,.toolbarPanel,.openFileView'
            );
          }

          function ggqGripCssPoint(fallbackX, fallbackY) {
            var p = window.__ggqLastPointer;
            if (p && isFinite(Number(p.x)) && isFinite(Number(p.y)) &&
                Number(p.x) >= 0 && Number(p.y) >= 0 &&
                Number(p.x) <= window.innerWidth && Number(p.y) <= window.innerHeight) {
              return { x: Number(p.x), y: Number(p.y) };
            }
            var ratio = Math.max(1, Number(window.devicePixelRatio) || 1);
            return { x: Number(fallbackX) / ratio, y: Number(fallbackY) / ratio };
          }

          function ggqGripCanvasAt(p) {
            var elements = document.elementsFromPoint(p.x, p.y);
            var best = null;
            var bestArea = Number.POSITIVE_INFINITY;
            for (var i = 0; i < elements.length; i++) {
              var el = elements[i];
              if (ggqGripBlockingUi(el)) return null;
              if (!el || String(el.tagName).toLowerCase() !== 'canvas') continue;
              var rect = el.getBoundingClientRect();
              var style = window.getComputedStyle(el);
              if (rect.width < 100 || rect.height < 100 ||
                  style.display === 'none' || style.visibility === 'hidden') continue;
              var area = rect.width * rect.height;
              if (area < bestArea) { best = el; bestArea = area; }
            }
            return best;
          }

          window.__ggqBeginGripMoveModeAt = function (fallbackX, fallbackY) {
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

if old_gate not in panel:
    raise RuntimeError("exp44 Exp43 canvas gate anchor missing")
panel = panel.replace(old_gate, new_gate, 1)

old_scale = "        private val CONTROLLER_PALETTE_SCALE = Vector3(0.30f, 0.30f, 0.30f)\n"
new_scale = "        private const val CONTROLLER_PALETTE_MAX_SCALE = 0.30f\n"
if old_scale not in activity:
    raise RuntimeError("exp44 controller palette scale anchor missing")
activity = activity.replace(old_scale, new_scale, 1)

action_anchor = '''    internal fun onQuestBButtonPressed(rightControllerEntity: Entity) {
        val panel = stereoPanelEntity ?: return
'''
action_new = '''    // EXP44_CONTROLLER_PALETTE_ASPECT: preserve the current graph/stereo
    // rectangle instead of forcing the controller palette back to a square.
    private fun controllerPaletteScale(): Vector3 {
        val sourceX = embeddedStereoScale.x.takeIf { it.isFinite() && it > 0f } ?: 1f
        val sourceY = embeddedStereoScale.y.takeIf { it.isFinite() && it > 0f } ?: 1f
        val normalizer = maxOf(sourceX, sourceY).coerceAtLeast(0.0001f)
        return Vector3(
            CONTROLLER_PALETTE_MAX_SCALE * sourceX / normalizer,
            CONTROLLER_PALETTE_MAX_SCALE * sourceY / normalizer,
            1f,
        )
    }

    internal fun onQuestBButtonPressed(rightControllerEntity: Entity) {
        val panel = stereoPanelEntity ?: return
'''
if action_anchor not in activity:
    raise RuntimeError("exp44 B-button anchor missing")
activity = activity.replace(action_anchor, action_new, 1)

old_apply = "            panel.setComponent(Scale(CONTROLLER_PALETTE_SCALE))\n"
new_apply = "            panel.setComponent(Scale(controllerPaletteScale()))\n"
if old_apply not in activity:
    raise RuntimeError("exp44 B-button scale application missing")
activity = activity.replace(old_apply, new_apply, 1)

old_splash = '''        val leftBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_right) ?: return
        val rightBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_left)
'''
new_splash = '''        // EXP44_DIRECT_SPLASH_EYE_MAPPING: L1 -> left eye, R1 -> right eye.
        val leftBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_left) ?: return
        val rightBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_right)
'''
if old_splash not in sink:
    raise RuntimeError("exp44 reversed splash anchor missing")
sink = sink.replace(old_splash, new_splash, 1)

for required in ("EXP44_CSS_POINTER_TRANSPARENT_CANVAS_GATE", "window.__ggqLastPointer",
                 "style.display === 'none'", "EXP44_CONTROLLER_PALETTE_ASPECT",
                 "controllerPaletteScale()", "EXP44_DIRECT_SPLASH_EYE_MAPPING"):
    if required not in panel + activity + sink:
        raise RuntimeError(f"exp44 requirement missing: {required}")
if "Number(style.opacity || 1) > 0" in panel:
    raise RuntimeError("exp44 still rejects the transparent stereo canvas")
if "Scale(CONTROLLER_PALETTE_SCALE)" in activity:
    raise RuntimeError("exp44 still forces a square controller palette")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
sink_path.write_text(sink, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += ("right_grip=exp44 CSS-space pointer; transparent stereo canvas accepted\n"
              "controller_palette=exp44 current stereo aspect preserved\n"
              "startup_splash=exp44 direct L1-left R1-right mapping\n")
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp44 Grip gate, controller aspect, and splash-eye mapping installed")
