from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


def sub_once(pattern: str, repl: str, text: str, label: str, flags=0) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: replacements={count}")
    return out


# ---------------------------------------------------------------------------
# v0.13.24
#
# Start from the known v0.13.22 behaviour and replace ONLY the stereo frame
# transport. Crucially, the visible GeoGebra/CEF compositor is never modified.
# No temporary left/right canvas is appended to the DOM, no A presentation is
# suppressed, and no accelerated-paint phase switching is used.
#
# New B path:
#   Exp46 left/right renderer canvases
#     -> detached 2D SBS canvas
#     -> getImageData RGBA
#     -> CefSharp.PostMessage(ArrayBuffer) native binary IPC
#     -> C# byte[]
#     -> existing SBS shared-memory mapping
#     -> XR texture
#
# CefSharp natively serializes V8 ArrayBuffer as CefBinaryValue and deserializes
# it in the browser process as byte[]. This avoids JPEG, Base64 and Bitmap decode.
# A remains the proven CEF GPU texture -> OpenXR path from v0.13.22.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1) JavaScript stereo runtime: detached raw SBS canvas + binary ArrayBuffer IPC.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

# Be conservative for the first raw transport build: one stereo request every
# ~33 ms maximum. The host ACK gate below prevents any binary-message backlog.
s = s.replace('  var CAPTURE_INTERVAL_MS = 16;', '  var CAPTURE_INTERVAL_MS = 33;', 1)
s = s.replace('  // v0.13.20: controlled ~60 fps stereo-B capture cadence test.\n',
              '  // v0.13.24: raw ArrayBuffer stereo transport, ~30 fps start cap.\n', 1)

state_start = s.find('  var pendingStereoSerial = null;')
bridge_start = s.find('  function bridge(name, value) {', state_start)
if state_start < 0 or bridge_start < 0:
    raise SystemExit('v0.13.24 JS state/bridge markers missing')

