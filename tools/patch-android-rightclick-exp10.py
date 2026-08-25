#!/usr/bin/env python3
"""Exp10 WebView context-menu fixes without UI-priority scheduling.

Applied after patch-android-ui-exp9.py so we keep its useful real-popup-state and
last-stereo-frame retention, but remove its stereo-free UI priority request.
Also make the intentionally transparent stereo-hole canvas eligible for pointer
coordinate mapping and avoid synthetic background right-click when the native
GeoGebra hook exists but correctly reports no object.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-rightclick-exp10.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

if "EXP10_STEREO_HOLE_CONTEXT_TARGET" in text:
    print("[GGQ] exp10 WebView right-click patch already present")
    raise SystemExit(0)

old_scan = """                var style = window.getComputedStyle(candidate);\n                if (style.display === 'none' || style.visibility === 'hidden' ||\n                    parseFloat(style.opacity || '1') === 0) continue;\n                var r = candidate.getBoundingClientRect();\n                if (r.width < 40 || r.height < 40) continue;\n                if (p.x < r.left || p.x > r.right || p.y < r.top || p.y > r.bottom) continue;\n                var area = r.width * r.height;\n                if (area < bestArea) {\n                  bestArea = area;\n                  canvas = candidate;\n                }\n"""
new_scan = """                var style = window.getComputedStyle(candidate);\n                var isStereoHole = !!(candidate.dataset &&\n                    candidate.dataset.ggqStereoHole === 'true');\n                // EXP10_STEREO_HOLE_CONTEXT_TARGET: the 3D canvas is intentionally opacity:0\n                // for A/B compositing, but it remains the authoritative input/hit-test surface.\n                if (style.display === 'none' || style.visibility === 'hidden' ||\n                    (parseFloat(style.opacity || '1') === 0 && !isStereoHole)) continue;\n                var r = candidate.getBoundingClientRect();\n                if (r.width < 40 || r.height < 40) continue;\n                if (p.x < r.left || p.x > r.right || p.y < r.top || p.y > r.bottom) continue;\n                if (isStereoHole) {\n                  canvas = candidate;\n                  break;\n                }\n                var area = r.width * r.height;\n                if (area < bestArea) {\n                  bestArea = area;\n                  canvas = candidate;\n                }\n"""
if old_scan not in text:
    raise RuntimeError("exp10 panel: findViewCoordinates canvas scan anchor not found")
text = text.replace(old_scan, new_scan, 1)

priority = """            // Stop requesting fresh stereo work while the menu action is queued/painted.\n            try {\n              if (typeof window.__ggqPrioritizeUi === 'function') {\n                window.__ggqPrioritizeUi(700);\n              }\n            } catch (e) {}\n\n"""
if priority not in text:
    raise RuntimeError("exp10 panel: exp9 UI-priority block not found")
text = text.replace(priority, "", 1)

old_open = """            var local = findViewCoordinates(p);\n            var opened = false;\n            try {\n              if (typeof window.ggqOpenContextMenu === 'function') {\n                opened = !!window.ggqOpenContextMenu(local.x, local.y);\n              }\n            } catch (e) {}\n\n            if (!opened) {\n              opened = syntheticRightClick(p);\n            }\n\n            window.__ggqContextMenuVisible = opened;\n"""
new_open = """            var local = findViewCoordinates(p);\n            var opened = false;\n            var nativeAvailable = typeof window.ggqOpenContextMenu === 'function';\n            try {\n              if (nativeAvailable) {\n                opened = !!window.ggqOpenContextMenu(local.x, local.y);\n              }\n            } catch (e) {}\n\n            // If the native hook exists and reports no object, that is a real no-hit.\n            // Synthetic right-click is only a compatibility fallback when the hook is absent.\n            if (!opened && !nativeAvailable) {\n              opened = syntheticRightClick(p);\n            }\n\n            window.__ggqContextMenuVisible = opened;\n"""
if old_open not in text:
    raise RuntimeError("exp10 panel: native context-open block anchor not found")
text = text.replace(old_open, new_open, 1)

path.write_text(text, encoding="utf-8")
print("[GGQ] exp10 stereo-hole pointer routing + native-only A context menu applied")
