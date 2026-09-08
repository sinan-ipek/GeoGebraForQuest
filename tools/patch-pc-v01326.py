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
# v0.13.26 — restore the simple stereo architecture.
#
# A is already a complete GeoGebra 3D projection, so do NOT transport two eyes.
# Keep A untouched as the first eye. Ask the already-proven Exp46/GeoGebra stereo
# renderer for its alternate (RIGHT) eye and transport ONLY that eye as raw RGBA.
# XR combines:
#   LEFT  eye = untouched A / normal GeoGebra 3D viewport
#   RIGHT eye = GeoGebra alternate projection in the same 3D viewport
#
# This also cuts the CEF binary IPC payload approximately in half. The host still
# writes the existing SBS MMF format for compatibility by duplicating the received
# alternate eye into both SBS halves; XR intentionally samples B only for RIGHT.
# No visible DOM overlay, no CEF compositor phase switching, no JPEG/Base64.
# ---------------------------------------------------------------------------

# 1) JS — keep v0.13.24 request/serial mechanism, but capture only GeoGebra's
# alternate/right eye canvas after the requested stereo render completes.
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

s = sub_once(
    r"  function beginRawStereoCapture\(serial, requestedAt\) \{.*?\n  \}\n\n(?=  // Called by the C# host)",
    r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!rawCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    // GeoGebra/Exp46 has already produced the alternate projection for this
    // serial. A itself is the first eye, so only RIGHT must cross CEF IPC.
    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.right) return false;

    try {
      var sourceWidth = eyes.right.width | 0;
      var sourceHeight = eyes.right.height | 0;
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(sourceWidth, sourceHeight, geometry.rect);
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;

      if (rawCaptureCanvas.width !== eyeWidth) rawCaptureCanvas.width = eyeWidth;
      if (rawCaptureCanvas.height !== eyeHeight) rawCaptureCanvas.height = eyeHeight;
      rawCaptureContext.imageSmoothingEnabled = true;
      rawCaptureContext.imageSmoothingQuality = 'high';

      var drawStartedAt = performance.now();
      rawCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      var drawMs = Math.max(0, performance.now() - drawStartedAt);
      perfDrawCount++;
      perfDrawMsSum += drawMs;
      perfDrawMsMax = Math.max(perfDrawMsMax, drawMs);

      var readStartedAt = performance.now();
      var image = rawCaptureContext.getImageData(0, 0, eyeWidth, eyeHeight);
      var readMs = Math.max(0, performance.now() - readStartedAt);
      perfReadbackCount++;
      perfReadbackMsSum += readMs;
      perfReadbackMsMax = Math.max(perfReadbackMsMax, readMs);

      var expectedBytes = eyeWidth * eyeHeight * 4;
      if (!image || !image.data || image.data.byteLength !== expectedBytes) {
        throw new Error('raw alternate-eye byte length uyuşmuyor');
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      var postStartedAt = performance.now();
      var posted = postHostMessage({
        type: 'stereoRawEye',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: eyeWidth * 4,
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
        'Raw alternate-eye capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }

''',
    s,
    'v0.13.26 alternate-eye raw capture replacement',
    re.S)

# Durable marker / telemetry kind. Existing ACK-gating stays exactly as v0.13.24.
s = s.replace("kind: 'js-stereo-raw-arraybuffer'",
              "kind: 'js-stereo-single-eye-raw'", 1)
s = s.replace('// GeoGebraForQuest PC v0.12.3 XR-Behind Native runtime.',
              '// GeoGebraForQuest PC v0.13.26 A-left + GeoGebra-right raw stereo runtime.', 1)

# The v0.13.23 compositor trick must never reappear.
for forbidden in ('stereoGpuPhase', 'ggq-pc-raw-left-eye-overlay', 'showLeftOverlay'):
    if forbidden in s:
        raise SystemExit(f'v0.13.26 forbidden visible capture path remains: {forbidden}')

p.write_text(s, encoding='utf-8')


# 2) Host — accept the half-size raw eye message and publish it through the same
# SBS shared-memory protocol. Existing v0.13.24 full-SBS handler remains available
# but is no longer emitted by this runtime.
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

old_type = '''        if (message is not IDictionary<string, object> values ||
            !values.TryGetValue("type", out var typeObject) ||
            !string.Equals(typeObject?.ToString(), "stereoRawSbs", StringComparison.Ordinal))
        {
            return false;
        }
'''
req(s, old_type, 'v0.13.26 raw message type marker missing')
s = s.replace(old_type, '''        if (message is not IDictionary<string, object> values ||
            !values.TryGetValue("type", out var typeObject))
        {
            return false;
        }

        var rawType = typeObject?.ToString();
        if (!string.Equals(rawType, "stereoRawSbs", StringComparison.Ordinal) &&
            !string.Equals(rawType, "stereoRawEye", StringComparison.Ordinal))
        {
            return false;
        }
''', 1)

old_dispatch = '''            HandleRawStereoSbs(rgba, eyeWidth, eyeHeight, stride, serial);
'''
req(s, old_dispatch, 'v0.13.26 raw dispatch marker missing')
s = s.replace(old_dispatch, '''            if (string.Equals(rawType, "stereoRawEye", StringComparison.Ordinal))
                HandleRawStereoEye(rgba, eyeWidth, eyeHeight, stride, serial);
            else
                HandleRawStereoSbs(rgba, eyeWidth, eyeHeight, stride, serial);
''', 1)

handler_marker = '''    private void HandleRawStereoSbs(
'''
req(s, handler_marker, 'v0.13.26 HandleRawStereoSbs marker missing')

single_handler = r'''    private void HandleRawStereoEye(
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

        var expectedStride = checked(eyeWidth * 4);
        var expectedBytes = checked(expectedStride * eyeHeight);
        if (eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > 2048 || eyeHeight > 2048 ||
            stride != expectedStride || rgba.Length != expectedBytes)
        {
            throw new InvalidDataException(
                $"Raw alternate-eye boyutu geçersiz: {eyeWidth}x{eyeHeight}, stride={stride}, bytes={rgba.Length}");
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
        _sharedStereoFrames.WriteRawMonoAsSbsRgba(
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
s = s.replace(handler_marker, single_handler + handler_marker, 1)
p.write_text(s, encoding='utf-8')


# 3) MMF writer — duplicate only locally, after IPC. This retains the proven SBS
# protocol/XR texture class while cutting renderer->host IPC in half.
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')
set_inactive_marker = '    public void SetInactive(Rectangle stereoPanelClientBounds, Size applicationClientSize)\n'
req(s, set_inactive_marker, 'v0.13.26 writer insertion marker missing')

mono_writer = r'''    public void WriteRawMonoAsSbsRgba(
        byte[] rgbaEye,
        int eyeWidth,
        int eyeHeight,
        int eyeStride,
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        IReadOnlyList<Rectangle>? uiOverlayClientBounds,
        long frameNumber)
    {
        if (_disposed || rgbaEye is null ||
            applicationClientSize.Width < 1 || applicationClientSize.Height < 1 ||
            stereoPanelClientBounds.Width < 2 || stereoPanelClientBounds.Height < 2 ||
            eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > MaxEyeWidth || eyeHeight > MaxEyeHeight)
        {
            return;
        }

        var expectedEyeStride = checked(eyeWidth * 4);
        if (eyeStride != expectedEyeStride)
            throw new ArgumentException("Raw alternate eye stride must be tightly packed RGBA.");
        var eyeBytes = checked(eyeStride * eyeHeight);
        if (rgbaEye.Length != eyeBytes)
            throw new ArgumentException("Raw alternate eye byte length mismatch.");

        var sbsStride = checked(eyeStride * 2);
        var totalBytes = checked(sbsStride * eyeHeight);
        var sbs = ArrayPool<byte>.Shared.Rent(totalBytes);
        try
        {
            // Keep MMF compatibility. Both halves contain the alternate eye; XR
            // intentionally uses this texture only for its RIGHT eye. LEFT uses A.
            for (var y = 0; y < eyeHeight; y++)
            {
                var src = y * eyeStride;
                var dst = y * sbsStride;
                Buffer.BlockCopy(rgbaEye, src, sbs, dst, eyeStride);
                Buffer.BlockCopy(rgbaEye, src, sbs, dst + eyeStride, eyeStride);
            }

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

                _view.Write(116, 2); // RGBA
                _view.WriteArray(SbsOffset, sbs, 0, totalBytes);
                Thread.MemoryBarrier();
                _view.Write(8, evenSequence);
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(sbs);
        }
    }

'''
s = s.replace(set_inactive_marker, mono_writer + set_inactive_marker, 1)
p.write_text(s, encoding='utf-8')


# 4) XR — left eye is A itself; right eye is the alternate GeoGebra projection.
# Both occupy the exact same physical A plane, so panel depth itself adds no
# artificial disparity. Only GeoGebra's projection difference creates depth.
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

old_block = r'''        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;
        if (stereoVisible) {
            // The old v0.12 geometry was calculated for a panel 2 cm IN FRONT of A.
            // Convert it back to A's exact 3D viewport, then place B 2 cm BEHIND A
            // while preserving the same angular boundary in the headset.
            const float frontToBase =
                kScreenDistanceMeters / kStereoDistanceMeters;
            PanelRect baseHole = ScalePanelRect(*stereoRect, frontToBase);
            baseHole = ClampPanelRect(baseHole, baseRect);

            constexpr float behindDistance = kScreenDistanceMeters + 0.02f;
            const float baseToBehind = behindDistance / kScreenDistanceMeters;
            const PanelRect behindStereo =
                ScalePanelRect(baseHole, baseToBehind);

            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;

            // B first. It is geometrically behind A.
            DrawQuad(
                context, view, behindStereo, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);

            // A second, but with the exact 3D viewport omitted. This is the XR-only
            // transparent 3D window: PC still receives the untouched full CEF image.
            if (baseSrv) {
                DrawBaseWithHole(
                    context, view, baseRect, baseHole, baseSrv);
            }
        } else if (baseSrv) {
            // When a GeoGebra menu/dialog covers 3D, JS marks B inactive. Then A is
            // completely opaque again, so menus can never be hidden behind B.
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
        }
'''
req(s, old_block, 'v0.13.26 XR stereo render block missing')

new_block = r'''        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;
        if (stereoVisible) {
            // Convert the historical B rectangle back to A's exact 3D viewport.
            const float frontToBase =
                kScreenDistanceMeters / kStereoDistanceMeters;
            PanelRect baseHole = ScalePanelRect(*stereoRect, frontToBase);
            baseHole = ClampPanelRect(baseHole, baseRect);

            if (!rightEye) {
                // First eye already exists: untouched A, including its normal
                // GeoGebra 3D projection. No second copy of this eye is transported.
                if (baseSrv) {
                    DrawQuad(
                        context, view, baseRect, -kScreenDistanceMeters,
                        baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
                }
            } else {
                // Second eye: GeoGebra's own alternate projection, transported raw.
                // Draw it at EXACTLY A's plane; only the camera projection differs.
                DrawQuad(
                    context, view, baseHole, -kScreenDistanceMeters,
                    sbsSrv, 0.5f, 0.0f, 1.0f, 1.0f, true);

                if (baseSrv) {
                    DrawBaseWithHole(
                        context, view, baseRect, baseHole, baseSrv);
                }
            }
        } else if (baseSrv) {
            // No valid alternate eye: ordinary A remains fully visible in both eyes.
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
        }
'''
s = s.replace(old_block, new_block, 1)
p.write_text(s, encoding='utf-8')


# 5) Version/cache/package labels.
for name in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(name)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.24-raw-arraybuffer', '0.13.26-geogebra-glasses-raw')
    s = s.replace('v0.13.24', 'v0.13.26')
    if name.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.26</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.26.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.26.0</AssemblyVersion>', s, count=1)
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.26 A-left + GeoGebra-right raw stereo patch applied')
