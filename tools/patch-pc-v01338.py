#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.38 — locked stereo baseline.

This release intentionally makes NO stereo capture, transport, MMF, XR,
or GeoGebra Web3D changes. It keeps the user-verified v0.13.35 stereo path
and the v0.13.36 log.zip convenience, and changes only release/cache/package
labels.

Stereo is treated as an immutable subsystem from this point forward:
  GeoGebra LEFT snapshot + final RIGHT WebGL
    -> separate left/right capture canvases
    -> separate getImageData() latches
    -> raw TRUE L/R pair
    -> legacy BGRA MMF pixelFormat=1
    -> proven A_L/A_R XR compositor
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# MainForm: cache/version labels only. Do not touch stereo handlers.
p = Path("pc/MainFormV11.cs")
s = p.read_text(encoding="utf-8")
require(s, "TryHandleRawStereoMessage", "v0.13.38 raw stereo host dispatcher missing before relabel")
require(s, '"stereoRawPair"', "v0.13.38 raw stereo message type missing before relabel")
require(s, "HandleRawStereoPair", "v0.13.38 raw stereo host handler missing before relabel")
require(s, "LogBundle.Create();", "v0.13.38 log.zip shutdown hook missing")
s = re.sub(
    r"(pc-stereo-layout\\.js\\?v=)[^\"']+",
    r"\g<1>0.13.38-locked-stereo",
    s,
    count=1,
)
s = s.replace("GeoGebraForQuest PC v0.13.36", "GeoGebraForQuest PC v0.13.38")
s = s.replace("0.13.36-logzip", "0.13.38-locked-stereo")
s = s.replace("v0.13.36", "v0.13.38")
p.write_text(s, encoding="utf-8")


# Assembly/package labels only.
p = Path("pc/GeoGebraForQuest.PC.csproj")
s = p.read_text(encoding="utf-8")
s = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.38</Version>", s, count=1)
s = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.38.0</FileVersion>", s, count=1)
s = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.38.0</AssemblyVersion>", s, count=1)
p.write_text(s, encoding="utf-8")

p = Path("pc/build.ps1")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "GeoGebraForQuest-PC-v0.13.36-logzip-win-x64",
    "GeoGebraForQuest-PC-v0.13.38-locked-stereo-win-x64",
)
s = s.replace("0.13.36-logzip", "0.13.38-locked-stereo")
s = s.replace(r"0\.13\.36-logzip", r"0\.13\.38-locked-stereo")
s = s.replace("v0.13.36", "v0.13.38")
s = s.replace(r"v0\.13\.36", r"v0\.13\.38")
p.write_text(s, encoding="utf-8")


# Runtime invariants. These are deliberately the v0.13.35/v0.13.36 ones.
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
writer = Path("pc/StereoSharedFrameWriter.cs").read_text(encoding="utf-8")
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")
xr = Path("pc-xr/main-v11.cpp").read_text(encoding="utf-8")
graphics = Path("pc/MainFormV11.Graphics.cs").read_text(encoding="utf-8")
main = Path("pc/MainFormV11.cs").read_text(encoding="utf-8")
bundle = Path("pc/LogBundle.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

required = (
    (runtime, "type: 'stereoRawPair'", "raw TRUE L/R IPC missing"),
    (runtime, "leftCaptureContext.getImageData", "separate LEFT latch missing"),
    (runtime, "rightCaptureContext.getImageData", "separate RIGHT latch missing"),
    (runtime, "window.ggqRawStereoAck", "raw ACK gate missing"),
    (writer, "_view.Write(116, 1)", "legacy BGRA pixelFormat=1 missing"),
    (render, "pairFrame->pixelFormat == 1", "XR legacy BGRA compositor missing"),
    (xr, "sbsFrame_.pixelFormat == 1", "XR TRUE L/R pair gate missing"),
    (graphics, "v0.13.35: D3D immediate-context state is global", "desktop viewport guard missing"),
    (main, "TryHandleRawStereoMessage", "host raw stereo dispatcher missing"),
    (main, '"stereoRawPair"', "host raw stereo message type missing"),
    (main, "HandleRawStereoPair", "host raw stereo handler missing"),
    (main, "LogBundle.Create();", "log.zip shutdown hook missing"),
    (bundle, 'Path.Combine(baseDir, "log.zip")', "log.zip target missing"),
    (project, "<Version>0.13.38</Version>", "v0.13.38 project version missing"),
    (build, "v0.13.38-locked-stereo", "v0.13.38 package label missing"),
)
for text, needle, label in required:
    require(text, needle, "v0.13.38: " + label)

forbidden = (
    (runtime, "rawPairCaptureContext.getImageData", "v0.13.37 single-readback path present"),
    (runtime, "__ggqPcGpuNativeSbs", "embedded-SBS JS path present"),
    (writer, "_view.Write(116, 4)", "embedded-SBS writer present"),
    (render, "pairFrame->pixelFormat == 4", "embedded-SBS XR split present"),
    (xr, "sbsFrame_.pixelFormat == 4", "embedded-SBS XR main path present"),
)
for text, needle, label in forbidden:
    if needle in text:
        raise SystemExit("v0.13.38: " + label)

print("GeoGebraForQuest PC v0.13.38 locked-stereo release patch applied")
