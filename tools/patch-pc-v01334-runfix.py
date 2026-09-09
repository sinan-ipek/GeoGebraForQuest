#!/usr/bin/env python3
"""Build-only wrapper for GeoGebraForQuest PC v0.13.34.

The architectural v0.13.34 patch is kept intact except for two brittle textual
matchers inherited from earlier generated patch chains:

1. The A-share call site may already use either cefTexture or the client-owned
   target texture.
2. The TryQueueGpuPublishLocked method signature may no longer be the exact
   single-line spelling expected by the original patch.

This wrapper rewrites only those matchers before executing the complete
v0.13.34 patch.
"""

from pathlib import Path


path = Path("tools/patch-pc-v01334.py")
source = path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Replace the original exact-string A-share call-site patch with a semantic
# regex matcher. Avoid embedding the original triple-quoted Python literals in
# this wrapper, because doing so makes the wrapper itself syntactically fragile.
# ---------------------------------------------------------------------------
call_start = source.find(
    "# Publish the just-copied client-owned target/SRV, not CEF's pool texture."
)
call_end = source.find(
    '\nstart = graphics.find("    private bool TryQueueGpuPublishLocked',
    call_start,
)
if call_start < 0 or call_end < 0:
    raise SystemExit("v0.13.34 wrapper: A-share patch section not found")

new_call_patch = """# Publish the client-owned PC copy/SRV, not CEF's temporary pool texture.
# v0.13.31-derived bases may spell the existing one-argument call with either
# cefTexture or target, so match the call semantically rather than byte-for-byte.
call_pattern = re.compile(
    r\"(?ms)^(?P<i>[ \\t]*)if \\(TryQueueGpuPublishLocked\\((?:cefTexture|target)\\)\\)\\s*\\{\\s*\"
    r\"_device\\.ImmediateContext\\.Flush\\(\\);\\s*\"
    r\"CompleteGpuPublishLocked\\((?:cefTexture|target)\\.Description\\);\"
)
call_match = call_pattern.search(graphics)
if not call_match:
    raise SystemExit(\"v0.13.34 A-share call shape missing\")
indent = call_match.group(\"i\")
replacement_call = (
    indent + \"if (TryQueueGpuPublishLocked(target, _pcSrvs[next]))\\n\" +
    indent + \"{\\n\" +
    indent + \"    _device.ImmediateContext.Flush();\\n\" +
    indent + \"    CompleteGpuPublishLocked(_xrSharedTexture!.Description);\"
)
graphics = graphics[:call_match.start()] + replacement_call + graphics[call_match.end():]
"""

source = source[:call_start] + new_call_patch + source[call_end:]

# ---------------------------------------------------------------------------
# Replace the exact TryQueueGpuPublishLocked signature lookup with a semantic
# method-boundary search.
# ---------------------------------------------------------------------------
bounds_start = source.find(
    'start = graphics.find("    private bool TryQueueGpuPublishLocked'
)
bounds_end = source.find("\n\nnew_method = r'''", bounds_start)
if bounds_start < 0 or bounds_end < 0:
    raise SystemExit("v0.13.34 wrapper: TryQueue bounds section not found")

new_bounds_patch = """method_match = re.search(
    r\"(?m)^    private bool TryQueueGpuPublishLocked\\([^\\n]+\\)\\s*$\",
    graphics,
)
start = method_match.start() if method_match else -1
end = graphics.find(\"\\n    private void CompleteGpuPublishLocked\", start)
if start < 0 or end < 0:
    raise SystemExit(\"v0.13.34 TryQueue method bounds missing\")
"""

source = source[:bounds_start] + new_bounds_patch + source[bounds_end:]

exec(
    compile(source, "patch-pc-v01334-runfixed.py", "exec"),
    {"__name__": "__main__"},
)
