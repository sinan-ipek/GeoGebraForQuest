from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.31
#
# Keep the v0.13.29 architecture that is now runtime-proven to create depth:
#   true L/R -> A_L|A_R single-panel compositor -> Quest/OpenXR.
#
# Change ONLY the transport/publication layer:
#   - Use the SAME two leftCaptureCanvas/rightCaptureCanvas images that the
#     working v0.13.29 JPEG encoder consumed.
#   - Read those exact canvases as raw RGBA ImageData.
#   - Send one binary ArrayBuffer through CefSharp.PostMessage.
#   - On the host, reuse the existing v0.13.28 raw handler.
#   - Before MMF publication, convert RGBA -> BGRA and mark pixelFormat=1 so
#     XR sees the EXACT legacy format already proven by v0.13.29.
#
# This deliberately does NOT touch the single-panel compositor, eye UV mapping,
# panel geometry, menu overlays, cursor behavior, or A's CEF GPU path.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) JS: exact working L/R capture canvases -> raw binary pair.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

req(s, '  var CAPTURE_INTERVAL_MS = 33;\n', 'v0.13.31 proven cadence marker missing')
s = s.replace('  var CAPTURE_INTERVAL_MS = 33;\n', '  var CAPTURE_INTERVAL_MS = 16;\n', 1)

# JPEG quality is no longer used at runtime.
s = s.replace('  var CAPTURE_JPEG_QUALITY = 0.99;\n', '', 1)

req(s, '  var encodingInFlight = false;\n', 'v0.13.31 encodingInFlight marker missing')
s = s.replace(
    '  var encodingInFlight = false;\n',
    '''  var rawInFlight = false;\n  var rawInFlightSerial = -1;\n  var rawInFlightRequestedAt = 0;\n  var rawPostedAt = 0;\n  var RAW_ACK_TIMEOUT_MS = 1500;\n''',
    1)

# Direct binary IPC helper. v0.13.24 proved this CefSharp ArrayBuffer route works.
bridge_marker = '''  function bridgeStereoEyes(leftDataUrl, rightDataUrl) {\n    try {\n      if (window.QuestBridge &&\n          typeof window.QuestBridge.updateStereoEyes === 'function') {\n        window.QuestBridge.updateStereoEyes(leftDataUrl, rightDataUrl);\n      }\n    } catch (_) {}\n  }\n'''
req(s, bridge_marker, 'v0.13.31 bridgeStereoEyes marker missing')
post_helper = bridge_marker + '''\n  function postHostMessage(payload) {\n    try {\n      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {\n        window.CefSharp.PostMessage(payload);\n        return true;\n      }\n    } catch (error) {\n      reportRuntimeError(\n        'Raw IPC post hatası: ' +\n        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))\n      );\n    }\n    return false;\n  }\n'''
s = s.replace(bridge_marker, post_helper, 1)

