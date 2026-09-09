#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.36 — automatic log.zip bundle.

Keep the v0.13.35 stereo and PC presentation architecture unchanged.
On orderly application shutdown, after XR has stopped and host telemetry has
closed its writers, gather every GeoGebraForQuestPC telemetry/log file from the
application root and xr/ folder into one easy-to-share log.zip.
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Bundle logs only after the XR child has been stopped and telemetry closed.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
s = p.read_text(encoding="utf-8")
marker = "        _performanceTelemetry.Dispose();\n"
require(s, marker, "v0.13.36 telemetry shutdown marker missing")
if "        LogBundle.Create();\n" not in s:
    s = s.replace(
        marker,
        marker +
        "        // v0.13.36: one user-facing diagnostics bundle. XR is already\n"
        "        // stopped above and host telemetry writers are now closed.\n"
        "        LogBundle.Create();\n",
        1,
    )

s = re.sub(
    r"(pc-stereo-layout\\.js\\?v=)[^\"']+",
    r"\g<1>0.13.36-logzip",
    s,
    count=1,
)
s = s.replace("GeoGebraForQuest PC v0.13.35", "GeoGebraForQuest PC v0.13.36")
s = s.replace("v0.13.35", "v0.13.36")
s = s.replace("0.13.35-correct-lr", "0.13.36-logzip")
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Version/package labels only. Stereo code remains v0.13.35.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
s = p.read_text(encoding="utf-8")
s = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.36</Version>", s, count=1)
s = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.36.0</FileVersion>", s, count=1)
s = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.36.0</AssemblyVersion>", s, count=1)
p.write_text(s, encoding="utf-8")

p = Path("pc/build.ps1")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "GeoGebraForQuest-PC-v0.13.35-correct-lr-win-x64",
    "GeoGebraForQuest-PC-v0.13.36-logzip-win-x64",
)
s = s.replace("0.13.35-correct-lr", "0.13.36-logzip")
s = s.replace(r"0\.13\.35-correct-lr", r"0\.13\.36-logzip")
s = s.replace("v0.13.35", "v0.13.36")
s = s.replace(r"v0\.13\.35", r"v0\.13\.36")
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Guards: logging convenience must not alter the proven stereo path.
# ---------------------------------------------------------------------------
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
writer = Path("pc/StereoSharedFrameWriter.cs").read_text(encoding="utf-8")
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")
xr = Path("pc-xr/main-v11.cpp").read_text(encoding="utf-8")
graphics = Path("pc/MainFormV11.Graphics.cs").read_text(encoding="utf-8")
main = Path("pc/MainFormV11.cs").read_text(encoding="utf-8")
log_bundle = Path("pc/LogBundle.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

required = (
    (runtime, "type: 'stereoRawPair'", "raw true-L/R IPC missing"),
    (runtime, "leftCaptureContext.getImageData", "LEFT eye source missing"),
    (runtime, "rightCaptureContext.getImageData", "RIGHT eye source missing"),
    (runtime, "window.ggqRawStereoAck", "raw ACK gate missing"),
    (writer, "_view.Write(116, 1)", "legacy BGRA pixelFormat=1 missing"),
    (render, "pairFrame->pixelFormat == 1", "XR legacy BGRA compositor missing"),
    (xr, "sbsFrame_.pixelFormat == 1", "XR true-L/R pair gate missing"),
    (graphics, "v0.13.35: D3D immediate-context state is global", "PC viewport guard missing"),
    (main, "LogBundle.Create();", "log bundle shutdown call missing"),
    (log_bundle, 'Path.Combine(baseDir, "log.zip")', "log.zip target missing"),
    (log_bundle, "GeoGebraForQuestPC.Performance.Host.csv", "Host telemetry bundling missing"),
    (log_bundle, "GeoGebraForQuestPC.Performance.JS.jsonl", "JS telemetry bundling missing"),
    (log_bundle, "GeoGebraForQuestPC.Performance.XR.csv", "XR telemetry bundling missing"),
    (project, "<Version>0.13.36</Version>", "v0.13.36 version missing"),
    (build, "v0.13.36-logzip", "v0.13.36 package label missing"),
)
for text, needle, label in required:
    require(text, needle, "v0.13.36: " + label)

forbidden = (
    (runtime, "__ggqPcGpuNativeSbs", "embedded-SBS JS path present"),
    (writer, "_view.Write(116, 4)", "embedded-SBS writer present"),
    (render, "pairFrame->pixelFormat == 4", "embedded-SBS XR split present"),
    (xr, "sbsFrame_.pixelFormat == 4", "embedded-SBS XR main path present"),
)
for text, needle, label in forbidden:
    if needle in text:
        raise SystemExit("v0.13.36: " + label)

print("GeoGebraForQuest PC v0.13.36 log.zip patch applied")
