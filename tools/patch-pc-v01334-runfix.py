#!/usr/bin/env python3
"""Build-only wrapper for GeoGebraForQuest PC v0.13.34.

The v0.13.34 architectural patch is correct in intent, but its A-share edit
assumed one exact spelling of the pre-existing call site.  The v0.13.31 base
can already use the client-owned target texture, so that exact marker is not
stable.  This wrapper makes only the textual matching tolerant, then executes
the complete v0.13.34 patch unchanged.
"""

from pathlib import Path


path = Path("tools/patch-pc-v01334.py")
source = path.read_text(encoding="utf-8")

old_call_patch = r'''# Publish the just-copied client-owned target/SRV, not CEF's pool texture.
old_call = '''                    if (TryQueueGpuPublishLocked(cefTexture))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(cefTexture.Description);'''
new_call = '''                    if (TryQueueGpuPublishLocked(target, _pcSrvs[next]))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(_xrSharedTexture!.Description);'''
require(graphics, old_call, "v0.13.34 A-share call marker missing")
graphics = graphics.replace(old_call, new_call, 1)
'''

new_call_patch = r'''# Publish the client-owned PC copy/SRV, not CEF's temporary pool texture.
# v0.13.31-derived bases may spell the existing one-argument call with either
# cefTexture or target, so match the call semantically rather than byte-for-byte.
call_pattern = re.compile(
    r"(?m)^(?P<i>[ \\t]*)if \\(TryQueueGpuPublishLocked\\((?:cefTexture|target)\\)\\)\\s*\\{\\s*"
    r"_device\\.ImmediateContext\\.Flush\\(\\);\\s*"
    r"CompleteGpuPublishLocked\\((?:cefTexture|target)\\.Description\\);"
)
call_match = call_pattern.search(graphics)
if not call_match:
    raise SystemExit("v0.13.34 A-share call shape missing")
indent = call_match.group("i")
new_call = (
    indent + "if (TryQueueGpuPublishLocked(target, _pcSrvs[next]))\\n" +
    indent + "{\\n" +
    indent + "    _device.ImmediateContext.Flush();\\n" +
    indent + "    CompleteGpuPublishLocked(_xrSharedTexture!.Description);"
)
graphics = graphics[:call_match.start()] + new_call + graphics[call_match.end():]
'''

if old_call_patch not in source:
    raise SystemExit("v0.13.34 wrapper: brittle A-share patch block not found")
source = source.replace(old_call_patch, new_call_patch, 1)

old_bounds = '''start = graphics.find("    private bool TryQueueGpuPublishLocked(Texture2D cefTexture)\\n")
end = graphics.find("\\n    private void CompleteGpuPublishLocked", start)
if start < 0 or end < 0:
    raise SystemExit("v0.13.34 TryQueue method bounds missing")
'''

new_bounds = '''method_match = re.search(
    r"(?m)^    private bool TryQueueGpuPublishLocked\\([^\\n]+\\)\\n",
    graphics,
)
start = method_match.start() if method_match else -1
end = graphics.find("\\n    private void CompleteGpuPublishLocked", start)
if start < 0 or end < 0:
    raise SystemExit("v0.13.34 TryQueue method bounds missing")
'''

if old_bounds not in source:
    raise SystemExit("v0.13.34 wrapper: brittle TryQueue bounds block not found")
source = source.replace(old_bounds, new_bounds, 1)

exec(compile(source, "patch-pc-v01334-runfixed.py", "exec"), {"__name__": "__main__"})
