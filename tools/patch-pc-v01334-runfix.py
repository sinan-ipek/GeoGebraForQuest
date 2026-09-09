#!/usr/bin/env python3
"""Build-only wrapper for GeoGebraForQuest PC v0.13.34.

The architectural v0.13.34 patch is kept intact except for brittle textual
matchers and stale build guards inherited from earlier generated patch chains.
This wrapper normalizes those matchers, executes the complete v0.13.34 patch,
then updates the generated host/build files for the actual v0.13.34 GPU/FBO
architecture.
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
# v0.13.34 changes TryQueueGpuPublishLocked to accept both the texture and an
# SRV. One inherited popup/composite helper still calls the old one-argument
# form after the patch chain. Update that exact generated call as well.
# ---------------------------------------------------------------------------
graphics_path = Path("pc/MainFormV11.Graphics.cs")
graphics = graphics_path.read_text(encoding="utf-8")
old_composite_call = "if (TryQueueGpuPublishLocked(target))"
new_composite_call = (
    "if (TryQueueGpuPublishLocked(target, _pcSrvs[_currentPcTexture]))"
)
composite_count = graphics.count(old_composite_call)
if composite_count > 1:
    raise SystemExit(
        f"v0.13.34 wrapper: unexpected legacy GPU publish call count: {composite_count}"
    )
if composite_count == 1:
    graphics = graphics.replace(old_composite_call, new_composite_call, 1)
graphics_path.write_text(graphics, encoding="utf-8")

# No one-argument target publish call may remain after the v0.13.34 signature
# change. Failing here is much faster and clearer than waiting for dotnet build.
if "TryQueueGpuPublishLocked(target)" in graphics:
    raise SystemExit("v0.13.34 wrapper: legacy one-argument GPU publish call remains")

# ---------------------------------------------------------------------------
# Normalize inherited cache-busting validation. Older guards can contain
# escaped dots, so plain replacement of only the visible version is not enough.
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

# ---------------------------------------------------------------------------
# v0.13's original "A GPU-direct" guard validates the old direct CopyResource
# publication path. v0.13.34 intentionally replaces that with a shader blit
# from the client-owned PC texture/SRV into a BGRA8 keyed-mutex XR render target.
# Replace only that obsolete guard, and validate the new path explicitly.
# ---------------------------------------------------------------------------
gpu_direct_guard = re.compile(
    r'(?ms)^if \([^\{]*\)\s*\{\s*'
    r'throw "v0\.13 doğrulaması başarısız: A GPU-direct yolu eksik\."\s*\}'
)
if not gpu_direct_guard.search(build):
    raise SystemExit("v0.13.34 wrapper: stale A GPU-direct build guard not found")

new_gpu_guard = '''if ($graphicsText -notmatch "TryQueueGpuPublishLocked\\(target, _pcSrvs\\[next\\]\\)" -or
    $graphicsText -notmatch "PSShare" -or
    $graphicsText -notmatch "BindFlags\\.ShaderResource \\| BindFlags\\.RenderTarget" -or
    $graphicsText -notmatch "SetRenderTargets\\(_xrSharedRtv\\)") {
    throw "v0.13.34 doğrulaması başarısız: shader tabanlı A GPU-share yolu eksik."
}'''
build = gpu_direct_guard.sub(new_gpu_guard, build, count=1)
build_path.write_text(build, encoding="utf-8")

# Keep the host-side cache-busting runtime id synchronized with this build.
main_path = Path("pc/MainFormV11.cs")
main = main_path.read_text(encoding="utf-8")
main = re.sub(
    r"(pc-stereo-layout\.js\?v=)[^\"']+",
    r"\g<1>0.13.34-gpu-fbo-sbs",
    main,
    count=1,
)
main_path.write_text(main, encoding="utf-8")

# Final wrapper-level invariants.
if "0.13.34-gpu-fbo-sbs" not in main:
    raise SystemExit("v0.13.34 wrapper: host cache-busting runtime id missing")
if (r"0\.13\.34-gpu-fbo-sbs" not in build and
        "0.13.34-gpu-fbo-sbs" not in build):
    raise SystemExit("v0.13.34 wrapper: build cache-busting guard missing")
for needle in (
    "TryQueueGpuPublishLocked\\(target, _pcSrvs\\[next\\]\\)",
    "PSShare",
    "SetRenderTargets\\(_xrSharedRtv\\)",
):
    if needle not in build:
        raise SystemExit(f"v0.13.34 wrapper: GPU-share validation missing: {needle}")

print(
    "v0.13.34 runfix: robust matchers + cache-busting + GPU-direct guard + "
    "remaining publish call normalized"
)
