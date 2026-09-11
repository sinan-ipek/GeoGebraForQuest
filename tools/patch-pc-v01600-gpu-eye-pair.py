#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.16.0 — two-paint GPU eye-pair transport.

Applied after v0.13.35 plus the v0.14.1/v0.14.2 GPU metadata/XR plumbing.
It replaces the failed full-screen SBS staging strategy with a LEFT-only overlay
that exists only over the real 3D panel. Both eye images are cropped from CEF
accelerated shared textures directly into a D3D11 2W x H pair texture.

No getImageData/readPixels/raw-pixel IPC/pixel MMF path is used.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Browser runtime: replace the v0.14 SBS stage with a LEFT-only overlay.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')
s = s.replace("ggq-gpu-stereo-stage-v0141", "ggq-gpu-left-eye-overlay-v0160")

start = s.find('  function ensureGpuStageCanvas() {')
end = s.find('\n  function pollRequestedStereoPair(now) {', start)
if start < 0 or end < 0:
    raise SystemExit('v0.16.0: v0.14 GPU stage block boundaries missing')

new_block = r'''  function ensureGpuStageCanvas() {
    if (gpuStageCanvas && gpuStageCanvas.isConnected && gpuStageContext) {
      return true;
    }

    gpuStageCanvas = document.createElement('canvas');
    gpuStageCanvas.id = 'ggq-gpu-left-eye-overlay-v0160';
    gpuStageCanvas.setAttribute('aria-hidden', 'true');
    var st = gpuStageCanvas.style;
    st.position = 'fixed';
    st.left = '0px';
    st.top = '0px';
    st.width = '2px';
    st.height = '2px';
    st.display = 'none';
    st.pointerEvents = 'none';
    st.zIndex = '2147483000';
    st.background = '#000';
    st.margin = '0';
    st.padding = '0';
    st.border = '0';
    st.opacity = '1';
    st.transform = 'none';
    st.imageRendering = 'auto';

    gpuStageContext = gpuStageCanvas.getContext('2d', {
      alpha: false,
      desynchronized: true
    });
    if (!gpuStageContext) {
      gpuStageCanvas = null;
      return false;
    }
    gpuStageContext.imageSmoothingEnabled = true;
    gpuStageContext.imageSmoothingQuality = 'high';
    (document.body || document.documentElement).appendChild(gpuStageCanvas);
    return true;
  }

  function hideGpuStage() {
    if (gpuStageCanvas) gpuStageCanvas.style.display = 'none';
    gpuStageLayout = null;
  }

  function beginGpuStereoCapture(serial, requestedAt) {
    if (gpuInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left || !eyes.right) return false;
    if (!ensureGpuStageCanvas()) return false;

    var sourceWidth = Math.min(eyes.left.width | 0, eyes.right.width | 0);
    var sourceHeight = Math.min(eyes.left.height | 0, eyes.right.height | 0);
    if (sourceWidth < 2 || sourceHeight < 2) return false;

    var r = geometry.rect;
    if (!r || r.width < 2 || r.height < 2) return false;

    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;
    gpuInFlight = true;
    gpuInFlightSerial = serial;
    gpuInFlightRequestedAt = requestedAt;
    gpuStageShownAt = 0;
    gpuReleaseOk = false;
    gpuStageLayout = {
      left: Number(r.left || 0),
      top: Number(r.top || 0),
      width: Number(r.width || 0),
      height: Number(r.height || 0)
    };

    bridge('gpuStereoPairReady', JSON.stringify({
      serial: serial,
      sourceWidth: sourceWidth,
      sourceHeight: sourceHeight,
      viewWidth: innerWidth,
      viewHeight: innerHeight,
      stereo: gpuStageLayout
    }));
    return true;
  }

  window.ggqGpuPresentStereoStage = function (serial) {
    serial = Number(serial);
    if (!gpuInFlight || !isFinite(serial) || serial !== gpuInFlightSerial) {
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left || !eyes.right || !ensureGpuStageCanvas()) return false;
    var sourceWidth = eyes.left.width | 0;
    var sourceHeight = eyes.left.height | 0;
    if (sourceWidth < 2 || sourceHeight < 2) return false;

    var layout = gpuStageLayout;
    if (!layout || layout.width < 2 || layout.height < 2) return false;

    if (gpuStageCanvas.width !== sourceWidth) gpuStageCanvas.width = sourceWidth;
    if (gpuStageCanvas.height !== sourceHeight) gpuStageCanvas.height = sourceHeight;
    gpuStageContext.imageSmoothingEnabled = true;
    gpuStageContext.imageSmoothingQuality = 'high';
    gpuStageContext.setTransform(1, 0, 0, 1, 0, 0);
    gpuStageContext.clearRect(0, 0, sourceWidth, sourceHeight);
    gpuStageContext.drawImage(
      eyes.left,
      0, 0, sourceWidth, sourceHeight,
      0, 0, sourceWidth, sourceHeight
    );

    var st = gpuStageCanvas.style;
    st.left = layout.left + 'px';
    st.top = layout.top + 'px';
    st.width = layout.width + 'px';
    st.height = layout.height + 'px';
    st.display = 'block';
    gpuStageShownAt = performance.now();

    var tokenSerial = serial;
    var done = false;
    function signalPresented(source) {
      if (done || !gpuInFlight || tokenSerial !== gpuInFlightSerial) return;
      done = true;
      bridge('gpuStereoStagePresented', JSON.stringify({
        serial: tokenSerial,
        viewWidth: innerWidth,
        viewHeight: innerHeight,
        stage: gpuStageLayout,
        sourceWidth: sourceWidth,
        sourceHeight: sourceHeight,
        ackSource: source,
        waitMs: Math.max(0, performance.now() - gpuStageShownAt)
      }));
    }
    try {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { signalPresented('raf2'); });
      });
    } catch (_) {}
    setTimeout(function () { signalPresented('timeout'); }, 36);
    return true;
  };

  window.ggqGpuReleaseStereoPair = function (serial, ok) {
    serial = Number(serial);
    var matched = gpuInFlight && isFinite(serial) && serial === gpuInFlightSerial;
    hideGpuStage();
    gpuStageShownAt = 0;
    gpuReleaseOk = matched && ok !== false;

    var tokenSerial = serial;
    var done = false;
    function signalHidden(source) {
      if (done) return;
      done = true;
      bridge('gpuStereoStageHidden', JSON.stringify({
        serial: tokenSerial,
        matched: !!matched,
        source: source
      }));
    }
    try {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { signalHidden('raf2'); });
      });
    } catch (_) {}
    setTimeout(function () { signalHidden('timeout'); }, 50);
    return matched;
  };

  window.ggqGpuResumeAfterCleanA = function (serial, ok) {
    serial = Number(serial);
    if (!gpuInFlight || !isFinite(serial) || serial !== gpuInFlightSerial) {
      hideGpuStage();
      return false;
    }

    var now = performance.now();
    var requestedAt = gpuInFlightRequestedAt;
    if (ok !== false && gpuReleaseOk) lastDeliveredStereoSerial = serial;

    gpuInFlight = false;
    gpuInFlightSerial = -1;
    gpuInFlightRequestedAt = 0;
    gpuStageShownAt = 0;
    gpuStageLayout = null;
    gpuReleaseOk = false;

    if (!gpuExternallySuspended) {
      var cycleMs = requestedAt ? Math.max(0, now - requestedAt) : 0;
      nextStereoRequestAt = requestedAt && cycleMs < CAPTURE_INTERVAL_MS
        ? requestedAt + CAPTURE_INTERVAL_MS
        : now + 1;
    }
    return true;
  };

  window.ggqGpuSetSuspended = function (value) {
    gpuExternallySuspended = !!value;
    if (gpuExternallySuspended) hideGpuStage();
    if (!gpuExternallySuspended && !gpuInFlight) {
      nextStereoRequestAt = performance.now() + 1;
    }
    return true;
  };
'''
s = s[:start] + new_block + s[end:]
s = s.replace("canvas.id === 'ggq-gpu-stereo-stage-v0141'", "canvas.id === 'ggq-gpu-left-eye-overlay-v0160'")

