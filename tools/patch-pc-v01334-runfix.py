#!/usr/bin/env python3
"""Build-only wrapper for GeoGebraForQuest PC v0.13.34.

The architectural v0.13.34 patch is kept intact except for brittle textual
matchers inherited from earlier generated patch chains. This wrapper normalizes
those matchers, executes the complete v0.13.34 patch, then fixes the inherited
cache-busting guard so build.ps1 validates the actual v0.13.34 runtime id.
"""

from pathlib import Path
import re


path = Path("tools/patch-pc-v01334.py")
source = path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Replace the original exact-string A-share call-site patch with a semantic
# regex matcher.
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

# ---------------------------------------------------------------------------
# Normalize the inherited v0.13.32 cache-busting validation. The old guard may
# contain escaped dots, so plain replacement of "0.13.32" is insufficient.
# ---------------------------------------------------------------------------
build_path = Path("pc/build.ps1")
build = build_path.read_text(encoding="utf-8")
for old, new in (
    (r"0\.13\.32-gpu-native-sbs", r"0\.13\.34-gpu-fbo-sbs"),
    (r"v0\.13\.32-gpu-native-sbs", r"v0\.13\.34-gpu-fbo-sbs"),
    ("0.13.32-gpu-native-sbs", "0.13.34-gpu-fbo-sbs"),
    ("v0.13.32-gpu-native-sbs", "v0.13.34-gpu-fbo-sbs"),
    (r"0\.13\.31-raw-legacy-bgra", r"0\.13\.34-gpu-fbo-sbs"),
    ("0.13.31-raw-legacy-bgra", "0.13.34-gpu-fbo-sbs"),
):
    build = build.replace(old, new)
build_path.write_text(build, encoding="utf-8")

main_path = Path("pc/MainFormV11.cs")
main = main_path.read_text(encoding="utf-8")
main = re.sub(
    r"(pc-stereo-layout\.js\?v=)[^\"']+",
    r"\g<1>0.13.34-gpu-fbo-sbs",
    main,
    count=1,
)
main_path.write_text(main, encoding="utf-8")

if "0.13.34-gpu-fbo-sbs" not in main:
    raise SystemExit("v0.13.34 wrapper: host cache-busting runtime id missing")
if (r"0\.13\.34-gpu-fbo-sbs" not in build and
        "0.13.34-gpu-fbo-sbs" not in build):
    raise SystemExit("v0.13.34 wrapper: build cache-busting guard missing")

print("v0.13.34 runfix: robust matchers + cache-busting guard normalized")