raw_state = r'''  var pendingStereoSerial = null;
  var pendingStereoRequestedAt = 0;
  var lastDeliveredStereoSerial = -1;
  var nextStereoRequestAt = 0;

  // At most one large ArrayBuffer is allowed to be in flight. The browser
  // process ACKs only after the raw SBS frame has been copied into the MMF.
  var rawInFlight = false;
  var rawInFlightSerial = -1;
  var rawInFlightRequestedAt = 0;
  var rawPostedAt = 0;
  var RAW_ACK_TIMEOUT_MS = 750;

  // Detached: this canvas is NEVER inserted into document/DOM, so capture can
  // never change what the user sees on the PC or on A in XR.
  var rawCaptureCanvas = document.createElement('canvas');
  var rawCaptureContext = rawCaptureCanvas.getContext('2d', {
    alpha: false,
    desynchronized: true,
    willReadFrequently: true
  });
  if (rawCaptureContext) {
    rawCaptureContext.imageSmoothingEnabled = true;
    rawCaptureContext.imageSmoothingQuality = 'high';
  }

  // v0.13.24 raw-transport telemetry, emitted once per second.
  var perfWindowStartedAt = performance.now();
  var perfRequestCount = 0;
  var perfRequestFailed = 0;
  var perfRequestCallMsSum = 0;
  var perfRequestCallMsMax = 0;
  var perfReadyCount = 0;
  var perfRequestToReadyMsSum = 0;
  var perfRequestToReadyMsMax = 0;
  var perfRequestIntervalCount = 0;
  var perfRequestIntervalMsSum = 0;
  var perfRequestIntervalMsMax = 0;
  var perfLastRequestAt = 0;
  var perfDrawCount = 0;
  var perfDrawMsSum = 0;
  var perfDrawMsMax = 0;
  var perfReadbackCount = 0;
  var perfReadbackMsSum = 0;
  var perfReadbackMsMax = 0;
  var perfPostCount = 0;
  var perfPostMsSum = 0;
  var perfPostMsMax = 0;
  var perfRawBytesSum = 0;
  var perfRawBytesMax = 0;
  var perfAckCount = 0;
  var perfAckMsSum = 0;
  var perfAckMsMax = 0;
  var perfCycleCount = 0;
  var perfCycleMsSum = 0;
  var perfCycleMsMax = 0;
  var perfPendingRafFrames = 0;
  var perfInFlightRafFrames = 0;
  var perfIntervalWaitRafFrames = 0;
  var perfPendingPolls = 0;
  var perfAckTimeouts = 0;
  var perfLastEyeWidth = 0;
  var perfLastEyeHeight = 0;

  function emitPerformanceSample() {
    var now = performance.now();
    var elapsed = Math.max(1, now - perfWindowStartedAt);
    var sample = {
      kind: 'js-stereo-raw-arraybuffer',
      elapsedMs: elapsed,
      targetIntervalMs: CAPTURE_INTERVAL_MS,
      targetFps: 1000 / CAPTURE_INTERVAL_MS,
      requestCount: perfRequestCount,
      requestFailed: perfRequestFailed,
      actualRequestFps: perfRequestCount * 1000 / elapsed,
      avgRequestCallMs: perfRequestCount ? perfRequestCallMsSum / perfRequestCount : 0,
      maxRequestCallMs: perfRequestCallMsMax,
      readyCount: perfReadyCount,
      actualReadyFps: perfReadyCount * 1000 / elapsed,
      avgRequestToReadyMs: perfReadyCount ? perfRequestToReadyMsSum / perfReadyCount : 0,
      maxRequestToReadyMs: perfRequestToReadyMsMax,
      avgRequestIntervalMs: perfRequestIntervalCount ? perfRequestIntervalMsSum / perfRequestIntervalCount : 0,
      maxRequestIntervalMs: perfRequestIntervalMsMax,
      rawFramesPosted: perfPostCount,
      actualRawPostFps: perfPostCount * 1000 / elapsed,
      avgDrawMs: perfDrawCount ? perfDrawMsSum / perfDrawCount : 0,
      maxDrawMs: perfDrawMsMax,
      avgReadbackMs: perfReadbackCount ? perfReadbackMsSum / perfReadbackCount : 0,
      maxReadbackMs: perfReadbackMsMax,
      avgPostMessageMs: perfPostCount ? perfPostMsSum / perfPostCount : 0,
      maxPostMessageMs: perfPostMsMax,
      avgRawBytes: perfPostCount ? perfRawBytesSum / perfPostCount : 0,
      maxRawBytes: perfRawBytesMax,
      ackCount: perfAckCount,
      actualAckFps: perfAckCount * 1000 / elapsed,
      avgHostAckMs: perfAckCount ? perfAckMsSum / perfAckCount : 0,
      maxHostAckMs: perfAckMsMax,
      avgCycleMs: perfCycleCount ? perfCycleMsSum / perfCycleCount : 0,
      maxCycleMs: perfCycleMsMax,
      pendingRafFrames: perfPendingRafFrames,
      inFlightRafFrames: perfInFlightRafFrames,
      intervalWaitRafFrames: perfIntervalWaitRafFrames,
      pendingPolls: perfPendingPolls,
      ackTimeouts: perfAckTimeouts,
      rawInFlight: !!rawInFlight,
      rawInFlightSerial: rawInFlightSerial,
      eyeWidth: perfLastEyeWidth,
      eyeHeight: perfLastEyeHeight
    };
    bridge('performanceSample', JSON.stringify(sample));

    perfWindowStartedAt = now;
    perfRequestCount = 0;
    perfRequestFailed = 0;
    perfRequestCallMsSum = 0;
    perfRequestCallMsMax = 0;
    perfReadyCount = 0;
    perfRequestToReadyMsSum = 0;
    perfRequestToReadyMsMax = 0;
    perfRequestIntervalCount = 0;
    perfRequestIntervalMsSum = 0;
    perfRequestIntervalMsMax = 0;
    perfDrawCount = 0;
    perfDrawMsSum = 0;
    perfDrawMsMax = 0;
    perfReadbackCount = 0;
    perfReadbackMsSum = 0;
    perfReadbackMsMax = 0;
    perfPostCount = 0;
    perfPostMsSum = 0;
    perfPostMsMax = 0;
    perfRawBytesSum = 0;
    perfRawBytesMax = 0;
    perfAckCount = 0;
    perfAckMsSum = 0;
    perfAckMsMax = 0;
    perfCycleCount = 0;
    perfCycleMsSum = 0;
    perfCycleMsMax = 0;
    perfPendingRafFrames = 0;
    perfInFlightRafFrames = 0;
    perfIntervalWaitRafFrames = 0;
    perfPendingPolls = 0;
    perfAckTimeouts = 0;
  }
  setInterval(emitPerformanceSample, 1000);

'''
s = s[:state_start] + raw_state + s[bridge_start:]

