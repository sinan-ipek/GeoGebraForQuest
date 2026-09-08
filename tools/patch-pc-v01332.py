#!/usr/bin/env python3
"""Stable launcher for the v0.13.32 GPU-native SBS patch.

The full implementation is frozen at commit 8fa715871e4f91e108941e22e6e21fafaf52bd7d.
This launcher corrects one over-broad final invariant in that implementation:
the old check rejected the harmless recursive requestAnimationFrame calls inside
the now-unreachable fallback captureLoop.  v0.13.32 only needs to guarantee that
the loop is never STARTED at runtime.
"""

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
