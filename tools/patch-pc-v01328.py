from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.28
#
# Exact A_L / A_R architecture:
#   * A is used only as the common full-application/UI base image.
#   * BOTH real GeoGebra stereo eye images are transported: true L and true R.
#   * XR GPU builds:
#       A_L = A with the 3D viewport replaced by true L
#       A_R = A with the 3D viewport replaced by true R
#   * The two complete application images are composed as FULL_SBS = A_L | A_R.
#   * Quest/OpenXR draws one application panel; left eye samples the left half,
#     right eye samples the right half.
#
# This deliberately removes the v0.13.27 assumption that ordinary A already
# contains the correct R projection. UI is still rendered only once by CEF.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) JavaScript: transport BOTH proven renderer eye canvases as one raw SBS
#    ArrayBuffer. No JPEG/Base64, no visible DOM overlay.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

s = s.replace("kind: 'js-al-ar-left-raw'", "kind: 'js-al-ar-pair-raw'", 1)

start = s.find('  function ensureRawCaptureCanvasSize(eyeWidth, eyeHeight) {')
end = s.find('\n  }\n', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.28 ensureRawCaptureCanvasSize block missing')
end += len('\n  }\n')
new_size = r'''  function ensureRawCaptureCanvasSize(eyeWidth, eyeHeight) {
    var sbsWidth = eyeWidth * 2;
    if (rawCaptureCanvas.width !== sbsWidth) rawCaptureCanvas.width = sbsWidth;
    if (rawCaptureCanvas.height !== eyeHeight) rawCaptureCanvas.height = eyeHeight;
    if (rawCaptureContext) {
      rawCaptureContext.imageSmoothingEnabled = true;
      rawCaptureContext.imageSmoothingQuality = 'high';
    }
  }
'''
s = s[:start] + new_size + s[end:]

capture_start = s.find('  function beginRawStereoCapture(serial, requestedAt) {')
capture_end = s.find('\n  // Called by the C# host after the ArrayBuffer', capture_start)
if capture_start < 0 or capture_end < 0:
    raise SystemExit('v0.13.28 beginRawStereoCapture block missing')

new_capture = r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!rawCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    // These are the exact proven Exp46/GeoGebra LEFT_EYE and RIGHT_EYE canvases
    // used by the last working stereo checkpoint. We transport both so the XR
    // compositor never has to infer an eye from A.
    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left || !eyes.right) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width | 0, eyes.right.width | 0);
      var sourceHeight = Math.min(eyes.left.height | 0, eyes.right.height | 0);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(sourceWidth, sourceHeight, geometry.rect);
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;
      ensureRawCaptureCanvasSize(eyeWidth, eyeHeight);

      var drawStartedAt = performance.now();
      rawCaptureContext.setTransform(1, 0, 0, 1, 0, 0);
      rawCaptureContext.clearRect(0, 0, eyeWidth * 2, eyeHeight);
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

      var stride = eyeWidth * 2 * 4;
      var expectedBytes = stride * eyeHeight;
      if (!image || !image.data || image.data.byteLength !== expectedBytes) {
        throw new Error('raw TRUE L/R byte length uyuşmuyor');
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      var postStartedAt = performance.now();
      var posted = postHostMessage({
        type: 'stereoRawPair',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: stride,
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
        'Raw TRUE L/R capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }
'''
s = s[:capture_start] + new_capture + s[capture_end:]

if "type: 'stereoRawLeft'" in s:
    raise SystemExit('v0.13.28 old LEFT-only IPC still reachable')
if "type: 'stereoRawPair'" not in s:
    raise SystemExit('v0.13.28 pair IPC missing')

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Host: accept raw true L|R pair.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

start = s.find('    private bool TryHandleRawStereoMessage(object? message)')
end = s.find('    private void AckRawStereo(long serial, bool ok)', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.28 host raw handler block missing')

new_host = r'''    private bool TryHandleRawStereoMessage(object? message)
    {
        if (message is not IDictionary<string, object> values ||
            !values.TryGetValue("type", out var typeObject) ||
            !string.Equals(typeObject?.ToString(), "stereoRawPair", StringComparison.Ordinal))
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
                throw new InvalidDataException("CEF raw TRUE L/R mesajı eksik.");
            }

            serial = Convert.ToInt64(serialObject);
            var eyeWidth = Convert.ToInt32(widthObject);
            var eyeHeight = Convert.ToInt32(heightObject);
            var stride = Convert.ToInt32(strideObject);
            HandleRawStereoPair(rgba, eyeWidth, eyeHeight, stride, serial);
        }
        catch (Exception ex)
        {
            _cefPageText = "Raw TRUE L/R IPC: " + ex.Message;
            BeginInvokeSafe(UpdateWindowTitle);
            AckRawStereo(serial, false);
        }
        return true;
    }

    private void HandleRawStereoPair(
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
                $"Raw TRUE L/R boyutu geçersiz: {eyeWidth}x{eyeHeight}, stride={stride}, bytes={rgba.Length}");
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
        _sharedStereoFrames.WriteRawStereoPairRgba(
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

'''
s = s[:start] + new_host + s[end:]

s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.28-true-al-ar-full-sbs',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.27', 'GeoGebraForQuest PC v0.13.28')

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Shared memory: raw TRUE L|R pair, pixelFormat=2 (raw RGBA SBS).
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')

method_start = s.find('    public void WriteRawLeftRgba(')
method_end = s.find('    public void SetInactive(', method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit('v0.13.28 WriteRawLeftRgba block missing')

new_writer = r'''    public void WriteRawStereoPairRgba(
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

            // 2 = raw RGBA full stereo SBS: [true L | true R].
            _view.Write(116, 2);
            _view.WriteArray(HeaderSize, rgbaSbs, 0, totalBytes);

            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s[:method_start] + new_writer + s[method_end:]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) XR GPU composer: build BOTH full images from A + true L/R 3D patches.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

s = s.replace(
    '        ID3D11ShaderResourceView* left3D,\n        const SbsSnapshot* leftFrame) {',
    '        ID3D11ShaderResourceView* stereoPair,\n        const SbsSnapshot* pairFrame) {',
    1)

block_start = s.find('        const bool leftReady = left3D && leftFrame && leftFrame->active &&')
block_end = s.find('\n        ID3D11ShaderResourceView* nullSrv[] = {nullptr};', block_start)
if block_start < 0 or block_end < 0:
    raise SystemExit('v0.13.28 FullSbs true-eye patch block missing')

new_pair_block = r'''        const bool pairReady = stereoPair && pairFrame && pairFrame->active &&
            pairFrame->pixelFormat == 2 &&
            pairFrame->clientWidth > 1 && pairFrame->clientHeight > 1 &&
            pairFrame->panelWidth > 1 && pairFrame->panelHeight > 1;

        if (pairReady) {
            const float cw = static_cast<float>(pairFrame->clientWidth);
            const float ch = static_cast<float>(pairFrame->clientHeight);
            const float sx = static_cast<float>(fullWidth) / cw;
            const float sy = static_cast<float>(fullHeight) / ch;

            const float panelL = std::clamp(pairFrame->panelLeft * sx, 0.0f, static_cast<float>(fullWidth));
            const float panelT = std::clamp(pairFrame->panelTop * sy, 0.0f, static_cast<float>(fullHeight));
            const float panelR = std::clamp(
                (pairFrame->panelLeft + pairFrame->panelWidth) * sx,
                0.0f, static_cast<float>(fullWidth));
            const float panelB = std::clamp(
                (pairFrame->panelTop + pairFrame->panelHeight) * sy,
                0.0f, static_cast<float>(fullHeight));

            if (panelR > panelL + 1.0f && panelB > panelT + 1.0f) {
                // A_L: replace 3D with the exact TRUE LEFT half of the proven pair.
                DrawRect(context, stereoPair,
                    panelL, panelT, panelR, panelB,
                    0.0f, 0.0f, 0.5f, 1.0f, fullWidth, fullHeight);

                // A_R: replace 3D with the exact TRUE RIGHT half of the proven pair.
                DrawRect(context, stereoPair,
                    static_cast<float>(fullWidth) + panelL,
                    panelT,
                    static_cast<float>(fullWidth) + panelR,
                    panelB,
                    0.5f, 0.0f, 1.0f, 1.0f, fullWidth, fullHeight);
            }

            // Restore GeoGebra UI/menu pixels over the 3D patch in BOTH complete
            // eye images, keeping A_L and A_R identical everywhere except 3D.
            const int overlayCount = std::clamp(
                pairFrame->uiOverlayCount, 0, kMaxUiOverlayRects);
            for (int i = 0; i < overlayCount; ++i) {
                const auto& r = pairFrame->uiOverlays[i];
                if (r.width < 2 || r.height < 2) continue;

                const float l = std::clamp(r.left * sx, 0.0f, static_cast<float>(fullWidth));
                const float t = std::clamp(r.top * sy, 0.0f, static_cast<float>(fullHeight));
                const float rr = std::clamp((r.left + r.width) * sx, 0.0f, static_cast<float>(fullWidth));
                const float bb = std::clamp((r.top + r.height) * sy, 0.0f, static_cast<float>(fullHeight));
                if (rr <= l + 1.0f || bb <= t + 1.0f) continue;

                const float u0 = l / static_cast<float>(fullWidth);
                const float v0 = t / static_cast<float>(fullHeight);
                const float u1 = rr / static_cast<float>(fullWidth);
                const float v1 = bb / static_cast<float>(fullHeight);

                DrawRect(context, fullAR,
                    l, t, rr, bb,
                    u0, v0, u1, v1, fullWidth, fullHeight);
                DrawRect(context, fullAR,
                    static_cast<float>(fullWidth) + l, t,
                    static_cast<float>(fullWidth) + rr, bb,
                    u0, v0, u1, v1, fullWidth, fullHeight);
            }
        }
'''
s = s[:block_start] + new_pair_block + s[block_end:]

s = s.replace(
    '// GGQ v0.13.27 full A_L/A_R SBS single-panel path.',
    '// GGQ v0.13.28 TRUE A_L/A_R SBS single-panel path.',
    1)
s = s.replace(
    '// A_R is the full CEF GPU image. A_L starts as the same image and receives one\n// GPU-scaled LEFT 3D patch plus the already-discovered A UI/menu overlay patches.',
    '// A is only the common UI/base image. Both complete eyes receive explicit\n// true GeoGebra L/R 3D patches before the final SBS is presented.',
    1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) XR main loop: pair format=2, upload width=2*eyeWidth, compose both true eyes.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

old = '''                    const bool leftReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 3 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        leftReady ? sbsTexture_.Srv() : nullptr,
                        leftReady ? &sbsFrame_ : nullptr);'''
req(s, old, 'v0.13.28 main LEFT-only compose block missing')
new = '''                    const bool pairReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 2 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        pairReady ? sbsTexture_.Srv() : nullptr,
                        pairReady ? &sbsFrame_ : nullptr);'''
s = s.replace(old, new, 1)

s = s.replace(
    'initialized: A_R CEF GPU + raw L -> GPU A_L|A_R full-SBS single panel',
    'initialized: A CEF GPU + raw TRUE L/R -> GPU A_L|A_R full-SBS single panel',
    1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) Version/package/build validation labels.
# ---------------------------------------------------------------------------
p = Path('pc/GeoGebraForQuest.PC.csproj')
s = p.read_text(encoding='utf-8')
s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.28</Version>', s, count=1)
s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.28.0</FileVersion>', s, count=1)
s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.28.0</AssemblyVersion>', s, count=1)
p.write_text(s, encoding='utf-8')

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace('GeoGebraForQuest-PC-v0.13.27-al-ar-full-sbs-win-x64',
              'GeoGebraForQuest-PC-v0.13.28-true-al-ar-full-sbs-win-x64')
s = s.replace('0.13.27-al-ar-full-sbs', '0.13.28-true-al-ar-full-sbs')
s = s.replace(r'0\.13\.27-al-ar-full-sbs', r'0\.13\.28-true-al-ar-full-sbs')
s = s.replace('stereoRawLeft', 'stereoRawPair')
s = s.replace('WriteRawLeftRgba', 'WriteRawStereoPairRgba')
s = s.replace('js-al-ar-left-raw', 'js-al-ar-pair-raw')
s = s.replace('16 ms LEFT-only raw cadence', '16 ms true L/R raw cadence')
s = s.replace('v0.13.27', 'v0.13.28')
s = s.replace(r'v0\.13\.27', r'v0\.13\.28')
s = s.replace('GGQ v0\\.13\\.27 full A_L/A_R SBS single-panel path',
              'GGQ v0\\.13\\.28 TRUE A_L/A_R SBS single-panel path')
p.write_text(s, encoding='utf-8')

# Final invariants.
checks = {
    'pc/pc-stereo-layout.js': ["type: 'stereoRawPair'", "kind: 'js-al-ar-pair-raw'", 'eyes.left', 'eyes.right'],
    'pc/MainFormV11.cs': ['HandleRawStereoPair', 'WriteRawStereoPairRgba'],
    'pc/StereoSharedFrameWriter.cs': ['WriteRawStereoPairRgba', '_view.Write(116, 2)'],
    'pc-xr/v11-render.hpp': ['TRUE A_L/A_R', '0.0f, 0.0f, 0.5f, 1.0f', '0.5f, 0.0f, 1.0f, 1.0f'],
    'pc-xr/main-v11.cpp': ['pairReady', 'sbsFrame_.pixelFormat == 2']
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.28 final invariant missing in {file}: {needle}')

print('GeoGebraForQuest PC v0.13.28 TRUE A_L/A_R full-SBS architecture applied')