# Replace the old DataURL bridge helper with a native binary-post helper.
s = sub_once(
    r"  function bridgeStereoEyes\(leftDataUrl, rightDataUrl\) \{.*?\n  \}\n\n",
    r'''  function postHostMessage(message) {
    try {
      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
        window.CefSharp.PostMessage(message);
        return true;
      }
      if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
        window.cefSharp.postMessage(message);
        return true;
      }
    } catch (error) {
      reportRuntimeError(
        'CEF binary post hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
    }
    return false;
  }

''',
    s,
    'v0.13.24 JS bridgeStereoEyes replacement',
    re.S)

# Reset now also drops only our logical in-flight gate. It never mutates A/DOM.
s = sub_once(
    r"  function resetStereoRequestState\(\) \{.*?\n  \}\n",
    r'''  function resetStereoRequestState() {
    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;
    lastDeliveredStereoSerial = -1;
    nextStereoRequestAt = 0;
    rawInFlight = false;
    rawInFlightSerial = -1;
    rawInFlightRequestedAt = 0;
    rawPostedAt = 0;
  }
''',
    s,
    'v0.13.24 JS reset replacement',
    re.S)

# Single SBS capture canvas instead of two JPEG canvases.
s = sub_once(
    r"  function ensureCaptureCanvasSize\(width, height\) \{.*?\n  \}\n",
    r'''  function ensureRawCaptureCanvasSize(eyeWidth, eyeHeight) {
    var sbsWidth = Math.max(2, eyeWidth * 2);
    if (rawCaptureCanvas.width !== sbsWidth) rawCaptureCanvas.width = sbsWidth;
    if (rawCaptureCanvas.height !== eyeHeight) rawCaptureCanvas.height = eyeHeight;
    if (rawCaptureContext) {
      rawCaptureContext.imageSmoothingEnabled = true;
      rawCaptureContext.imageSmoothingQuality = 'high';
    }
  }
''',
    s,
    'v0.13.24 JS capture canvas replacement',
    re.S)

# Remove JPEG encoder completely.
s = sub_once(
    r"  function canvasToDataUrlAsync\(canvas\) \{.*?\n  \}\n\n",
    '',
    s,
    'v0.13.24 JS JPEG encoder removal',
    re.S)

