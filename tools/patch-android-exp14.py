#!/usr/bin/env python3
"""Exp14 runtime hotfix: remove unsafe startup access to GrabbableSystem.

Exp13 called systemManager.findSystem<GrabbableSystem>() inside onVRReady(), before
creating the GeoGebra panel entity. On Quest runtime this can fail if that toolkit
system is not available at that lifecycle point, which aborts onVRReady() and leaves
no panel visible at all.

Keep the right-Grip WebView/GeoGebra bridge, but restore exp12's safe panel startup
path. Panel-grab button routing will be handled separately after runtime validation.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp14.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
text = path.read_text(encoding="utf-8")

old_import = "import com.meta.spatial.toolkit.GrabbableSystem\n"
text = text.replace(old_import, "", 1)

unsafe = '''        // Right Grip belongs to temporary 3D rotation. Keep left Grip available for moving
        // Grabbable panels so the existing spatial-panel positioning workflow is preserved.
        systemManager.findSystem<GrabbableSystem>().grabButtons = ButtonBits.ButtonSqueezeL

'''
if unsafe not in text:
    if "findSystem<GrabbableSystem>()" in text:
        raise RuntimeError("exp14 found unexpected GrabbableSystem startup code")
else:
    text = text.replace(unsafe, "", 1)

# Marker beside the existing Grip bridge methods; no startup system lookup remains.
marker_anchor = '''    // EXP13_RIGHT_GRIP_ROTATE: momentary rotate modifier; release restores the old tool natively.
'''
marker = '''    // EXP14_RUNTIME_HOTFIX: Grip bridge is retained, but onVRReady no longer touches
    // GrabbableSystem before the GeoGebra panel entities are created.
'''
if "EXP14_RUNTIME_HOTFIX" not in text:
    if marker_anchor not in text:
        raise RuntimeError("exp14 Grip bridge marker anchor not found")
    text = text.replace(marker_anchor, marker + marker_anchor, 1)

if "findSystem<GrabbableSystem>()" in text or "import com.meta.spatial.toolkit.GrabbableSystem" in text:
    raise RuntimeError("exp14 unsafe GrabbableSystem startup access still present")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp14 removed unsafe GrabbableSystem lookup from onVRReady; panel startup restored")
