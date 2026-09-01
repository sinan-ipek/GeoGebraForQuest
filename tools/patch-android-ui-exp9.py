#!/usr/bin/env python3
"""Patch Android/WebView app sources for exp9 UI priority.

- Retain the last good stereo frame indefinitely; clear only on a real inactive
  3D-view signal, surface detach, or explicit disable.
- Make Quest A context-menu toggle inspect the actual DOM popup state instead
  of trusting a stale boolean, and grant the WebView a short stereo-free UI
  priority window before opening/closing the menu.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-ui-exp9.py <repo-root>")

root = Path(sys.argv[1]).resolve()

sink_path = root / "app/src/main/java/com/sinan/geogebraforquest/LiveStereoFrameSink.kt"
sink = sink_path.read_text(encoding="utf-8")
if "exp9 retains last live stereo frame" not in sink:
    sink = sink.replace("import java.util.concurrent.TimeUnit\n", "", 1)
    sink = sink.replace("    private const val STREAM_IDLE_TIMEOUT_MS = 350L\n", "", 1)
    sink, count = re.subn(
        r"\n    private val watchdog = Executors\.newSingleThreadScheduledExecutor \{ runnable ->\n"
        r"        Thread\(runnable, \"GGQ-StereoIdleWatchdog\"\)\.apply \{ isDaemon = true \}\n"
        r"    \}\n",
        "\n",
        sink,
        count=1,
    )
    if count != 1:
        raise RuntimeError("exp9 sink: watchdog executor anchor not found")

    old_submit = """        val generation = surfaceGeneration.get()\n        val serial = frameSerial.incrementAndGet()\n        scheduleIdleClear(generation, serial)\n        scheduleDrain()\n    }\n\n    private fun scheduleIdleClear(generation: Long, serial: Long) {\n        watchdog.schedule(\n            {\n                if (\n                    enabled &&\n                    surfaceGeneration.get() == generation &&\n                    frameSerial.get() == serial &&\n                    hasRenderedLiveFrame\n                ) {\n                    latestFrame.set(null)\n                    executor.execute {\n                        if (\n                            enabled &&\n                            surfaceGeneration.get() == generation &&\n                            frameSerial.get() == serial &&\n                            hasRenderedLiveFrame\n                        ) {\n                            clearSurfaceToTransparent()\n                            hasRenderedLiveFrame = false\n                            Log.i(TAG, \"exp6 stereo stream idle; panel cleared to transparent\")\n                        }\n                    }\n                }\n            },\n            STREAM_IDLE_TIMEOUT_MS,\n            TimeUnit.MILLISECONDS,\n        )\n    }\n"""
    new_submit = """        // exp9 retains last live stereo frame through slow render/encode gaps.\n        // Surface clearing is driven only by a real inactive-view signal, detach or disable.\n        frameSerial.incrementAndGet()\n        scheduleDrain()\n    }\n"""
    if old_submit not in sink:
        raise RuntimeError("exp9 sink: idle-clear block anchor not found")
    sink = sink.replace(old_submit, new_submit, 1)
    sink_path.write_text(sink, encoding="utf-8")
    print("[GGQ] exp9 retains last stereo frame; removed 350ms idle clear")
else:
    print("[GGQ] exp9 sink patch already present")

panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")
if "EXP9_ACTUAL_POPUP_STATE" not in panel:
    anchor = """          window.__ggqToggleContextMenu = function () {\n            var p = window.__ggqLastPointer || { x: 1, y: 1 };\n\n            if (window.__ggqContextMenuVisible) {\n"""
    replacement = """          function isVisibleContextPopup() {\n            // EXP9_ACTUAL_POPUP_STATE: never trust the old sticky boolean alone.\n            var selectors = [\n              '.gwt-PopupPanel', '.contextMenu', '.selectionMenu',\n              '.menuPanel', '.matMenu', '[role=\\\"menu\\\"]'\n            ];\n            for (var s = 0; s < selectors.length; s++) {\n              var nodes;\n              try { nodes = document.querySelectorAll(selectors[s]); } catch (e) { continue; }\n              for (var i = 0; i < nodes.length; i++) {\n                var node = nodes[i];\n                if (!node || !node.isConnected) continue;\n                var style;\n                try { style = getComputedStyle(node); } catch (e) { continue; }\n                if (!style || style.display === 'none' || style.visibility === 'hidden' ||\n                    parseFloat(style.opacity || '1') === 0) continue;\n                var r;\n                try { r = node.getBoundingClientRect(); } catch (e) { continue; }\n                if (r && r.width > 2 && r.height > 2) return true;\n              }\n            }\n            return false;\n          }\n\n          window.__ggqToggleContextMenu = function () {\n            var p = window.__ggqLastPointer || { x: 1, y: 1 };\n\n            // Stop requesting fresh stereo work while the menu action is queued/painted.\n            try {\n              if (typeof window.__ggqPrioritizeUi === 'function') {\n                window.__ggqPrioritizeUi(700);\n              }\n            } catch (e) {}\n\n            if (isVisibleContextPopup()) {\n"""
    if anchor not in panel:
        raise RuntimeError("exp9 panel: context toggle anchor not found")
    panel = panel.replace(anchor, replacement, 1)

    # Keep the legacy flag only as diagnostics/fallback state; actual DOM state governs toggling.
    panel_path.write_text(panel, encoding="utf-8")
    print("[GGQ] exp9 A-button uses actual popup state and 700ms UI priority")
else:
    print("[GGQ] exp9 panel patch already present")
