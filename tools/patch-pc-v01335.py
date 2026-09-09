#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.35 — correct L/R recovery release.

This release deliberately returns the stereo source/transport to the
runtime-proven v0.13.31 path:

    exact GeoGebra LEFT_EYE + RIGHT_EYE canvases
      -> raw RGBA ArrayBuffer
      -> legacy BGRA SBS MMF (pixelFormat=1)
      -> proven A_L/A_R single-panel compositor

It does NOT use the v0.13.32-v0.13.34 embedded-SBS-in-CEF path, does not split
a compressed 3D CSS rectangle in XR, and does not use the v0.13.34 shader-blit
A-share path.

The only presentation change here is defensive: the PC swapchain viewport is
reset on every presented frame. That makes the desktop presentation immune to
any D3D operation that changes the immediate-context viewport and prevents the
large right/bottom black areas seen in v0.13.34.
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) PC presentation: always restore a full-window viewport before drawing A.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.Graphics.cs")
s = p.read_text(encoding="utf-8")

marker = """                    var context = _device.ImmediateContext;
                    context.OutputMerger.SetRenderTargets(_renderTarget);
                    context.ClearRenderTargetView(_renderTarget, new Color4(0, 0, 0, 1));
"""
require(s, marker, "v0.13.35 RenderLoop render-target marker missing")
replacement = """                    var context = _device.ImmediateContext;
                    context.OutputMerger.SetRenderTargets(_renderTarget);
                    // v0.13.35: D3D immediate-context state is global. Never rely
                    // on a viewport left behind by A-share/XR publication or any
                    // other GPU operation. Reassert the desktop viewport every frame.
                    context.Rasterizer.SetViewport(new Viewport(
                        0,
                        0,
                        Math.Max(2, ClientSize.Width),
                        Math.Max(2, ClientSize.Height),
                        0,
                        1));
                    context.ClearRenderTargetView(_renderTarget, new Color4(0, 0, 0, 1));
"""
s = s.replace(marker, replacement, 1)
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Version/runtime labels. Architecture stays byte-for-byte v0.13.31.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
s = p.read_text(encoding="utf-8")
s = re.sub(
    r"(pc-stereo-layout\\.js\\?v=)[^\"']+",
    r"\g<1>0.13.35-correct-lr",
    s,
    count=1,
)
s = s.replace("GeoGebraForQuest PC v0.13.31", "GeoGebraForQuest PC v0.13.35")
s = s.replace("v0.13.31", "v0.13.35")
s = s.replace("0.13.31-raw-legacy-bgra", "0.13.35-correct-lr")
p.write_text(s, encoding="utf-8")

p = Path("pc/GeoGebraForQuest.PC.csproj")
s = p.read_text(encoding="utf-8")
s = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.35</Version>", s, count=1)
s = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.35.0</FileVersion>", s, count=1)
s = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.35.0</AssemblyVersion>", s, count=1)
p.write_text(s, encoding="utf-8")

p = Path("pc/build.ps1")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "GeoGebraForQuest-PC-v0.13.31-raw-legacy-bgra-win-x64",
    "GeoGebraForQuest-PC-v0.13.35-correct-lr-win-x64",
)
s = s.replace("0.13.31-raw-legacy-bgra", "0.13.35-correct-lr")
s = s.replace(r"0\.13\.31-raw-legacy-bgra", r"0\.13\.35-correct-lr")
s = s.replace("v0.13.31", "v0.13.35")
s = s.replace(r"v0\.13\.31", r"v0\.13\.35")
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Hard architecture guards: do not silently reintroduce embedded SBS.
# ---------------------------------------------------------------------------
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
writer = Path("pc/StereoSharedFrameWriter.cs").read_text(encoding="utf-8")
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")
xr = Path("pc-xr/main-v11.cpp").read_text(encoding="utf-8")
graphics = Path("pc/MainFormV11.Graphics.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

required = (
    (runtime, "type: 'stereoRawPair'", "raw true-L/R IPC missing"),
    (runtime, "leftCaptureContext.getImageData", "LEFT eye source missing"),
    (runtime, "rightCaptureContext.getImageData", "RIGHT eye source missing"),
    (runtime, "window.ggqRawStereoAck", "raw ACK gate missing"),
    (writer, "_view.Write(116, 1)", "legacy BGRA pixelFormat=1 missing"),
    (render, "pairFrame->pixelFormat == 1", "XR legacy BGRA compositor gate missing"),
    (xr, "sbsFrame_.pixelFormat == 1", "XR legacy true-L/R pair gate missing"),
    (graphics, "v0.13.35: D3D immediate-context state is global", "PC viewport guard missing"),
    (project, "<Version>0.13.35</Version>", "v0.13.35 project version missing"),
    (build, "v0.13.35-correct-lr", "v0.13.35 package label missing"),
)
for text, needle, label in required:
    require(text, needle, "v0.13.35: " + label)

forbidden = (
    (runtime, "__ggqPcGpuNativeSbs", "embedded-SBS JS path present"),
    (writer, "_view.Write(116, 4)", "embedded-SBS pixelFormat=4 writer present"),
    (render, "pairFrame->pixelFormat == 4", "embedded-SBS XR split path present"),
    (xr, "sbsFrame_.pixelFormat == 4", "embedded-SBS XR main path present"),
)
for text, needle, label in forbidden:
    if needle in text:
        raise SystemExit("v0.13.35: " + label)

print("GeoGebraForQuest PC v0.13.35 correct-L/R recovery patch applied")
