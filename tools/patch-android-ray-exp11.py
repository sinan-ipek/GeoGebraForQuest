#!/usr/bin/env python3
"""Exp11 Android/WebView bridge for stereo depth-pointer presentation.

The transparent A panel remains the real input/raycast surface. JS reports whether
that pointer lies inside the live 3D hole. Android then hides only Meta's flat panel
laser visual; GeoGebra's own stereo cursor/highlight remains at the actual picked
3D depth. Reset the state whenever 3D goes inactive or the activity starts.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-ray-exp11.py <repo-root>")

root = Path(sys.argv[1]).resolve()

panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")
if "EXP11_DEPTH_POINTER_BRIDGE" not in panel:
    old_inactive = '''    @JavascriptInterface
    fun stereoInactive() {
        if (spatialMode) {
            LiveStereoFrameSink.clearForInactiveView()
        }
    }

    @JavascriptInterface
    fun getStereoDebugStatus(): String = StereoDebugState.toJson()
'''
    new_inactive = '''    @JavascriptInterface
    fun stereoInactive() {
        if (spatialMode) {
            DepthPointerState.setActive(false)
            LiveStereoFrameSink.clearForInactiveView()
        }
    }

    // EXP11_DEPTH_POINTER_BRIDGE: visual-only laser suppression over the stereo 3D hole.
    @JavascriptInterface
    fun setDepthPointerActive(value: String) {
        if (spatialMode) {
            DepthPointerState.setActive(
                value == "1" || value.equals("true", ignoreCase = true),
            )
        }
    }

    @JavascriptInterface
    fun getStereoDebugStatus(): String = StereoDebugState.toJson()
'''
    if old_inactive not in panel:
        raise RuntimeError("exp11 panel: stereoInactive bridge anchor not found")
    panel = panel.replace(old_inactive, new_inactive, 1)
    panel_path.write_text(panel, encoding="utf-8")
    print("[GGQ] exp11 WebView depth-pointer bridge installed")
else:
    print("[GGQ] exp11 WebView depth-pointer bridge already present")

activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
activity = activity_path.read_text(encoding="utf-8")
if "DepthPointerState.reset()" not in activity:
    old_create = '''        super.onCreate(savedInstanceState)
        StereoDebugState.reset()
        SpatialBridgeBus.clear()
'''
    new_create = '''        super.onCreate(savedInstanceState)
        StereoDebugState.reset()
        DepthPointerState.reset()
        SpatialBridgeBus.clear()
'''
    if old_create not in activity:
        raise RuntimeError("exp11 activity: onCreate reset anchor not found")
    activity = activity.replace(old_create, new_create, 1)
    activity_path.write_text(activity, encoding="utf-8")
    print("[GGQ] exp11 depth-pointer state resets on activity creation")
else:
    print("[GGQ] exp11 activity reset already present")