# Replace the whole JPEG capture function. Capture is synchronous up to
# PostMessage; completion is gated by the small host ACK callback below.
s = sub_once(
    r"  function beginAsyncStereoCapture\(serial, requestedAt\) \{.*?\n  \}\n\n(?=  function pollRequestedStereoPair)",
    r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!rawCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(sourceWidth, sourceHeight, geometry.rect);
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;
      ensureRawCaptureCanvasSize(eyeWidth, eyeHeight);

      var drawStartedAt = performance.now();
      rawCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      rawCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        eyeWidth, 0, eyeWidth, eyeHeight
      );
      var drawMs = Math.max(0, performance.now() - drawStartedAt);
      perfDrawCount++;
      perfDrawMsSum += drawMs;
      perfDrawMsMax = Math.max(perfDrawMsMax, drawMs);

      var readStartedAt = performance.now();
      var image = rawCaptureContext.getImageData(0, 0, eyeWidth * 2, eyeHeight);
      var readMs = Math.max(0, performance.now() - readStartedAt);
      perfReadbackCount++;
      perfReadbackMsSum += readMs;
      perfReadbackMsMax = Math.max(perfReadbackMsMax, readMs);

      var expectedBytes = eyeWidth * 2 * eyeHeight * 4;
      if (!image || !image.data || image.data.byteLength !== expectedBytes) {
        throw new Error('raw SBS byte length uyuşmuyor');
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      var postStartedAt = performance.now();
      var posted = postHostMessage({
        type: 'stereoRawSbs',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: eyeWidth * 2 * 4,
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

      perfPostCount++;
      perfPostMsSum += postMs;
      perfPostMsMax = Math.max(perfPostMsMax, postMs);
      perfRawBytesSum += expectedBytes;
      perfRawBytesMax = Math.max(perfRawBytesMax, expectedBytes);
      perfLastEyeWidth = eyeWidth;
      perfLastEyeHeight = eyeHeight;
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
        'Raw stereo capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }

  // Called by the C# host after the ArrayBuffer has actually been copied into
  // the SBS memory mapping. This prevents CEF IPC from ever accumulating raw
  // stereo frames behind a slow consumer.
  window.ggqRawStereoAck = function (serial, ok) {
    serial = Number(serial);
    if (!rawInFlight || !isFinite(serial) || serial !== rawInFlightSerial) {
      return false;
    }

    var now = performance.now();
    var ackMs = rawPostedAt ? Math.max(0, now - rawPostedAt) : 0;
    var cycleMs = rawInFlightRequestedAt ? Math.max(0, now - rawInFlightRequestedAt) : 0;
    perfAckCount++;
    perfAckMsSum += ackMs;
    perfAckMsMax = Math.max(perfAckMsMax, ackMs);
    perfCycleCount++;
    perfCycleMsSum += cycleMs;
    perfCycleMsMax = Math.max(perfCycleMsMax, cycleMs);

    if (ok !== false) lastDeliveredStereoSerial = serial;
    var requestBase = rawInFlightRequestedAt;
    rawInFlight = false;
    rawInFlightSerial = -1;
    rawInFlightRequestedAt = 0;
    rawPostedAt = 0;
    nextStereoRequestAt = requestBase && cycleMs < CAPTURE_INTERVAL_MS
      ? requestBase + CAPTURE_INTERVAL_MS
      : now + 1;
    return true;
  };

''',
    s,
    'v0.13.24 JS raw capture replacement',
    re.S)

# Polling still waits for the Exp46 stereo renderer serial, then captures raw.
s = s.replace('return beginAsyncStereoCapture(serial, requestedAt);',
              'return beginRawStereoCapture(serial, requestedAt);', 1)

# Replace the capture loop so large binary messages are ACK-gated with a timeout.
s = sub_once(
    r"  function captureLoop\(now\) \{.*?\n  \}\n\n(?=  if \(window\.ResizeObserver\))",
    r'''  function captureLoop(now) {
    if (rawInFlight) {
      perfInFlightRafFrames++;
      if (rawPostedAt > 0 && now - rawPostedAt > RAW_ACK_TIMEOUT_MS) {
        perfAckTimeouts++;
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
      perfPendingRafFrames++;
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
      perfIntervalWaitRafFrames++;
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!requestStereoPair(now)) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }

    requestAnimationFrame(captureLoop);
  }

''',
    s,
    'v0.13.24 JS capture loop replacement',
    re.S)

# requestStereoPair from v0.13.22 already measures request timing. poll function
# also measures request->ready; remove the old encodingInFlight gate only.
s = s.replace('if (pendingStereoSerial === null || encodingInFlight) return false;',
              'if (pendingStereoSerial === null || rawInFlight) return false;', 1)

# Hard safety checks: this build must not retain any JPEG/DataURL or v0.13.23
# visible-compositor capture mechanism.
for forbidden in (
    'canvasToDataUrlAsync', 'bridgeStereoEyes', "'image/jpeg'", '"image/jpeg"',
    'stereoGpuPhase', 'ggq-pc-raw-left-eye-overlay', 'showLeftOverlay'
):
    if forbidden in s:
        raise SystemExit(f'v0.13.24 forbidden JS transport remains: {forbidden}')

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) C# bridge: fast-path CefSharp ArrayBuffer -> byte[] before JSON serialization.
#    Leave the old decode methods compiled but unreachable for maximum stability.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

# The legacy JS bridge entry is removed so no JPEG eye-pair can be sent.
s = sub_once(
    r"\s*updateStereoEyes: function \(left, right\) \{\n\s*post\(\{ type: 'stereoEyes', left: String\(left \|\| ''\), right: String\(right \|\| ''\) \}\);\n\s*\},\n",
    '\n',
    s,
    'v0.13.24 QuestBridge JPEG method removal')

# Fast path before System.Text.Json: otherwise byte[] would become Base64 again.
handler_marker = '''        try
        {
            var json = JsonSerializer.Serialize(e.Message);'''
req(s, handler_marker, 'v0.13.24 JavascriptMessageReceived marker missing')
s = s.replace(handler_marker, '''        try
        {
            if (TryHandleRawStereoMessage(e.Message)) return;

            var json = JsonSerializer.Serialize(e.Message);''', 1)

# Remove the reachable stereoEyes switch arm. Dead decoder helpers remain untouched.
s = sub_once(
    r'''                case "stereoEyes":\n.*?                    break;\n(?=                case "performanceSample":|                case "runtimeError":)''',
    '',
    s,
    'v0.13.24 stereoEyes switch removal',
    re.S)

layout_marker = '    private void HandleStereoLayout(string? payload)\n'
req(s, layout_marker, 'v0.13.24 HandleStereoLayout marker missing')

raw_handler = r'''    private bool TryHandleRawStereoMessage(object? message)
    {
        if (message is not IDictionary<string, object> values ||
            !values.TryGetValue("type", out var typeObject) ||
            !string.Equals(typeObject?.ToString(), "stereoRawSbs", StringComparison.Ordinal))
        {
            return false;
        }

        long serial = -1;
        try
        {
            if (!values.TryGetValue("serial", out var serialObject) ||
                !values.TryGetValue("eyeWidth", out var widthObject) ||
                !values.TryGetValue("eyeHeight", out var heightObject) ||
                !values.TryGetValue("stride", out var strideObject) ||
                !values.TryGetValue("rgba", out var rgbaObject) ||
                rgbaObject is not byte[] rgba)
            {
                throw new InvalidDataException("CEF raw stereo mesajı eksik.");
            }

            serial = Convert.ToInt64(serialObject);
            var eyeWidth = Convert.ToInt32(widthObject);
            var eyeHeight = Convert.ToInt32(heightObject);
            var stride = Convert.ToInt32(strideObject);
            HandleRawStereoSbs(rgba, eyeWidth, eyeHeight, stride, serial);
        }
        catch (Exception ex)
        {
            _cefPageText = "Raw stereo IPC: " + ex.Message;
            BeginInvokeSafe(UpdateWindowTitle);
            AckRawStereo(serial, false);
        }
        return true;
    }

    private void HandleRawStereoSbs(
        byte[] rgba,
        int eyeWidth,
        int eyeHeight,
        int stride,
        long serial)
    {
        if (_closing || _stereoUiSuspended)
        {
            AckRawStereo(serial, false);
            return;
        }

        var expectedStride = checked(eyeWidth * 2 * 4);
        var expectedBytes = checked(expectedStride * eyeHeight);
        if (eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > 2048 || eyeHeight > 2048 ||
            stride != expectedStride || rgba.Length != expectedBytes)
        {
            throw new InvalidDataException(
                $"Raw SBS boyutu geçersiz: {eyeWidth}x{eyeHeight}, stride={stride}, bytes={rgba.Length}");
        }

        bool active;
        Rectangle rect;
        Rectangle[] overlays;
        Size clientSize;
        lock (_geometryLock)
        {
            active = _stereo3DActive;
            rect = _stereo3DRenderBounds;
            overlays = _stereoUiOverlayBounds;
            clientSize = _browserSize;
        }

        if (!active || rect.Width < 2 || rect.Height < 2 ||
            clientSize.Width < 2 || clientSize.Height < 2)
        {
            AckRawStereo(serial, false);
            return;
        }

        var frame = Interlocked.Increment(ref _stereoFrameNumber);
        var publishWatch = System.Diagnostics.Stopwatch.StartNew();
        _sharedStereoFrames.WriteRawSbsRgba(
            rgba,
            eyeWidth,
            eyeHeight,
            stride,
            rect,
            clientSize,
            overlays,
            frame);
        publishWatch.Stop();
        _performanceTelemetry.RecordRawFrame(
            rgba.Length,
            publishWatch.Elapsed.TotalMilliseconds,
            eyeWidth,
            eyeHeight,
            stride);

        if ((frame % 30) == 0) BeginInvokeSafe(UpdateWindowTitle);
        AckRawStereo(serial, true);
    }

    private void AckRawStereo(long serial, bool ok)
    {
        var browser = _browser;
        if (browser is null || _closing || serial < 0) return;
        try
        {
            var okText = ok ? "true" : "false";
            _ = browser.EvaluateScriptAsync(
                $"window.ggqRawStereoAck && window.ggqRawStereoAck({serial}, {okText});");
        }
        catch { }
    }

'''
s = s.replace(layout_marker, raw_handler + layout_marker, 1)

# Version/cache labels.
s = re.sub(r'(pc-stereo-layout\.js\?v=)[^"\']+',
           r'\g<1>0.13.24-raw-arraybuffer', s, count=1)
s = s.replace('GeoGebraForQuest PC v0.13.22', 'GeoGebraForQuest PC v0.13.24')
s = s.replace('v0.13.22', 'v0.13.24')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) SBS writer: add raw RGBA write and a pixel-format marker at header offset
#    116 (unused after the three v0.13.18 UI-overlay rectangles at 68..115).
#    1 = BGRA legacy Bitmap path, 2 = RGBA raw ArrayBuffer path.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')

# Constructor initial state.
ctor = '        _view.Write(64, 0);\n        _view.Flush();'
req(s, ctor, 'v0.13.24 SBS constructor overlay marker missing')
s = s.replace(ctor, '        _view.Write(64, 0);\n        _view.Write(116, 0);\n        _view.Flush();', 1)

# Legacy Bitmap writer explicitly marks BGRA.
legacy = '''                for (var i = 0; i < MaxUiOverlayRects; i++)
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

                WriteSbsBitmap'''
req(s, legacy, 'v0.13.24 SBS legacy overlay block missing')
s = s.replace(legacy, legacy.replace('\n\n                WriteSbsBitmap',
                                    '\n                _view.Write(116, 1);\n\n                WriteSbsBitmap'), 1)

inactive_marker = '            _view.Write(64, 0);\n\n            Thread.MemoryBarrier();'
req(s, inactive_marker, 'v0.13.24 SBS inactive marker missing')
s = s.replace(inactive_marker,
              '            _view.Write(64, 0);\n            _view.Write(116, 0);\n\n            Thread.MemoryBarrier();', 1)

set_inactive_marker = '    public void SetInactive(Rectangle stereoPanelClientBounds, Size applicationClientSize)\n'
req(s, set_inactive_marker, 'v0.13.24 SBS raw insertion marker missing')

raw_writer = r'''    public void WriteRawSbsRgba(
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
            throw new ArgumentException("Raw SBS stride must be tightly packed RGBA.");
        var totalBytes = checked(sbsStride * eyeHeight);
        if (rgbaSbs.Length != totalBytes)
            throw new ArgumentException("Raw SBS RGBA byte length mismatch.");

        lock (_sync)
        {
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

            // v0.13.24 raw Canvas ImageData is RGBA, not Bitmap BGRA.
            _view.Write(116, 2);
            _view.WriteArray(SbsOffset, rgbaSbs, 0, totalBytes);
            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s.replace(set_inactive_marker, raw_writer + set_inactive_marker, 1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) XR reader/texture: understand the pixel-format marker. This keeps legacy
#    BGRA compatibility and lets the new raw path upload RGBA with zero channel
#    conversion on the C# side.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
s = p.read_text(encoding='utf-8')

frame_marker = '    std::int32_t frameNumber{};\n'
req(s, frame_marker, 'v0.13.24 XR SbsSnapshot frame marker missing')
s = s.replace(frame_marker, frame_marker + '    int pixelFormat{1}; // 1=BGRA, 2=RGBA\n', 1)

read_marker = '            candidate.frameNumber = ReadI32(view_, 56);\n'
req(s, read_marker, 'v0.13.24 XR pixel format read marker missing')
s = s.replace(read_marker, read_marker + '''            candidate.pixelFormat = ReadI32(view_, 116);
            if (candidate.pixelFormat == 0) candidate.pixelFormat = 1;
''', 1)

valid_marker = '                candidate.sbsStride == candidate.eyeWidth * 2 * 4;'
req(s, valid_marker, 'v0.13.24 XR SBS validity marker missing')
s = s.replace(valid_marker,
              '                candidate.sbsStride == candidate.eyeWidth * 2 * 4 &&\n'
              '                (candidate.pixelFormat == 1 || candidate.pixelFormat == 2);', 1)

# SourceTexture gets an explicit pixel format and recreates only if it changes.
s = s.replace('        int rowPitch) {\n', '        int rowPitch,\n        int pixelFormat) {\n', 1)
source_if = '        if (!texture_ || width != width_ || height != height_) {\n'
req(s, source_if, 'v0.13.24 SourceTexture recreate marker missing')
s = s.replace(source_if, '''        const DXGI_FORMAT desiredFormat = pixelFormat == 2
            ? DXGI_FORMAT_R8G8B8A8_UNORM
            : DXGI_FORMAT_B8G8R8A8_UNORM;
        if (!texture_ || width != width_ || height != height_ || desiredFormat != format_) {
''', 1)
s = s.replace('            desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;\n',
              '            desc.Format = desiredFormat;\n', 1)
width_marker = '            width_ = width;\n            height_ = height;\n'
req(s, width_marker, 'v0.13.24 SourceTexture dimensions marker missing')
s = s.replace(width_marker, width_marker + '            format_ = desiredFormat;\n', 1)
reset_marker = '        width_ = 0;\n        height_ = 0;\n'
req(s, reset_marker, 'v0.13.24 SourceTexture Reset marker missing')
s = s.replace(reset_marker, reset_marker + '        format_ = DXGI_FORMAT_UNKNOWN;\n', 1)
member_marker = '    int width_{};\n    int height_{};\n};\n\nclass SharedGpuTextureConsumer'
req(s, member_marker, 'v0.13.24 SourceTexture member marker missing')
s = s.replace(member_marker,
              '    int width_{};\n    int height_{};\n    DXGI_FORMAT format_{DXGI_FORMAT_UNKNOWN};\n};\n\nclass SharedGpuTextureConsumer', 1)
p.write_text(s, encoding='utf-8')

# Add pixel format to the one SBS upload call in native XR.
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')
pos = s.find('sbsTexture_.Upload(')
if pos < 0:
    raise SystemExit('v0.13.24 XR SBS upload call missing')
tail = '                    sbsFrame_.sbsStride);'
tail_pos = s.find(tail, pos)
if tail_pos < 0:
    raise SystemExit('v0.13.24 XR SBS upload tail missing')
s = s[:tail_pos] + '''                    sbsFrame_.sbsStride,
                    sbsFrame_.pixelFormat);''' + s[tail_pos + len(tail):]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) Host telemetry: keep all v0.13.22 legacy columns for comparison and append
#    raw-binary frame/publish measurements.
# ---------------------------------------------------------------------------
Path('pc/PerformanceTelemetry.cs').write_text(r'''using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace GeoGebraForQuest.PC;

internal sealed class HostPerformanceTelemetry : IDisposable
{
    private readonly object _sync = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly Process _process = Process.GetCurrentProcess();
    private readonly StreamWriter _host;
    private readonly StreamWriter _js;

    private long _lastWriteMs;
    private TimeSpan _lastCpu;
    private long _received;
    private long _replaced;
    private long _decoded;
    private long _published;
    private double _decodeMsSum;
    private double _decodeMsMax;
    private double _publishMsSum;
    private double _publishMsMax;
    private int _eyeWidth;
    private int _eyeHeight;
    private long _lastLeftChars;
    private long _lastRightChars;

    private long _rawFrames;
    private long _rawBytes;
    private double _rawPublishMsSum;
    private double _rawPublishMsMax;
    private int _rawEyeWidth;
    private int _rawEyeHeight;
    private int _rawStride;
    private bool _disposed;

    public HostPerformanceTelemetry()
    {
        var hostPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.Host.csv");
        var jsPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.JS.jsonl");
        _host = new StreamWriter(new FileStream(hostPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite, 4096, FileOptions.SequentialScan), new UTF8Encoding(false));
        _js = new StreamWriter(new FileStream(jsPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite, 4096, FileOptions.SequentialScan), new UTF8Encoding(false));
        _host.WriteLine(
            "elapsed_s,utc,received_pairs,pending_replaced,decoded_pairs,published_pairs," +
            "avg_decode_ms,max_decode_ms,avg_publish_ms,max_publish_ms," +
            "eye_width,eye_height,left_dataurl_chars,right_dataurl_chars," +
            "raw_frames,raw_mb,avg_raw_publish_ms,max_raw_publish_ms," +
            "raw_eye_width,raw_eye_height,raw_stride," +
            "working_set_mb,private_mb,gc_heap_mb,cpu_percent");
        _host.Flush();
        _lastCpu = _process.TotalProcessorTime;
    }

    public void RecordReceived(int leftChars, int rightChars, bool replaced)
    {
        lock (_sync)
        {
            _received++;
            if (replaced) _replaced++;
            _lastLeftChars = leftChars;
            _lastRightChars = rightChars;
            MaybeWriteLocked();
        }
    }

    public void RecordDecoded(double ms, int width, int height)
    {
        lock (_sync)
        {
            _decoded++;
            _decodeMsSum += ms;
            _decodeMsMax = Math.Max(_decodeMsMax, ms);
            _eyeWidth = width;
            _eyeHeight = height;
            MaybeWriteLocked();
        }
    }

    public void RecordPublished(double ms)
    {
        lock (_sync)
        {
            _published++;
            _publishMsSum += ms;
            _publishMsMax = Math.Max(_publishMsMax, ms);
            MaybeWriteLocked();
        }
    }

    public void RecordRawFrame(int bytes, double publishMs, int eyeWidth, int eyeHeight, int stride)
    {
        lock (_sync)
        {
            _rawFrames++;
            _rawBytes += bytes;
            _rawPublishMsSum += publishMs;
            _rawPublishMsMax = Math.Max(_rawPublishMsMax, publishMs);
            _rawEyeWidth = eyeWidth;
            _rawEyeHeight = eyeHeight;
            _rawStride = stride;
            MaybeWriteLocked();
        }
    }

    public void RecordJsSample(string json)
    {
        lock (_sync)
        {
            if (_disposed) return;
            _js.Write('{');
            _js.Write("\"hostElapsedMs\":");
            _js.Write(_clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture));
            _js.Write(",\"sample\":");
            _js.Write(string.IsNullOrWhiteSpace(json) ? "null" : json);
            _js.WriteLine('}');
            _js.Flush();
            MaybeWriteLocked();
        }
    }

    private void MaybeWriteLocked(bool force = false)
    {
        if (_disposed) return;
        var nowMs = _clock.ElapsedMilliseconds;
        if (!force && nowMs - _lastWriteMs < 1000) return;

        _process.Refresh();
        var cpuNow = _process.TotalProcessorTime;
        var intervalMs = Math.Max(1, nowMs - _lastWriteMs);
        var cpuMs = (cpuNow - _lastCpu).TotalMilliseconds;
        var cpuPercent = 100.0 * cpuMs / intervalMs / Math.Max(1, Environment.ProcessorCount);
        var avgDecode = _decoded > 0 ? _decodeMsSum / _decoded : 0.0;
        var avgPublish = _published > 0 ? _publishMsSum / _published : 0.0;
        var avgRawPublish = _rawFrames > 0 ? _rawPublishMsSum / _rawFrames : 0.0;
        static string F(double value) => value.ToString("0.###", CultureInfo.InvariantCulture);

        _host.Write(F(nowMs / 1000.0)); _host.Write(',');
        _host.Write(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)); _host.Write(',');
        _host.Write(_received); _host.Write(','); _host.Write(_replaced); _host.Write(',');
        _host.Write(_decoded); _host.Write(','); _host.Write(_published); _host.Write(',');
        _host.Write(F(avgDecode)); _host.Write(','); _host.Write(F(_decodeMsMax)); _host.Write(',');
        _host.Write(F(avgPublish)); _host.Write(','); _host.Write(F(_publishMsMax)); _host.Write(',');
        _host.Write(_eyeWidth); _host.Write(','); _host.Write(_eyeHeight); _host.Write(',');
        _host.Write(_lastLeftChars); _host.Write(','); _host.Write(_lastRightChars); _host.Write(',');
        _host.Write(_rawFrames); _host.Write(','); _host.Write(F(_rawBytes / 1048576.0)); _host.Write(',');
        _host.Write(F(avgRawPublish)); _host.Write(','); _host.Write(F(_rawPublishMsMax)); _host.Write(',');
        _host.Write(_rawEyeWidth); _host.Write(','); _host.Write(_rawEyeHeight); _host.Write(','); _host.Write(_rawStride); _host.Write(',');
        _host.Write(F(_process.WorkingSet64 / 1048576.0)); _host.Write(',');
        _host.Write(F(_process.PrivateMemorySize64 / 1048576.0)); _host.Write(',');
        _host.Write(F(GC.GetTotalMemory(false) / 1048576.0)); _host.Write(',');
        _host.WriteLine(F(cpuPercent));
        _host.Flush();

        _lastWriteMs = nowMs;
        _lastCpu = cpuNow;
        _received = _replaced = _decoded = _published = 0;
        _decodeMsSum = _decodeMsMax = _publishMsSum = _publishMsMax = 0;
        _rawFrames = 0;
        _rawBytes = 0;
        _rawPublishMsSum = _rawPublishMsMax = 0;
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            MaybeWriteLocked(force: true);
            _disposed = true;
            _host.Dispose();
            _js.Dispose();
        }
    }
}
''', encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) Version/package labels.
# ---------------------------------------------------------------------------
for file in ('pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.24</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.24.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.24.0</AssemblyVersion>', s, count=1)
    else:
        s = s.replace('GeoGebraForQuest-PC-v0.13.22-pipeline-latency-telemetry-win-x64',
                      'GeoGebraForQuest-PC-v0.13.24-raw-arraybuffer-win-x64')
        s = s.replace('0.13.22-pipeline-latency-telemetry', '0.13.24-raw-arraybuffer')
        s = s.replace(r'0\.13\.22-pipeline-latency-telemetry', r'0\.13\.24-raw-arraybuffer')
        s = s.replace('v0.13.22', 'v0.13.24')
        s = s.replace(r'v0\.13\.22', r'v0\.13\.24')
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.24 raw ArrayBuffer transport patch applied')
