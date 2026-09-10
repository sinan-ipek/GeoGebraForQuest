#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.40 — prevent XR startup black screen.

v0.13.39 intentionally stopped publishing ordinary CEF GPU paints to XR because
XR now expects a 2W x H full-SBS texture. That creates a hard startup failure:
until the first real stereo pair completes, XR has no valid base texture and
submits no application projection layer, so Quest shows only black.

This patch keeps the v0.13.39 GPU full-frame stereo architecture intact, but
adds a safe bootstrap/fallback path:

    ordinary CEF A frame -> copy to LEFT and RIGHT GPU eye textures
                         -> compose [A | A] as native 2W x H shared texture
                         -> publish to XR

The duplicated fallback is used only before the first successful real stereo
pair. As soon as v0.13.39 publishes [A_L | A_R], _gpuStereoPairAvailable becomes
true and ordinary paints stop overwriting stereo output.
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Host accelerated-paint path: publish [A|A] until first real stereo pair.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.Graphics.cs")
graphics = p.read_text(encoding="utf-8")

old = '''                // Ordinary browser paint. This is the PC-visible A/right-eye
                // baseline only; it is NOT sent to XR as a stereo frame.
                EnsurePcTextureLocked(cefTexture.Description);
                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;

                _device.ImmediateContext.CopyResource(cefTexture, target);
                _currentPcTexture = next;
                var frame = Interlocked.Increment(ref _gpuFrameNumber);
                normalPaint = true;

                if ((frame % 120) == 0)
                {
                    BeginInvokeSafe(UpdateWindowTitle);
                }
'''

new = '''                // Ordinary browser paint remains the PC-visible A/right-eye
                // baseline. Before the first successful real stereo pair, XR
                // would otherwise have no valid 2W texture at all and would
                // submit no projection layer (Quest = completely black).
                EnsurePcTextureLocked(cefTexture.Description);
                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;

                _device.ImmediateContext.CopyResource(cefTexture, target);
                _currentPcTexture = next;
                var frame = Interlocked.Increment(ref _gpuFrameNumber);
                normalPaint = true;

                // v0.13.40 bootstrap/fallback: while no proven A_L|A_R pair has
                // reached XR yet, duplicate the ordinary A texture on the GPU
                // and publish a valid [A|A] 2W frame. This never changes the
                // GeoGebra eye geometry and stops automatically after the first
                // successful real stereo publication.
                if (!_gpuStereoPairAvailable)
                {
                    EnsureGpuStereoCaptureTexturesLocked(cefTexture.Description);
                    if (_gpuStereoLeftTexture is not null &&
                        _gpuStereoRightTexture is not null)
                    {
                        _device.ImmediateContext.CopyResource(
                            cefTexture, _gpuStereoLeftTexture);
                        _device.ImmediateContext.CopyResource(
                            cefTexture, _gpuStereoRightTexture);

                        var fallbackComposeMs = 0.0;
                        var fallbackPublishMs = 0.0;
                        var fallbackPublished = ComposeAndPublishGpuFullSbsLocked(
                            cefTexture.Description,
                            out fallbackComposeMs,
                            out fallbackPublishMs);

                        if (fallbackPublished)
                        {
                            _gpuShareStatus = "A|A GPU fallback";
                        }

                        _gpuStereoTelemetry.Event(
                            fallbackPublished
                                ? "bootstrap-aa-published"
                                : "bootstrap-aa-publish-missed",
                            _gpuStereoCaptureSerial,
                            -1,
                            _gpuStereoCaptureState.ToString(),
                            cefTexture.Description.Width,
                            cefTexture.Description.Height,
                            composeMs: fallbackComposeMs,
                            publishMs: fallbackPublishMs,
                            detail: "v0.13.40 duplicated ordinary CEF frame");
                    }
                }

                if ((frame % 120) == 0)
                {
                    BeginInvokeSafe(UpdateWindowTitle);
                }
'''

require(graphics, old, "v0.13.40 ordinary accelerated-paint block missing")
graphics = graphics.replace(old, new, 1)
p.write_text(graphics, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Version labels. GeoGebra source renderer itself remains v0.13.39; only the
#    PC host/XR bootstrap behavior is v0.13.40.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
main = main.replace("GeoGebraForQuest PC v0.13.39", "GeoGebraForQuest PC v0.13.40")
main = main.replace("0.13.39-gpu-fullframe-sbs", "0.13.40-blackframe-fallback")
p.write_text(main, encoding="utf-8")

p = Path("pc-xr/main-v11.cpp")
xr = p.read_text(encoding="utf-8")
xr = xr.replace(
    "GeoGebraForQuest PC v0.13.39 initialized: GPU [A_L|A_R] full-window SBS -> OpenXR; no CPU framebuffer path",
    "GeoGebraForQuest PC v0.13.40 initialized: GPU [A|A] bootstrap then [A_L|A_R] full-window SBS -> OpenXR",
)
p.write_text(xr, encoding="utf-8")

p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.40</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.40.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.40.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

p = Path("pc/build.ps1")
build = p.read_text(encoding="utf-8")
build = build.replace(
    "GeoGebraForQuest-PC-v0.13.39-gpu-fullframe-sbs-win-x64",
    "GeoGebraForQuest-PC-v0.13.40-blackframe-fallback-win-x64",
)
build = build.replace("v0.13.39", "v0.13.40")
p.write_text(build, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Hard invariants: build must prove the fallback exists and old full-SBS
#    geometry is still present.
# ---------------------------------------------------------------------------
graphics = Path("pc/MainFormV11.Graphics.cs").read_text(encoding="utf-8")
host = Path("pc/MainFormV139.GpuStereo.cs").read_text(encoding="utf-8")
xr = Path("pc-xr/main-v11.cpp").read_text(encoding="utf-8")
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")

checks = {
    "graphics bootstrap": "bootstrap-aa-published" in graphics,
    "graphics pair guard": "if (!_gpuStereoPairAvailable)" in graphics,
    "real stereo compositor": "ComposeAndPublishGpuFullSbsLocked" in host,
    "XR half-width geometry": "baseTexture_.Width() / 2" in xr,
    "physical-eye half sampler": "rightEye ? 0.5f : 0.0f" in render,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("v0.13.40 invariant failure: " + ", ".join(failed))

print("v0.13.40 patch applied: XR [A|A] bootstrap fallback + unchanged real full-SBS stereo")
