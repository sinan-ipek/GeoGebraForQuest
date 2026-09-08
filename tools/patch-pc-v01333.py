#!/usr/bin/env python3
"""Build-safe launcher for the v0.13.33 host/XR patch.

The architectural implementation is frozen at commit
9d273acca509f9370f8b4f98d0e3b72a19065ea5. This launcher changes only one
brittle multi-line source matcher in the A-share ownership fix. Runtime behavior
is unchanged: XR sharing is sourced from the client-owned `target` texture,
never from CefSharp's temporary accelerated-paint pool texture.
"""

from urllib.request import urlopen

URL = (
    "https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/"
    "9d273acca509f9370f8b4f98d0e3b72a19065ea5/tools/patch-pc-v01333.py"
)

source = urlopen(URL, timeout=30).read().decode("utf-8")

old = '''require(graphics, old, "v0.13.33 A-share source marker missing")
graphics = graphics.replace(old, new, 1)'''

new = '''if old in graphics:
    graphics = graphics.replace(old, new, 1)
else:
    # Generated v0.13.32 files can differ in surrounding whitespace/comments.
    # Match only the two semantic call sites that must change.
    call_old = "TryQueueGpuPublishLocked(cefTexture)"
    call_new = "TryQueueGpuPublishLocked(target)"
    desc_old = "CompleteGpuPublishLocked(cefTexture.Description)"
    desc_new = "CompleteGpuPublishLocked(target.Description)"
    require(graphics, call_old, "v0.13.33 A-share call marker missing")
    require(graphics, desc_old, "v0.13.33 A-share description marker missing")
    graphics = graphics.replace(call_old, call_new, 1)
    graphics = graphics.replace(desc_old, desc_new, 1)'''

if old not in source:
    raise SystemExit("v0.13.33 frozen A-share matcher marker missing")

source = source.replace(old, new, 1)
exec(compile(source, "patch-pc-v01333-frozen.py", "exec"), {"__name__": "__main__"})
print("GeoGebraForQuest PC v0.13.33 build-safe A-share matcher applied")
