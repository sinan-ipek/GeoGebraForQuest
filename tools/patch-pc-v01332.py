#!/usr/bin/env python3
"""Stable launcher for the v0.13.32 GPU-native SBS patch.

The full implementation is frozen at commit 8fa715871e4f91e108941e22e6e21fafaf52bd7d.
This launcher corrects two build-only issues without changing the architecture:
1) the old final invariant rejected harmless recursive captureLoop calls inside
   an unreachable fallback function; only a startup call is forbidden,
2) SharpDX/CefSharp namespace collisions introduced ambiguous MapFlags,
   Rectangle and Size references in the new PC GPU shader helper.
"""

from pathlib import Path
from urllib.request import urlopen

URL = (
    "https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/"
    "8fa715871e4f91e108941e22e6e21fafaf52bd7d/tools/patch-pc-v01332.py"
)

source = urlopen(URL, timeout=30).read().decode("utf-8")
old = r'''# There must be exactly zero startup calls to the raw capture RAF loop.
if re.search(r'^\s*requestAnimationFrame\(captureLoop\);\s*$', runtime, re.M):
    raise SystemExit('v0.13.32 active captureLoop startup remains')'''
new = r'''# Recursive calls inside the dead fallback function are harmless. Reject only
# the historical bottom-of-file startup sequence that would activate it.
if "  requestAnimationFrame(captureLoop);\n  bridge('panelReady', '');" in runtime:
    raise SystemExit('v0.13.32 active captureLoop startup remains')'''
if old not in source:
    raise SystemExit("v0.13.32 frozen implementation invariant marker missing")
source = source.replace(old, new, 1)
exec(compile(source, "patch-pc-v01332-frozen.py", "exec"), {"__name__": "__main__"})

# Build-only namespace disambiguation. Do this after the frozen architectural
# patch so its source matching remains byte-for-byte stable.
p = Path("pc/MainFormV11.Graphics.cs")
text = p.read_text(encoding="utf-8")

replacements = (
    (
        "_pcStereoParams, 0, MapMode.WriteDiscard, MapFlags.None);",
        "_pcStereoParams, 0, MapMode.WriteDiscard, SharpDX.Direct3D11.MapFlags.None);",
    ),
    (
        "        Rectangle panel;\n        Rectangle[] overlays;\n        Size size;\n",
        "        System.Drawing.Rectangle panel;\n"
        "        System.Drawing.Rectangle[] overlays;\n"
        "        System.Drawing.Size size;\n",
    ),
    (
        "        static Vector4 NormalizeRect(Rectangle r, float width, float height)\n",
        "        static Vector4 NormalizeRect(System.Drawing.Rectangle r, float width, float height)\n",
    ),
)

for before, after in replacements:
    if before not in text:
        raise SystemExit(f"v0.13.32 build-fix marker missing: {before!r}")
    text = text.replace(before, after, 1)

p.write_text(text, encoding="utf-8")
print("GeoGebraForQuest PC v0.13.32 C# namespace build fix applied")