start = s.find('  function canvasToDataUrlAsync(canvas) {')
end = s.find('\n  function pollRequestedStereoPair(now) {', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.31 JPEG capture block boundaries missing')

raw_capture = r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!leftCaptureContext || !rightCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    // IMPORTANT: these are the exact same renderer-eye canvases used by the
    // depth-proven v0.13.29 JPEG path.
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
      ensureCaptureCanvasSize(eyeWidth, eyeHeight);

      // EXACT v0.13.29 draw stage: do not combine or reinterpret the source eyes.
      leftCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      rightCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );

      var leftImage = leftCaptureContext.getImageData(0, 0, eyeWidth, eyeHeight);
      var rightImage = rightCaptureContext.getImageData(0, 0, eyeWidth, eyeHeight);
      if (!leftImage || !leftImage.data || !rightImage || !rightImage.data) {
        throw new Error('raw L/R ImageData boş');
      }

      var eyeStride = eyeWidth * 4;
      var sbsStride = eyeStride * 2;
      var expectedEyeBytes = eyeStride * eyeHeight;
      if (leftImage.data.byteLength !== expectedEyeBytes ||
          rightImage.data.byteLength !== expectedEyeBytes) {
        throw new Error('raw L/R ImageData boyutu uyuşmuyor');
      }

      // Pack row-by-row as true SBS [L | R]. This preserves the proven eye order.
      var pair = new Uint8Array(sbsStride * eyeHeight);
      for (var y = 0; y < eyeHeight; y++) {
        var src = y * eyeStride;
        var dst = y * sbsStride;
        pair.set(leftImage.data.subarray(src, src + eyeStride), dst);
        pair.set(rightImage.data.subarray(src, src + eyeStride), dst + eyeStride);
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      var posted = postHostMessage({
        type: 'stereoRawPair',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: sbsStride,
        rgba: pair.buffer
      });
      if (!posted) {
        rawInFlight = false;
        rawInFlightSerial = -1;
        rawInFlightRequestedAt = 0;
        rawPostedAt = 0;
        nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
        return false;
      }
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
        'Raw exact-L/R capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }

  // Host ACK is sent only after the raw frame has been converted to the legacy
  // BGRA MMF representation. This keeps at most one large binary message in flight.
  window.ggqRawStereoAck = function (serial, ok) {
    serial = Number(serial);
    if (!rawInFlight || !isFinite(serial) || serial !== rawInFlightSerial) {
      return false;
    }

    var now = performance.now();
    if (ok !== false) lastDeliveredStereoSerial = serial;
    var requestedAt = rawInFlightRequestedAt;
    var cycleMs = requestedAt ? Math.max(0, now - requestedAt) : 0;

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
s = s[:start] + raw_capture + s[end:]

s = s.replace(
    '    if (pendingStereoSerial === null || encodingInFlight) return false;\n',
    '    if (pendingStereoSerial === null || rawInFlight) return false;\n',
    1)
s = s.replace(
    '    return beginAsyncStereoCapture(serial, requestedAt);\n',
    '    return beginRawStereoCapture(serial, requestedAt);\n',
    1)

loop_start = s.find('  function captureLoop(now) {')
loop_end = s.find('\n  if (window.ResizeObserver) {', loop_start)
if loop_start < 0 or loop_end < 0:
    raise SystemExit('v0.13.31 captureLoop boundaries missing')
raw_loop = r'''  function captureLoop(now) {
    if (rawInFlight) {
      if (rawPostedAt > 0 && now - rawPostedAt > RAW_ACK_TIMEOUT_MS) {
        rawInFlight = false;
        rawInFlightSerial = -1;
        rawInFlightRequestedAt = 0;
        rawPostedAt = 0;
        nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      }
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!geometryState) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      requestAnimationFrame(captureLoop);
      return;
    }

    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!requestStereoPair(now)) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }

    requestAnimationFrame(captureLoop);
  }
'''
s = s[:loop_start] + raw_loop + s[loop_end:]

# No encoder or JPEG payload may remain reachable in this runtime.
for forbidden in ('canvasToDataUrlAsync', "'image/jpeg'", '"image/jpeg"', 'CAPTURE_JPEG_QUALITY'):
    if forbidden in s:
        raise SystemExit(f'v0.13.31 JPEG runtime residue: {forbidden}')

for needed in (
    "document.getElementById('ggq-renderer-left-eye')",
    "document.getElementById('ggq-renderer-right-eye')",
    "type: 'stereoRawPair'",
    'leftCaptureContext.getImageData',
    'rightCaptureContext.getImageData',
    'window.ggqRawStereoAck',
):
    req(s, needed, f'v0.13.31 raw runtime invariant missing: {needed}')

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Host writer: raw RGBA -> exact legacy BGRA MMF format=1.
#    The raw handler and ACK path already exist from v0.13.28.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')
method_start = s.find('    public void WriteRawStereoPairRgba(')
method_end = s.find('    public void SetInactive(', method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit('v0.13.31 raw pair writer boundaries missing')

writer = r'''    public void WriteRawStereoPairRgba(
        byte[] rgbaSbs,
        int eyeWidth,
        int eyeHeight,
        int sbsStride,
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        IReadOnlyList<Rectangle>? uiOverlayClientBounds,
        long frameNumber)
    {
        if (_disposed || rgbaSbs is null ||
            applicationClientSize.Width < 1 || applicationClientSize.Height < 1 ||
            stereoPanelClientBounds.Width < 2 || stereoPanelClientBounds.Height < 2 ||
            eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > MaxEyeWidth || eyeHeight > MaxEyeHeight)
        {
            return;
        }

        var expectedStride = checked(eyeWidth * 2 * 4);
        if (sbsStride != expectedStride)
            throw new ArgumentException("Raw TRUE L/R stride must be tightly packed SBS RGBA.");
        var totalBytes = checked(sbsStride * eyeHeight);
        if (rgbaSbs.Length != totalBytes)
            throw new ArgumentException("Raw TRUE L/R RGBA byte length mismatch.");

        lock (_sync)
        {
            // Canvas ImageData is top-down RGBA. The depth-proven legacy Bitmap path
            // publishes top-down BGRA (Format32bppArgb memory layout). Convert the
            // incoming byte[] IN PLACE so downstream MMF/XR sees exactly format=1.
            for (var i = 0; i < totalBytes; i += 4)
            {
                (rgbaSbs[i], rgbaSbs[i + 2]) = (rgbaSbs[i + 2], rgbaSbs[i]);
            }

            var evenSequence = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, evenSequence - 1);
            _view.Write(16, 1);
            _view.Write(20, applicationClientSize.Width);
            _view.Write(24, applicationClientSize.Height);
            _view.Write(28, stereoPanelClientBounds.Left);
            _view.Write(32, stereoPanelClientBounds.Top);
            _view.Write(36, stereoPanelClientBounds.Width);
            _view.Write(40, stereoPanelClientBounds.Height);
            _view.Write(44, eyeWidth);
            _view.Write(48, eyeHeight);
            _view.Write(52, sbsStride);
            _view.Write(56, unchecked((int)frameNumber));
            _view.Write(60, Environment.ProcessId);

            var overlayCount = Math.Min(
                MaxUiOverlayRects,
                uiOverlayClientBounds?.Count ?? 0);
            _view.Write(64, overlayCount);
            for (var i = 0; i < MaxUiOverlayRects; i++)
            {
                var offset = 68 + i * 16;
                var r = i < overlayCount
                    ? uiOverlayClientBounds![i]
                    : Rectangle.Empty;
                _view.Write(offset + 0, r.Left);
                _view.Write(offset + 4, r.Top);
                _view.Write(offset + 8, r.Width);
                _view.Write(offset + 12, r.Height);
            }

            // 1 = exact legacy BGRA SBS representation proven by v0.13.29.
            _view.Write(116, 1);
            _view.WriteArray(HeaderSize, rgbaSbs, 0, totalBytes);

            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s[:method_start] + writer + s[method_end:]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Version/cache/package labels and build guards.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')
s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.31-raw-legacy-bgra',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.29', 'GeoGebraForQuest PC v0.13.31')
p.write_text(s, encoding='utf-8')

p = Path('pc/GeoGebraForQuest.PC.csproj')
s = p.read_text(encoding='utf-8')
s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.31</Version>', s, count=1)
s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.31.0</FileVersion>', s, count=1)
s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.31.0</AssemblyVersion>', s, count=1)
p.write_text(s, encoding='utf-8')

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'GeoGebraForQuest-PC-v0.13.29-jpeg-proof-single-panel-win-x64',
    'GeoGebraForQuest-PC-v0.13.31-raw-legacy-bgra-win-x64')
s = s.replace('0.13.29-jpeg-proof-single-panel', '0.13.31-raw-legacy-bgra')
s = s.replace(r'0\.13\.29-jpeg-proof-single-panel', r'0\.13\.31-raw-legacy-bgra')
s = s.replace('v0.13.29', 'v0.13.31')
s = s.replace(r'v0\.13\.29', r'v0\.13\.31')

jpeg_guard = '''if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 33")) { throw "v0.13.31 doğrulaması: proven 33 ms JPEG cadence eksik." }
if (-not $runtimeText.Contains("CAPTURE_JPEG_QUALITY")) { throw "v0.13.31 doğrulaması: JPEG quality marker eksik." }
if (-not $runtimeText.Contains("canvasToDataUrlAsync")) { throw "v0.13.31 doğrulaması: proven JPEG encoder eksik." }
if (-not $runtimeText.Contains("bridgeStereoEyes")) { throw "v0.13.31 doğrulaması: proven L/R bridge eksik." }
if (-not $mainFormText.Contains("updateStereoEyes: function (left, right)")) { throw "v0.13.31 doğrulaması: host stereoEyes bridge eksik." }
if (-not $mainFormText.Contains('case "stereoEyes":')) { throw "v0.13.31 doğrulaması: host stereoEyes switch eksik." }
if (-not $writerText.Contains("_view.Write(116, 1)")) { throw "v0.13.31 doğrulaması: legacy BGRA MMF marker eksik." }
if (-not $sharedText.Contains("candidate.pixelFormat == 1")) { throw "v0.13.31 doğrulaması: XR legacy BGRA reader eksik." }
'''

# v0.13.29 guards are version-renamed above. Replace the whole cluster if present.
raw_guard = '''if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 16")) { throw "v0.13.31 doğrulaması: 16 ms raw cadence eksik." }
if (-not $runtimeText.Contains("type: 'stereoRawPair'")) { throw "v0.13.31 doğrulaması: raw pair IPC eksik." }
if (-not $runtimeText.Contains("leftCaptureContext.getImageData")) { throw "v0.13.31 doğrulaması: exact LEFT capture raw readback eksik." }
if (-not $runtimeText.Contains("rightCaptureContext.getImageData")) { throw "v0.13.31 doğrulaması: exact RIGHT capture raw readback eksik." }
if (-not $mainFormText.Contains("HandleRawStereoPair")) { throw "v0.13.31 doğrulaması: raw host handler eksik." }
if (-not $writerText.Contains("WriteRawStereoPairRgba")) { throw "v0.13.31 doğrulaması: raw writer eksik." }
if (-not $writerText.Contains("rgbaSbs[i + 2]")) { throw "v0.13.31 doğrulaması: RGBA->BGRA swizzle eksik." }
if (-not $writerText.Contains("_view.Write(116, 1)")) { throw "v0.13.31 doğrulaması: legacy BGRA MMF marker eksik." }
if (-not $sharedText.Contains("candidate.pixelFormat == 1")) { throw "v0.13.31 doğrulaması: XR legacy BGRA reader eksik." }
'''

if jpeg_guard in s:
    s = s.replace(jpeg_guard, raw_guard, 1)
else:
    # Robust fallback: replace from the first cadence proof line through the
    # shared legacy reader line.
    begin = s.find('if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 33"))')
    tail_token = 'if (-not $sharedText.Contains("candidate.pixelFormat == 1"))'
    tail = s.find(tail_token, begin)
    if begin < 0 or tail < 0:
        raise SystemExit('v0.13.31 build raw/JPEG guard cluster missing')
    tail_end = s.find('\n', tail)
    if tail_end < 0:
        tail_end = len(s)
    else:
        tail_end += 1
    s = s[:begin] + raw_guard + s[tail_end:]

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Final invariants.
# ---------------------------------------------------------------------------
checks = {
    'pc/pc-stereo-layout.js': [
        "type: 'stereoRawPair'",
        'leftCaptureContext.getImageData',
        'rightCaptureContext.getImageData',
        'window.ggqRawStereoAck',
        "document.getElementById('ggq-renderer-left-eye')",
        "document.getElementById('ggq-renderer-right-eye')",
    ],
    'pc/MainFormV11.cs': [
        'TryHandleRawStereoMessage',
        'HandleRawStereoPair',
        'AckRawStereo',
    ],
    'pc/StereoSharedFrameWriter.cs': [
        'WriteRawStereoPairRgba',
        '(rgbaSbs[i], rgbaSbs[i + 2])',
        '_view.Write(116, 1)',
    ],
    'pc-xr/v11-render.hpp': [
        'A_L/A_R SBS single-panel path',
        'pairFrame->pixelFormat == 1',
        'rightEye ? 0.5f : 0.0f',
    ],
    'pc-xr/main-v11.cpp': [
        'sbsFrame_.pixelFormat == 1',
        'fullSbsComposer_.Compose',
    ],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.31 invariant missing in {file}: {needle}')

runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
for forbidden in ('canvasToDataUrlAsync', 'CAPTURE_JPEG_QUALITY', "'image/jpeg'", '"image/jpeg"'):
    if forbidden in runtime:
        raise SystemExit(f'v0.13.31 forbidden JPEG runtime remains: {forbidden}')

print('GeoGebraForQuest PC v0.13.31 exact L/R raw -> legacy BGRA single-panel transport applied')