for forbidden in ('getImageData(', 'readPixels(', "type: 'stereoRawPair'", 'ggqRawStereoAck', 'ggq-gpu-stereo-stage-v0141'):
    if forbidden in s:
        raise SystemExit('v0.16.0 forbidden path remains: ' + forbidden)
for needed in (
    'ggq-gpu-left-eye-overlay-v0160',
    "gpuStageContext.drawImage(\n      eyes.left",
    "bridge('gpuStereoPairReady'",
    "bridge('gpuStereoStagePresented'",
    "bridge('gpuStereoStageHidden'",
    'window.ggqGpuResumeAfterCleanA',
    'window.ggqGpuSetSuspended',
):
    req(s, needed, 'v0.16.0 runtime invariant missing: ' + needed)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Host: two accelerated paints become a cropped 2W x H GPU pair.
# ---------------------------------------------------------------------------
host = r'''using System.Diagnostics;
using System.Text.Json;
using CefSharp;
using SharpDX.Direct3D11;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private enum GpuStereoV141State
    {
        Idle,
        AwaitStagePresented,
        CaptureStagePaint,
        AwaitStageHidden,
        CaptureCleanAPaint,
        AwaitCleanAPublish
    }

    private readonly StereoGpuTexturePublisher _stereoGpuPublisher = new();
    private readonly GpuStereoV141Telemetry _gpuStereoV141Telemetry = new();
    private GpuStereoV141State _gpuStereoV141State = GpuStereoV141State.Idle;
    private long _gpuStereoV141Serial = -1;
    private RectangleF _gpuStereoV141StageCss = RectangleF.Empty;
    private SizeF _gpuStereoV141ViewCss = SizeF.Empty;
    private Rectangle _gpuStereoV141PanelSnapshot = Rectangle.Empty;
    private Size _gpuStereoV141ClientSnapshot = Size.Empty;
    private bool _gpuStereoV141PairSucceeded;
    private Texture2D? _stereoGpuWorkingTexture;
    private Texture2D? _stereoGpuSharedTexture;
    private KeyedMutex? _stereoGpuSharedMutex;
    private IntPtr _stereoGpuSharedHandle;
    private int _stereoGpuEyeWidth;
    private int _stereoGpuEyeHeight;
    private long _stereoGpuFrameNumber;

    private static bool TryGpuPayload(JsonElement root, out JsonDocument? document)
    {
        document = null;
        if (!root.TryGetProperty("payload", out var payloadNode)) return false;
        var payload = payloadNode.GetString();
        if (string.IsNullOrWhiteSpace(payload)) return false;
        document = JsonDocument.Parse(payload);
        return true;
    }

    private void HandleGpuStereoV141PairReady(JsonElement root)
    {
        try
        {
            if (!TryGpuPayload(root, out var document) || document is null) return;
            using (document)
            {
                var payload = document.RootElement;
                var serial = payload.TryGetProperty("serial", out var serialNode) ? serialNode.GetInt64() : -1;
                if (serial < 0) return;
                if (_stereoUiSuspended)
                {
                    _stereoGpuPublisher.SetInactive();
                    ExecuteGpuStereoV141Script($"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},false);");
                    return;
                }

                bool active;
                Rectangle panel;
                Size clientSize;
                lock (_geometryLock)
                {
                    active = _stereo3DActive;
                    panel = _stereo3DRenderBounds;
                    clientSize = _browserSize;
                }
                if (!active || panel.Width < 2 || panel.Height < 2 || clientSize.Width < 2 || clientSize.Height < 2)
                {
                    _stereoGpuPublisher.SetInactive();
                    ExecuteGpuStereoV141Script($"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},false);");
                    return;
                }

                bool begin = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141State == GpuStereoV141State.Idle)
                    {
                        _gpuStereoV141Serial = serial;
                        _gpuStereoV141PanelSnapshot = panel;
                        _gpuStereoV141ClientSnapshot = clientSize;
                        _gpuStereoV141PairSucceeded = false;
                        _gpuStereoV141State = GpuStereoV141State.AwaitStagePresented;
                        begin = true;
                    }
                }
                if (!begin) return;

                _gpuStereoV141Telemetry.Event("pair-ready", serial, detail: $"panel={panel.X}:{panel.Y}:{panel.Width}:{panel.Height}");
                ExecuteGpuStereoV141Script($"window.ggqGpuPresentStereoStage && window.ggqGpuPresentStereoStage({serial});");
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.AwaitStagePresented);
            }
        }
        catch (Exception ex) { _gpuStereoV141Telemetry.Event("pair-ready-error", detail: ex.Message); }
    }

    private void HandleGpuStereoV141StagePresented(JsonElement root)
    {
        try
        {
            if (!TryGpuPayload(root, out var document) || document is null) return;
            using (document)
            {
                var payload = document.RootElement;
                var serial = payload.TryGetProperty("serial", out var serialNode) ? serialNode.GetInt64() : -1;
                if (!payload.TryGetProperty("stage", out var stage)) return;
                var viewWidth = payload.TryGetProperty("viewWidth", out var vw) ? vw.GetDouble() : 0;
                var viewHeight = payload.TryGetProperty("viewHeight", out var vh) ? vh.GetDouble() : 0;
                if (serial < 0 || viewWidth < 2 || viewHeight < 2) return;

                var rect = new RectangleF(
                    (float)stage.GetProperty("left").GetDouble(),
                    (float)stage.GetProperty("top").GetDouble(),
                    (float)stage.GetProperty("width").GetDouble(),
                    (float)stage.GetProperty("height").GetDouble());
                if (rect.Width < 2 || rect.Height < 2) return;

                bool capture = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial && _gpuStereoV141State == GpuStereoV141State.AwaitStagePresented)
                    {
                        _gpuStereoV141StageCss = rect;
                        _gpuStereoV141ViewCss = new SizeF((float)viewWidth, (float)viewHeight);
                        _gpuStereoV141State = GpuStereoV141State.CaptureStagePaint;
                        capture = true;
                    }
                }
                if (!capture) return;
                _gpuStereoV141Telemetry.Event("left-presented", serial);
                InvalidateGpuStereoV141View();
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureStagePaint);
            }
        }
        catch (Exception ex) { _gpuStereoV141Telemetry.Event("left-presented-error", detail: ex.Message); }
    }

    private void HandleGpuStereoV141StageHidden(JsonElement root)
    {
        try
        {
            if (!TryGpuPayload(root, out var document) || document is null) return;
            using (document)
            {
                var payload = document.RootElement;
                var serial = payload.TryGetProperty("serial", out var serialNode) ? serialNode.GetInt64() : -1;
                if (serial < 0) return;
                bool capture = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial && _gpuStereoV141State == GpuStereoV141State.AwaitStageHidden)
                    {
                        _gpuStereoV141State = GpuStereoV141State.CaptureCleanAPaint;
                        capture = true;
                    }
                }
                if (!capture) return;
                _gpuStereoV141Telemetry.Event("left-hidden", serial);
                InvalidateGpuStereoV141View();
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureCleanAPaint);
            }
        }
        catch (Exception ex) { _gpuStereoV141Telemetry.Event("left-hidden-error", detail: ex.Message); }
    }

    private void ExecuteGpuStereoV141Script(string script)
    {
        if (_closing) return;
        try { _browser?.GetBrowser()?.MainFrame?.ExecuteJavaScriptAsync(script); }
        catch (Exception ex) { _gpuStereoV141Telemetry.Event("execute-js-error", detail: ex.Message); }
    }

    private void InvalidateGpuStereoV141View()
    {
        try { _browser?.GetBrowserHost()?.Invalidate(PaintElementType.View); } catch { }
    }

    private void ScheduleGpuStereoV141Invalidate(int delayMs = 1)
    {
        ThreadPool.QueueUserWorkItem(_ =>
        {
            if (delayMs > 0) Thread.Sleep(delayMs);
            if (!_closing) InvalidateGpuStereoV141View();
        });
    }

    private void ArmGpuStereoV141Watchdog(long serial, GpuStereoV141State expected)
    {
        _ = Task.Run(async () =>
        {
            await Task.Delay(900).ConfigureAwait(false);
            if (_closing) return;
            GpuStereoV141State current;
            lock (_d3dLock)
            {
                if (_gpuStereoV141Serial != serial || _gpuStereoV141State != expected) return;
                current = _gpuStereoV141State;
            }
            _gpuStereoV141Telemetry.Event("phase-timeout", serial, detail: current.ToString());
            if (current == GpuStereoV141State.CaptureStagePaint || current == GpuStereoV141State.CaptureCleanAPaint || current == GpuStereoV141State.AwaitCleanAPublish)
            {
                ScheduleGpuStereoV141Invalidate(1);
                ArmGpuStereoV141Watchdog(serial, current);
                return;
            }
            if (current == GpuStereoV141State.AwaitStageHidden)
            {
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial && _gpuStereoV141State == GpuStereoV141State.AwaitStageHidden)
                        _gpuStereoV141State = GpuStereoV141State.CaptureCleanAPaint;
                }
                InvalidateGpuStereoV141View();
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureCleanAPaint);
                return;
            }
            AbortGpuStereoV160(serial, "watchdog-" + current);
        });
    }

    private bool TryConsumeGpuStereoV141PaintLocked(Texture2D cefTexture)
    {
        var state = _gpuStereoV141State;
        if (state == GpuStereoV141State.Idle) return false;
        if (state == GpuStereoV141State.AwaitStagePresented || state == GpuStereoV141State.AwaitStageHidden) return true;
        if (state == GpuStereoV141State.AwaitCleanAPublish) return false;
        if (state != GpuStereoV141State.CaptureStagePaint && state != GpuStereoV141State.CaptureCleanAPaint) return false;

        var view = _gpuStereoV141ViewCss;
        var stage = _gpuStereoV141StageCss;
        if (view.Width < 2 || view.Height < 2 || stage.Width < 2 || stage.Height < 2)
            return state == GpuStereoV141State.CaptureStagePaint;

        var textureWidth = cefTexture.Description.Width;
        var textureHeight = cefTexture.Description.Height;
        var scaleX = textureWidth / Math.Max(1.0f, view.Width);
        var scaleY = textureHeight / Math.Max(1.0f, view.Height);
        var left = Math.Clamp((int)Math.Round(stage.Left * scaleX), 0, Math.Max(0, textureWidth - 2));
        var top = Math.Clamp((int)Math.Round(stage.Top * scaleY), 0, Math.Max(0, textureHeight - 2));
        var right = Math.Clamp((int)Math.Round((stage.Left + stage.Width) * scaleX), left + 2, textureWidth);
        var bottom = Math.Clamp((int)Math.Round((stage.Top + stage.Height) * scaleY), top + 2, textureHeight);
        var crop = Rectangle.FromLTRB(left, top, right, bottom);
        if (crop.Width < 2 || crop.Height < 2) return state == GpuStereoV141State.CaptureStagePaint;

        EnsureStereoGpuPairTexturesLocked(crop.Width, crop.Height, cefTexture.Description.Format);
        if (_stereoGpuWorkingTexture is null) return state == GpuStereoV141State.CaptureStagePaint;

        var region = new SharpDX.Direct3D11.ResourceRegion
        {
            Left = crop.Left,
            Top = crop.Top,
            Front = 0,
            Right = crop.Right,
            Bottom = crop.Bottom,
            Back = 1
        };
        var destX = state == GpuStereoV141State.CaptureStagePaint ? 0 : crop.Width;
        _device!.ImmediateContext.CopySubresourceRegion(cefTexture, 0, region, _stereoGpuWorkingTexture, 0, destX, 0, 0);

        var serial = _gpuStereoV141Serial;
        if (state == GpuStereoV141State.CaptureStagePaint)
        {
            _gpuStereoV141State = GpuStereoV141State.AwaitStageHidden;
            _gpuStereoV141Telemetry.Event("left-gpu-copied", serial, crop.Width, crop.Height);
            ThreadPool.QueueUserWorkItem(_ => ExecuteGpuStereoV141Script(
                $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial},true);"));
            ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.AwaitStageHidden);
            return true;
        }

        _gpuStereoV141State = GpuStereoV141State.AwaitCleanAPublish;
        _gpuStereoV141PairSucceeded = true;
        _gpuStereoV141Telemetry.Event("right-gpu-copied", serial, crop.Width, crop.Height);
        return false;
    }

    private void CompleteGpuStereoV141CleanAPaintLocked(bool aGpuPublished)
    {
        if (_gpuStereoV141State != GpuStereoV141State.AwaitCleanAPublish) return;
        var serial = _gpuStereoV141Serial;
        if (!aGpuPublished)
        {
            ScheduleGpuStereoV141Invalidate(1);
            return;
        }
        if (!_gpuStereoV141PairSucceeded || _stereoGpuWorkingTexture is null || _stereoGpuSharedTexture is null || _stereoGpuSharedMutex is null || _stereoGpuSharedHandle == IntPtr.Zero || _stereoGpuEyeWidth < 2 || _stereoGpuEyeHeight < 2)
        {
            AbortGpuStereoV160(serial, "pair-resources-missing");
            return;
        }

        try { _stereoGpuSharedMutex.Acquire(0, 0); }
        catch
        {
            _gpuStereoV141Telemetry.Event("b-mutex-busy", serial);
            ScheduleGpuStereoV141Invalidate(1);
            return;
        }

        var released = false;
        try
        {
            var watch = Stopwatch.StartNew();
            _device!.ImmediateContext.CopyResource(_stereoGpuWorkingTexture, _stereoGpuSharedTexture);
            _device.ImmediateContext.Flush();
            watch.Stop();
            _stereoGpuSharedMutex.Release(1);
            released = true;

            var frame = Interlocked.Increment(ref _stereoGpuFrameNumber);
            var fullPair = new Rectangle(0, 0, _stereoGpuEyeWidth * 2, _stereoGpuEyeHeight);
            _stereoGpuPublisher.Publish(
                _stereoGpuSharedHandle,
                _stereoGpuEyeWidth * 2,
                _stereoGpuEyeHeight,
                _stereoGpuWorkingTexture.Description.Format,
                _gpuStereoV141ClientSnapshot,
                _gpuStereoV141PanelSnapshot,
                fullPair,
                frame);

            _gpuStereoV141State = GpuStereoV141State.Idle;
            _gpuShareStatus = "B GPU L/R";
            _gpuStereoV141Telemetry.Event(
                "b-gpu-published", serial,
                _stereoGpuEyeWidth * 2, _stereoGpuEyeHeight,
                _stereoGpuEyeWidth, _stereoGpuEyeHeight,
                watch.Elapsed.TotalMilliseconds,
                "2W x H direct GPU pair");
            ThreadPool.QueueUserWorkItem(_ => ExecuteGpuStereoV141Script(
                $"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},true);"));
            BeginInvokeSafe(UpdateWindowTitle);
        }
        finally
        {
            if (!released) { try { _stereoGpuSharedMutex.Release(0); } catch { } }
        }
    }

    private void AbortGpuStereoV160(long serial, string reason)
    {
        lock (_d3dLock)
        {
            if (_gpuStereoV141Serial != serial) return;
            _gpuStereoV141State = GpuStereoV141State.Idle;
            _gpuStereoV141PairSucceeded = false;
        }
        _stereoGpuPublisher.SetInactive();
        _gpuStereoV141Telemetry.Event("pair-abort", serial, detail: reason);
        ExecuteGpuStereoV141Script(
            $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial},false);" +
            $"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},false);");
    }

    private void EnsureStereoGpuPairTexturesLocked(int eyeWidth, int eyeHeight, Format format)
    {
        if (_device is null) return;
        var pairWidth = eyeWidth * 2;
        bool reusable = _stereoGpuWorkingTexture is not null && _stereoGpuSharedTexture is not null && _stereoGpuSharedMutex is not null &&
            _stereoGpuWorkingTexture.Description.Width == pairWidth && _stereoGpuWorkingTexture.Description.Height == eyeHeight && _stereoGpuWorkingTexture.Description.Format == format;
        if (reusable)
        {
            _stereoGpuEyeWidth = eyeWidth;
            _stereoGpuEyeHeight = eyeHeight;
            return;
        }

        if (_stereoGpuSharedMutex is not null) _retiredSharedResources.Add(_stereoGpuSharedMutex);
        if (_stereoGpuSharedTexture is not null) _retiredSharedResources.Add(_stereoGpuSharedTexture);
        _stereoGpuWorkingTexture?.Dispose();
        _stereoGpuWorkingTexture = null;
        _stereoGpuSharedMutex = null;
        _stereoGpuSharedTexture = null;
        _stereoGpuSharedHandle = IntPtr.Zero;

        var common = new Texture2DDescription
        {
            Width = pairWidth,
            Height = eyeHeight,
            MipLevels = 1,
            ArraySize = 1,
            Format = format,
            SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default,
            BindFlags = BindFlags.ShaderResource,
            CpuAccessFlags = CpuAccessFlags.None,
            OptionFlags = ResourceOptionFlags.None
        };
        _stereoGpuWorkingTexture = new Texture2D(_device, common);
        common.OptionFlags = ResourceOptionFlags.SharedKeyedmutex;
        _stereoGpuSharedTexture = new Texture2D(_device, common);
        _stereoGpuSharedMutex = _stereoGpuSharedTexture.QueryInterface<KeyedMutex>();
        using var dxgiResource = _stereoGpuSharedTexture.QueryInterface<SharpDX.DXGI.Resource>();
        _stereoGpuSharedHandle = dxgiResource.SharedHandle;
        _stereoGpuEyeWidth = eyeWidth;
        _stereoGpuEyeHeight = eyeHeight;
    }

    private void EnsureStereoGpuSharedTextureLocked(Texture2DDescription source) { }

    private void DisposeGpuStereoV141ResourcesLocked()
    {
        _stereoGpuWorkingTexture?.Dispose();
        _stereoGpuSharedMutex?.Dispose();
        _stereoGpuSharedTexture?.Dispose();
        _stereoGpuWorkingTexture = null;
        _stereoGpuSharedMutex = null;
        _stereoGpuSharedTexture = null;
        _stereoGpuSharedHandle = IntPtr.Zero;
    }
}
'''
Path('pc/MainFormV141.GpuStereo.cs').write_text(host, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Graphics hook: LEFT paint is swallowed; clean RIGHT goes through normal A.
#    v0.14.2 already calls CompleteGpuStereoV141CleanAPaintLocked after A.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.Graphics.cs')
g = p.read_text(encoding='utf-8')
req(g, 'TryConsumeGpuStereoV141PaintLocked(cefTexture)', 'v0.16.0: accelerated-paint stereo hook missing')
if 'CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142)' not in g:
    marker = '                        CompleteGpuPublishLocked(cefTexture.Description);\n'
    req(g, marker, 'v0.16.0: A publish completion marker missing')
    g = g.replace(marker, marker + '                        CompleteGpuStereoV141CleanAPaintLocked(true);\n', 1)
popup_pos = g.find('PaintElementType.Popup')
hook_pos = g.find('TryConsumeGpuStereoV141PaintLocked(cefTexture)')
if popup_pos < 0 or hook_pos < 0 or popup_pos > hook_pos:
    raise SystemExit('v0.16.0: popup-first accelerated paint ordering lost')
p.write_text(g, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Labels/version. XR v0.14.1 reader/compositor remains valid: stage == full B.
# ---------------------------------------------------------------------------
p = Path('pc/GeoGebraForQuest.PC.csproj')
project = p.read_text(encoding='utf-8')
project = re.sub(r'<Version>[^<]+</Version>', '<Version>0.16.0</Version>', project, count=1)
project = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.16.0.0</FileVersion>', project, count=1)
project = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.16.0.0</AssemblyVersion>', project, count=1)
p.write_text(project, encoding='utf-8')

p = Path('pc/build.ps1')
b = p.read_text(encoding='utf-8')
b = b.replace('GeoGebraForQuest-PC-v0.14.2-safe-gpu-b-win-x64', 'GeoGebraForQuest-PC-v0.16.0-gpu-eye-pair-win-x64')
b = b.replace('GeoGebraForQuest-PC-v0.14.1-zero-copy-b-win-x64', 'GeoGebraForQuest-PC-v0.16.0-gpu-eye-pair-win-x64')
b = b.replace('0.14.2-safe-gpu-b', '0.16.0-gpu-eye-pair').replace('0.14.1-zero-copy-b', '0.16.0-gpu-eye-pair')
b = b.replace('v0.14.2', 'v0.16.0').replace('v0.14.1', 'v0.16.0')
p.write_text(b, encoding='utf-8')

p = Path('pc/MainFormV11.cs')
main = p.read_text(encoding='utf-8')
main = re.sub(r'(pc-stereo-layout\.js\?v=)[^"\']+', r'\g<1>0.16.0-gpu-eye-pair', main, count=1)
main = main.replace('GeoGebraForQuest PC v0.14.2', 'GeoGebraForQuest PC v0.16.0')
main = main.replace('GeoGebraForQuest PC v0.14.1', 'GeoGebraForQuest PC v0.16.0')
main = main.replace('v0.14.2 ·', 'v0.16.0 ·').replace('v0.14.1 ·', 'v0.16.0 ·')
p.write_text(main, encoding='utf-8')

s = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
g = Path('pc/MainFormV11.Graphics.cs').read_text(encoding='utf-8')
h = Path('pc/MainFormV141.GpuStereo.cs').read_text(encoding='utf-8')
for forbidden in ('getImageData(', 'readPixels(', 'stereoRawPair', 'ggqRawStereoAck', 'ggq-gpu-stereo-stage-v0141'):
    if forbidden in s:
        raise SystemExit('v0.16.0 final forbidden runtime path: ' + forbidden)
for text, needle, label in (
    (s, 'ggq-gpu-left-eye-overlay-v0160', 'LEFT overlay missing'),
    (h, 'CopySubresourceRegion(', 'GPU crop copy missing'),
    (h, 'AwaitCleanAPublish', 'clean-A publication gate missing'),
    (h, '2W x H direct GPU pair', '2W x H pair publisher missing'),
    (g, 'TryConsumeGpuStereoV141PaintLocked(cefTexture)', 'accelerated paint hook missing'),
):
    req(text, needle, 'v0.16.0: ' + label)

print('[GGQ] v0.16.0 two-paint GPU L/R transport applied')
