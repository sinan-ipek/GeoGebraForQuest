#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.37 — single-readback raw stereo transport.

Start from the proven v0.13.36/v0.13.35 architecture and change ONLY the
raw L/R capture/transport hot path:

    proven GeoGebra LEFT_EYE + RIGHT_EYE sources
      -> one detached SBS 2D canvas
      -> ONE getImageData() readback
      -> one CefSharp ArrayBuffer message
      -> existing host raw handler
      -> optimized RGBA->BGRA swizzle
      -> existing pixelFormat=1 MMF
      -> existing A_L/A_R XR compositor

This removes the v0.13.31 per-eye readbacks plus the extra 9 MB JavaScript
row-by-row SBS packing allocation/copy, while preserving the exact same eye
sources, eye order, resolution calculation, host ACK gate, MMF format, XR UVs,
PC viewport guard, and v0.13.36 log.zip bundling.
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) JavaScript: two proven eye sources -> ONE detached SBS readback canvas.
# ---------------------------------------------------------------------------
p = Path("pc/pc-stereo-layout.js")
s = p.read_text(encoding="utf-8")

require(s, "  var CAPTURE_INTERVAL_MS = 16;\n", "v0.13.37 raw cadence marker missing")
require(s, "  function beginRawStereoCapture(serial, requestedAt) {", "v0.13.37 raw capture function missing")
require(s, "type: 'stereoRawPair'", "v0.13.37 raw pair IPC marker missing")
require(s, "window.ggqRawStereoAck", "v0.13.37 raw ACK marker missing")
require(s, "configureCaptureContext(rightCaptureContext);\n", "v0.13.37 capture context insertion marker missing")

insert_marker = "configureCaptureContext(rightCaptureContext);\n"
insert_block = r'''

  // v0.13.37: one detached SBS canvas for both proven eye images.  It is never
  // attached to the DOM, so this cannot alter A or the PC presentation.
  // willReadFrequently asks Chromium to optimize this canvas for the exact
  // operation we perform every frame: draw two images, then read pixels once.
  var rawPairCaptureCanvas = document.createElement('canvas');
  var rawPairCaptureContext = rawPairCaptureCanvas.getContext('2d', {
    alpha: false,
    desynchronized: true,
    willReadFrequently: true
  });
  if (rawPairCaptureContext) {
    rawPairCaptureContext.imageSmoothingEnabled = true;
    rawPairCaptureContext.imageSmoothingQuality = 'high';
  }

  // Focused telemetry for the remaining hot path.  The host already owns the
  // performanceSample bridge; these samples make JS.jsonl useful again and are
  // automatically included in v0.13.36+ log.zip.
  var perf37WindowStartedAt = performance.now();
  var perf37DrawCount = 0;
  var perf37DrawMsSum = 0;
  var perf37DrawMsMax = 0;
  var perf37ReadCount = 0;
  var perf37ReadMsSum = 0;
  var perf37ReadMsMax = 0;
  var perf37PostCount = 0;
  var perf37PostMsSum = 0;
  var perf37PostMsMax = 0;
  var perf37AckCount = 0;
  var perf37AckMsSum = 0;
  var perf37AckMsMax = 0;
  var perf37CycleCount = 0;
  var perf37CycleMsSum = 0;
  var perf37CycleMsMax = 0;
  var perf37RawBytesSum = 0;
  var perf37RawBytesMax = 0;
  var perf37LastEyeWidth = 0;
  var perf37LastEyeHeight = 0;

  function emitPerformanceSample37() {
    var now = performance.now();
    var elapsed = Math.max(1, now - perf37WindowStartedAt);
    var sample = {
      kind: 'js-stereo-single-readback-v01337',
      elapsedMs: elapsed,
      targetIntervalMs: CAPTURE_INTERVAL_MS,
      actualAckFps: perf37AckCount * 1000 / elapsed,
      drawCount: perf37DrawCount,
      avgDrawMs: perf37DrawCount ? perf37DrawMsSum / perf37DrawCount : 0,
      maxDrawMs: perf37DrawMsMax,
      readbackCount: perf37ReadCount,
      avgReadbackMs: perf37ReadCount ? perf37ReadMsSum / perf37ReadCount : 0,
      maxReadbackMs: perf37ReadMsMax,
      postCount: perf37PostCount,
      avgPostMessageMs: perf37PostCount ? perf37PostMsSum / perf37PostCount : 0,
      maxPostMessageMs: perf37PostMsMax,
      ackCount: perf37AckCount,
      avgHostAckMs: perf37AckCount ? perf37AckMsSum / perf37AckCount : 0,
      maxHostAckMs: perf37AckMsMax,
      avgCycleMs: perf37CycleCount ? perf37CycleMsSum / perf37CycleCount : 0,
      maxCycleMs: perf37CycleMsMax,
      avgRawBytes: perf37PostCount ? perf37RawBytesSum / perf37PostCount : 0,
      maxRawBytes: perf37RawBytesMax,
      eyeWidth: perf37LastEyeWidth,
      eyeHeight: perf37LastEyeHeight,
      rawInFlight: !!rawInFlight
    };
    bridge('performanceSample', JSON.stringify(sample));

    perf37WindowStartedAt = now;
    perf37DrawCount = 0;
    perf37DrawMsSum = 0;
    perf37DrawMsMax = 0;
    perf37ReadCount = 0;
    perf37ReadMsSum = 0;
    perf37ReadMsMax = 0;
    perf37PostCount = 0;
    perf37PostMsSum = 0;
    perf37PostMsMax = 0;
    perf37AckCount = 0;
    perf37AckMsSum = 0;
    perf37AckMsMax = 0;
    perf37CycleCount = 0;
    perf37CycleMsSum = 0;
    perf37CycleMsMax = 0;
    perf37RawBytesSum = 0;
    perf37RawBytesMax = 0;
  }
  setInterval(emitPerformanceSample37, 1000);
'''
s = s.replace(insert_marker, insert_marker + insert_block, 1)

# Add a dedicated size helper.  The old per-eye capture canvases stay at their
# tiny default size and are no longer used for raw readback, so they consume no
# large backing stores and we avoid touching unrelated legacy helper code.
helper_marker = "  function readStereoFrameSerial() {\n"
require(s, helper_marker, "v0.13.37 helper insertion marker missing")
helper = r'''  function ensureRawPairCaptureSize(eyeWidth, eyeHeight) {
    var sbsWidth = Math.max(2, eyeWidth * 2);
    if (rawPairCaptureCanvas.width !== sbsWidth) rawPairCaptureCanvas.width = sbsWidth;
    if (rawPairCaptureCanvas.height !== eyeHeight) rawPairCaptureCanvas.height = eyeHeight;
    if (rawPairCaptureContext) {
      rawPairCaptureContext.imageSmoothingEnabled = true;
      rawPairCaptureContext.imageSmoothingQuality = 'high';
    }
  }

'''
s = s.replace(helper_marker, helper + helper_marker, 1)

capture_start = s.find("  function beginRawStereoCapture(serial, requestedAt) {")
capture_end = s.find("\n  // Host ACK", capture_start)
if capture_start < 0 or capture_end < 0:
    raise SystemExit("v0.13.37 raw capture block boundaries missing")

new_capture = r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!rawPairCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    // EXACT same renderer-eye sources that create real depth in v0.13.35.
    var eyes = getRendererEyeCanvases();
    if (!eyes) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(
        sourceWidth,
        sourceHeight,
        geometry.rect
      );
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;
      ensureRawPairCaptureSize(eyeWidth, eyeHeight);

      // Draw both complete eyes side-by-side directly into the final transport
      // layout.  Every pixel is overwritten, so no clearRect pass is needed.
      var drawStartedAt = performance.now();
      rawPairCaptureContext.setTransform(1, 0, 0, 1, 0, 0);
      rawPairCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      rawPairCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        eyeWidth, 0, eyeWidth, eyeHeight
      );
      var drawMs = Math.max(0, performance.now() - drawStartedAt);
      perf37DrawCount++;
      perf37DrawMsSum += drawMs;
      perf37DrawMsMax = Math.max(perf37DrawMsMax, drawMs);

      // ONE readback for the whole [true L | true R] pair.  v0.13.31 performed
      // two readbacks and then allocated/copied another full SBS buffer in JS.
      var readStartedAt = performance.now();
      var image = rawPairCaptureContext.getImageData(
        0, 0, eyeWidth * 2, eyeHeight
      );
      var readMs = Math.max(0, performance.now() - readStartedAt);
      perf37ReadCount++;
      perf37ReadMsSum += readMs;
      perf37ReadMsMax = Math.max(perf37ReadMsMax, readMs);

      var sbsStride = eyeWidth * 2 * 4;
      var expectedBytes = sbsStride * eyeHeight;
      if (!image || !image.data || image.data.byteLength !== expectedBytes) {
        throw new Error('single-readback TRUE L/R byte length uyuşmuyor');
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      // Post ImageData's existing ArrayBuffer directly: no second 9 MB pair
      // allocation and no row-by-row pair.set() packing pass.
      var postStartedAt = performance.now();
      var posted = postHostMessage({
        type: 'stereoRawPair',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: sbsStride,
        rgba: image.data.buffer
      });
      var postMs = Math.max(0, performance.now() - postStartedAt);

      if (!posted) {
        rawInFlight = false;
        rawInFlightSerial = -1;
        rawInFlightRequestedAt = 0;
        rawPostedAt = 0;
        nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
        return false;
      }

      perf37PostCount++;
      perf37PostMsSum += postMs;
      perf37PostMsMax = Math.max(perf37PostMsMax, postMs);
      perf37RawBytesSum += expectedBytes;
      perf37RawBytesMax = Math.max(perf37RawBytesMax, expectedBytes);
      perf37LastEyeWidth = eyeWidth;
      perf37LastEyeHeight = eyeHeight;
      return true;
    } catch (error) {
      rawInFlight = false;
      rawInFlightSerial = -1;
      rawInFlightRequestedAt = 0;
      rawPostedAt = 0;
      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
      reportRuntimeError(
        'Single-readback exact-L/R capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }
'''
s = s[:capture_start] + new_capture + s[capture_end:]

ack_start = s.find("  window.ggqRawStereoAck = function (serial, ok) {")
ack_end = s.find("\n  function captureLoop(now) {", ack_start)
if ack_start < 0 or ack_end < 0:
    raise SystemExit("v0.13.37 ACK block boundaries missing")

new_ack = r'''  window.ggqRawStereoAck = function (serial, ok) {
    serial = Number(serial);
    if (!rawInFlight || !isFinite(serial) || serial !== rawInFlightSerial) {
      return false;
    }

    var now = performance.now();
    var ackMs = rawPostedAt ? Math.max(0, now - rawPostedAt) : 0;
    var requestedAt = rawInFlightRequestedAt;
    var cycleMs = requestedAt ? Math.max(0, now - requestedAt) : 0;

    perf37AckCount++;
    perf37AckMsSum += ackMs;
    perf37AckMsMax = Math.max(perf37AckMsMax, ackMs);
    perf37CycleCount++;
    perf37CycleMsSum += cycleMs;
    perf37CycleMsMax = Math.max(perf37CycleMsMax, cycleMs);

    if (ok !== false) lastDeliveredStereoSerial = serial;
    rawInFlight = false;
    rawInFlightSerial = -1;
    rawInFlightRequestedAt = 0;
    rawPostedAt = 0;
    nextStereoRequestAt = requestedAt && cycleMs < CAPTURE_INTERVAL_MS
      ? requestedAt + CAPTURE_INTERVAL_MS
      : now + 1;
    return true;
  };
'''
s = s[:ack_start] + new_ack + s[ack_end:]

# Hard safety: v0.13.37 must have only the one large readback path and must not
# reintroduce JPEG, visible DOM phase capture, or embedded-SBS-in-CEF logic.
for forbidden in (
    'leftCaptureContext.getImageData',
    'rightCaptureContext.getImageData',
    'pair.set(',
    'canvasToDataUrlAsync',
    'CAPTURE_JPEG_QUALITY',
    "'image/jpeg'",
    '"image/jpeg"',
    'ggq-pc-raw-left-eye-overlay',
    '__ggqPcGpuNativeSbs',
):
    if forbidden in s:
        raise SystemExit(f"v0.13.37 forbidden runtime residue: {forbidden}")

for needed in (
    "type: 'stereoRawPair'",
    'rawPairCaptureContext.getImageData',
    'willReadFrequently: true',
    'window.ggqRawStereoAck',
    "document.getElementById('ggq-renderer-left-eye')",
    "document.getElementById('ggq-renderer-right-eye')",
    "kind: 'js-stereo-single-readback-v01337'",
):
    require(s, needed, f"v0.13.37 runtime invariant missing: {needed}")

p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Host: make the already-small RGBA->BGRA stage cheaper without changing
#    output bytes.  One uint bit-swap replaces tuple byte assignments per pixel.
# ---------------------------------------------------------------------------
p = Path("pc/StereoSharedFrameWriter.cs")
s = p.read_text(encoding="utf-8")
old_swizzle = '''            for (var i = 0; i < totalBytes; i += 4)\n            {\n                (rgbaSbs[i], rgbaSbs[i + 2]) = (rgbaSbs[i + 2], rgbaSbs[i]);\n            }\n'''
require(s, old_swizzle, "v0.13.37 legacy RGBA->BGRA swizzle marker missing")
new_swizzle = '''            // v0.13.37: exact same RGBA -> BGRA conversion, but operate on\n            // 32-bit pixels. On little-endian Windows RGBA bytes are\n            // 0xAABBGGRR; swapping the low and third byte yields 0xAARRGGBB.\n            var pixels = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, uint>(\n                rgbaSbs.AsSpan(0, totalBytes));\n            for (var i = 0; i < pixels.Length; i++)\n            {\n                var value = pixels[i];\n                pixels[i] =\n                    (value & 0xFF00FF00u) |\n                    ((value & 0x000000FFu) << 16) |\n                    ((value & 0x00FF0000u) >> 16);\n            }\n'''
s = s.replace(old_swizzle, new_swizzle, 1)
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Update build guards and labels; preserve log.zip and proven XR architecture.
# ---------------------------------------------------------------------------
p = Path("pc/build.ps1")
s = p.read_text(encoding="utf-8")

# v0.13.31/35/36 guards expected two per-eye readbacks. Replace them with the
# single-readback invariant so the old validation layer checks the new hot path.
s, count = re.subn(
    r'if \(-not \$runtimeText\.Contains\("leftCaptureContext\.getImageData"\)\) \{ throw "[^"]*" \}\r?\n'
    r'if \(-not \$runtimeText\.Contains\("rightCaptureContext\.getImageData"\)\) \{ throw "[^"]*" \}\r?\n',
    'if (-not $runtimeText.Contains("rawPairCaptureContext.getImageData")) { throw "v0.13.37 doğrulaması: single SBS readback eksik." }\n'
    'if (-not $runtimeText.Contains("willReadFrequently: true")) { throw "v0.13.37 doğrulaması: readback-optimized canvas eksik." }\n',
    s,
    count=1,
)
if count != 1:
    raise SystemExit("v0.13.37 build single-readback guard cluster missing")

s = s.replace(
    "GeoGebraForQuest-PC-v0.13.36-logzip-win-x64",
    "GeoGebraForQuest-PC-v0.13.37-single-readback-win-x64",
)
s = s.replace("0.13.36-logzip", "0.13.37-single-readback")
s = s.replace(r"0\.13\.36-logzip", r"0\.13\.37-single-readback")
s = s.replace("v0.13.36", "v0.13.37")
s = s.replace(r"v0\.13\.36", r"v0\.13\.37")
p.write_text(s, encoding="utf-8")

p = Path("pc/MainFormV11.cs")
s = p.read_text(encoding="utf-8")
s = re.sub(
    r"(pc-stereo-layout\\.js\\?v=)[^\"']+",
    r"\g<1>0.13.37-single-readback",
    s,
    count=1,
)
s = s.replace("GeoGebraForQuest PC v0.13.36", "GeoGebraForQuest PC v0.13.37")
s = s.replace("v0.13.36", "v0.13.37")
s = s.replace("0.13.36-logzip", "0.13.37-single-readback")
p.write_text(s, encoding="utf-8")

p = Path("pc/GeoGebraForQuest.PC.csproj")
s = p.read_text(encoding="utf-8")
s = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.37</Version>", s, count=1)
s = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.37.0</FileVersion>", s, count=1)
s = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.37.0</AssemblyVersion>", s, count=1)
p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Final architecture guards.
# ---------------------------------------------------------------------------
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
writer = Path("pc/StereoSharedFrameWriter.cs").read_text(encoding="utf-8")
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")
xr = Path("pc-xr/main-v11.cpp").read_text(encoding="utf-8")
graphics = Path("pc/MainFormV11.Graphics.cs").read_text(encoding="utf-8")
main = Path("pc/MainFormV11.cs").read_text(encoding="utf-8")
telemetry = Path("pc/PerformanceTelemetry.cs").read_text(encoding="utf-8")
log_bundle = Path("pc/LogBundle.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

required = (
    (runtime, "type: 'stereoRawPair'", "raw true-L/R IPC missing"),
    (runtime, "rawPairCaptureContext.getImageData", "single SBS readback missing"),
    (runtime, "willReadFrequently: true", "readback-optimized canvas missing"),
    (runtime, "kind: 'js-stereo-single-readback-v01337'", "JS telemetry missing"),
    (runtime, "window.ggqRawStereoAck", "ACK gate missing"),
    (writer, "MemoryMarshal.Cast<byte, uint>", "fast BGRA swizzle missing"),
    (writer, "_view.Write(116, 1)", "legacy BGRA pixelFormat=1 missing"),
    (render, "pairFrame->pixelFormat == 1", "proven XR compositor gate missing"),
    (xr, "sbsFrame_.pixelFormat == 1", "XR true-L/R pair gate missing"),
    (graphics, "v0.13.35: D3D immediate-context state is global", "PC viewport guard missing"),
    (main, "LogBundle.Create();", "log.zip shutdown bundle missing"),
    (main, 'case "performanceSample":', "performanceSample host bridge missing"),
    (telemetry, "GeoGebraForQuestPC.Performance.JS.jsonl", "JS telemetry writer missing"),
    (log_bundle, 'Path.Combine(baseDir, "log.zip")', "log.zip target missing"),
    (project, "<Version>0.13.37</Version>", "v0.13.37 version missing"),
    (build, "v0.13.37-single-readback", "v0.13.37 package label missing"),
)
for text, needle, label in required:
    require(text, needle, "v0.13.37: " + label)

forbidden = (
    (runtime, "leftCaptureContext.getImageData", "old LEFT readback remains"),
    (runtime, "rightCaptureContext.getImageData", "old RIGHT readback remains"),
    (runtime, "pair.set(", "old JS SBS packing copy remains"),
    (runtime, "__ggqPcGpuNativeSbs", "embedded-SBS JS path present"),
    (writer, "_view.Write(116, 4)", "embedded-SBS writer present"),
    (render, "pairFrame->pixelFormat == 4", "embedded-SBS XR split present"),
    (xr, "sbsFrame_.pixelFormat == 4", "embedded-SBS XR main path present"),
)
for text, needle, label in forbidden:
    if needle in text:
        raise SystemExit("v0.13.37: " + label)

print("GeoGebraForQuest PC v0.13.37 single-readback optimization applied")
