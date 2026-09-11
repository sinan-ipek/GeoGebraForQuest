#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.14.2 — safe zero-copy GPU-B latch.

Fixes the first v0.14.1 field test regressions without returning to CPU pixels:

1. Snapshot the valid 3D geometry BEFORE the temporary SBS stage becomes visible.
2. Never return the GPU-B state machine to Idle while the SBS stage can still be
   present in the CEF View texture.
3. After B is copied/published, hide the stage, wait for a hidden acknowledgement,
   force one clean A paint, publish that clean A frame, and only then resume the
   next stereo capture.
4. Set the new GPU-B publisher inactive immediately whenever GeoGebra reports
   stereo inactive or the UI is suspended (CEF popup, native File/Open, auth).
5. Pause the JS capture loop while UI suspension is active.
6. Disable the injected Quest virtual keyboard while preserving the auth popup
   flow and normal physical-PC keyboard input.

The v0.13.35 L/R production path remains unchanged. There is still no
getImageData/readPixels/raw pixel IPC/pixel MMF path in the v0.14 runtime.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Browser runtime: hold the capture cycle until the temporary SBS stage has
#    been hidden AND a clean A frame has been republished by the host.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

field_marker = '  var gpuStageLayout = null;\n'
req(s, field_marker, 'v0.14.2: gpu stage field marker missing')
s = s.replace(
    field_marker,
    field_marker +
    '  var gpuExternallySuspended = false;\n'
    '  var gpuReleaseOk = false;\n',
    1)

release_start = s.find('  window.ggqGpuReleaseStereoPair = function (serial, ok) {')
release_end = s.find('\n  function pollRequestedStereoPair(now) {', release_start)
if release_start < 0 or release_end < 0:
    raise SystemExit('v0.14.2: v0.14.1 release function boundaries missing')

new_release = r'''  window.ggqGpuReleaseStereoPair = function (serial, ok) {
    serial = Number(serial);
    var matched = gpuInFlight && isFinite(serial) && serial === gpuInFlightSerial;

    // Hiding is synchronous from the DOM point of view, but we deliberately keep
    // gpuInFlight true until the host has republished one clean A frame. That
    // prevents a new stereo request from racing the clean-A restore phase.
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
    if (!gpuExternallySuspended && !gpuInFlight) {
      nextStereoRequestAt = performance.now() + 1;
    }
    return true;
  };
'''
s = s[:release_start] + new_release + s[release_end:]

loop_marker = '''  function captureLoop(now) {
    if (gpuInFlight) {'''
req(s, loop_marker, 'v0.14.2: captureLoop marker missing')
s = s.replace(
    loop_marker,
    '''  function captureLoop(now) {
    if (gpuExternallySuspended) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (gpuInFlight) {''',
    1)

for needed in (
    'window.ggqGpuResumeAfterCleanA',
    'window.ggqGpuSetSuspended',
    "bridge('gpuStereoStageHidden'",
    'gpuExternallySuspended',
):
    req(s, needed, 'v0.14.2 runtime invariant missing: ' + needed)
for forbidden in ('getImageData(', 'readPixels(', "type: 'stereoRawPair'", 'ggqRawStereoAck'):
    if forbidden in s:
        raise SystemExit('v0.14.2 forbidden CPU pixel path remains: ' + forbidden)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Host GPU-B state machine. Keep the existing method/file names so the
#    v0.14.1 accelerated-paint hook remains a minimal, proven integration point.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV141.GpuStereo.cs')
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
        CaptureCleanAPaint
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
    private Texture2D? _stereoGpuSharedTexture;
    private KeyedMutex? _stereoGpuSharedMutex;
    private IntPtr _stereoGpuSharedHandle;
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
                var serial = payload.TryGetProperty("serial", out var serialNode)
                    ? serialNode.GetInt64()
                    : -1;
                if (serial < 0) return;

                if (_stereoUiSuspended)
                {
                    _stereoGpuPublisher.SetInactive();
                    _gpuStereoV141Telemetry.Event("pair-rejected-ui-suspended", serial);
                    ExecuteGpuStereoV141Script(
                        $"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},false);");
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

                // CRITICAL v0.14.2 rule: geometry is snapshotted before the SBS
                // staging canvas becomes visible. Never re-detect the 3D panel from
                // a page that already contains our own temporary overlay.
                if (!active || panel.Width < 2 || panel.Height < 2 ||
                    clientSize.Width < 2 || clientSize.Height < 2)
                {
                    _stereoGpuPublisher.SetInactive();
                    _gpuStereoV141Telemetry.Event("pair-rejected-no-3d", serial);
                    ExecuteGpuStereoV141Script(
                        $"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},false);");
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

                _gpuStereoV141Telemetry.Event(
                    "pair-ready",
                    serial,
                    detail: $"panel={panel.X}:{panel.Y}:{panel.Width}:{panel.Height}");
                ExecuteGpuStereoV141Script(
                    $"window.ggqGpuPresentStereoStage && window.ggqGpuPresentStereoStage({serial});");
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.AwaitStagePresented);
            }
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("pair-ready-error", detail: ex.Message);
        }
    }

    private void HandleGpuStereoV141StagePresented(JsonElement root)
    {
        try
        {
            if (!TryGpuPayload(root, out var document) || document is null) return;
            using (document)
            {
                var payload = document.RootElement;
                var serial = payload.TryGetProperty("serial", out var serialNode)
                    ? serialNode.GetInt64()
                    : -1;
                if (!payload.TryGetProperty("stage", out var stage)) return;

                var viewWidth = payload.TryGetProperty("viewWidth", out var viewWidthNode)
                    ? viewWidthNode.GetDouble()
                    : 0;
                var viewHeight = payload.TryGetProperty("viewHeight", out var viewHeightNode)
                    ? viewHeightNode.GetDouble()
                    : 0;
                if (serial < 0 || viewWidth < 2 || viewHeight < 2) return;

                var rect = new RectangleF(
                    (float)stage.GetProperty("left").GetDouble(),
                    (float)stage.GetProperty("top").GetDouble(),
                    (float)stage.GetProperty("width").GetDouble(),
                    (float)stage.GetProperty("height").GetDouble());
                if (rect.Width < 4 || rect.Height < 2) return;

                if (_stereoUiSuspended)
                {
                    BeginGpuStereoV141HideAndRestore(serial, false, "stage-presented-ui-suspended");
                    return;
                }

                bool capture = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial &&
                        _gpuStereoV141State == GpuStereoV141State.AwaitStagePresented)
                    {
                        _gpuStereoV141StageCss = rect;
                        _gpuStereoV141ViewCss = new SizeF((float)viewWidth, (float)viewHeight);
                        _gpuStereoV141State = GpuStereoV141State.CaptureStagePaint;
                        capture = true;
                    }
                }
                if (!capture) return;

                _gpuStereoV141Telemetry.Event(
                    "stage-presented",
                    serial,
                    stageWidth: (int)Math.Round(rect.Width),
                    stageHeight: (int)Math.Round(rect.Height));
                InvalidateGpuStereoV141View();
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureStagePaint);
            }
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("stage-presented-error", detail: ex.Message);
        }
    }

    private void HandleGpuStereoV141StageHidden(JsonElement root)
    {
        try
        {
            if (!TryGpuPayload(root, out var document) || document is null) return;
            using (document)
            {
                var payload = document.RootElement;
                var serial = payload.TryGetProperty("serial", out var serialNode)
                    ? serialNode.GetInt64()
                    : -1;
                if (serial < 0) return;

                bool restore = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial &&
                        _gpuStereoV141State == GpuStereoV141State.AwaitStageHidden)
                    {
                        _gpuStereoV141State = GpuStereoV141State.CaptureCleanAPaint;
                        restore = true;
                    }
                }
                if (!restore) return;

                _gpuStereoV141Telemetry.Event("stage-hidden", serial);
                InvalidateGpuStereoV141View();
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureCleanAPaint);
            }
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("stage-hidden-error", detail: ex.Message);
        }
    }

    private void ExecuteGpuStereoV141Script(string script)
    {
        if (_closing) return;
        try
        {
            _browser?.GetBrowser()?.MainFrame?.ExecuteJavaScriptAsync(script);
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("execute-js-error", detail: ex.Message);
        }
    }

    private void InvalidateGpuStereoV141View()
    {
        try
        {
            _browser?.GetBrowserHost()?.Invalidate(PaintElementType.View);
        }
        catch
        {
        }
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
                if (_gpuStereoV141Serial != serial || _gpuStereoV141State != expected)
                    return;
                current = _gpuStereoV141State;
            }

            _gpuStereoV141Telemetry.Event(
                "phase-timeout",
                serial,
                detail: current.ToString());

            if (current == GpuStereoV141State.CaptureCleanAPaint)
            {
                // Stage is already hidden in this phase. Keep capture paused and
                // request another clean A paint rather than allowing contamination.
                ScheduleGpuStereoV141Invalidate(0);
                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureCleanAPaint);
                return;
            }

            if (current == GpuStereoV141State.AwaitStageHidden)
            {
                // ggqGpuReleaseStereoPair hides synchronously before its rAF ACK.
                // If the ACK was lost, advance conservatively to a clean-A repaint.
                lock (_d3dLock)
                {
                    if (_gpuStereoV141Serial == serial &&
                        _gpuStereoV141State == GpuStereoV141State.AwaitStageHidden)
                    {
                        _gpuStereoV141State = GpuStereoV141State.CaptureCleanAPaint;
                    }
                }
                InvalidateGpuStereoV141View();
                return;
            }

            BeginGpuStereoV141HideAndRestore(serial, false, "watchdog");
        });
    }

    private void BeginGpuStereoV141HideAndRestore(long serial, bool success, string reason)
    {
        bool hide = false;
        lock (_d3dLock)
        {
            if (_gpuStereoV141Serial != serial ||
                _gpuStereoV141State == GpuStereoV141State.Idle)
            {
                return;
            }

            _gpuStereoV141PairSucceeded = success;
            if (_gpuStereoV141State != GpuStereoV141State.AwaitStageHidden &&
                _gpuStereoV141State != GpuStereoV141State.CaptureCleanAPaint)
            {
                _gpuStereoV141State = GpuStereoV141State.AwaitStageHidden;
                hide = true;
            }
        }

        _gpuStereoV141Telemetry.Event("hide-stage", serial, detail: reason);
        if (hide)
        {
            ExecuteGpuStereoV141Script(
                $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial},{(success ? "true" : "false")});");
            ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.AwaitStageHidden);
        }
    }

    private bool TryConsumeGpuStereoV141PaintLocked(Texture2D cefTexture)
    {
        var state = _gpuStereoV141State;
        if (state == GpuStereoV141State.Idle) return false;

        // During clean-A restoration the temporary stage is already hidden.
        // Allow the ordinary A path to consume this paint; completion is signaled
        // by CompleteGpuStereoV141CleanAPaintLocked after A's GPU publish succeeds.
        if (state == GpuStereoV141State.CaptureCleanAPaint)
        {
            return false;
        }

        // Suppress all temporary-stage paints from both the physical PC swapchain
        // and the ordinary A XR publisher until the exact B capture phase.
        if (state != GpuStereoV141State.CaptureStagePaint)
        {
            return true;
        }

        if (_stereoUiSuspended)
        {
            BeginGpuStereoV141HideAndRestore(
                _gpuStereoV141Serial,
                false,
                "capture-ui-suspended");
            return true;
        }

        var serial = _gpuStereoV141Serial;
        var view = _gpuStereoV141ViewCss;
        var stage = _gpuStereoV141StageCss;
        var panel = _gpuStereoV141PanelSnapshot;
        var clientSize = _gpuStereoV141ClientSnapshot;

        if (view.Width < 2 || view.Height < 2 || stage.Width < 4 || stage.Height < 2 ||
            panel.Width < 2 || panel.Height < 2 ||
            clientSize.Width < 2 || clientSize.Height < 2)
        {
            BeginGpuStereoV141HideAndRestore(serial, false, "invalid-snapshot");
            return true;
        }

        var textureWidth = cefTexture.Description.Width;
        var textureHeight = cefTexture.Description.Height;
        var scaleX = textureWidth / Math.Max(1.0f, view.Width);
        var scaleY = textureHeight / Math.Max(1.0f, view.Height);

        var left = Math.Clamp(
            (int)Math.Round(stage.Left * scaleX),
            0,
            Math.Max(0, textureWidth - 2));
        var top = Math.Clamp(
            (int)Math.Round(stage.Top * scaleY),
            0,
            Math.Max(0, textureHeight - 2));
        var right = Math.Clamp(
            (int)Math.Round((stage.Left + stage.Width) * scaleX),
            left + 2,
            textureWidth);
        var bottom = Math.Clamp(
            (int)Math.Round((stage.Top + stage.Height) * scaleY),
            top + 2,
            textureHeight);

        var stagePixels = Rectangle.FromLTRB(left, top, right, bottom);
        if ((stagePixels.Width & 1) != 0) stagePixels.Width -= 1;
        if (stagePixels.Width < 4 || stagePixels.Height < 2)
        {
            BeginGpuStereoV141HideAndRestore(serial, false, "invalid-stage-pixels");
            return true;
        }

        EnsureStereoGpuSharedTextureLocked(cefTexture.Description);
        if (_stereoGpuSharedTexture is null ||
            _stereoGpuSharedMutex is null ||
            _stereoGpuSharedHandle == IntPtr.Zero)
        {
            BeginGpuStereoV141HideAndRestore(serial, false, "shared-texture-missing");
            return true;
        }

        try
        {
            _stereoGpuSharedMutex.Acquire(0, 0);
        }
        catch
        {
            _gpuStereoV141Telemetry.Event("b-mutex-busy", serial);
            ScheduleGpuStereoV141Invalidate();
            return true;
        }

        var released = false;
        try
        {
            var copyWatch = Stopwatch.StartNew();
            _device!.ImmediateContext.CopyResource(cefTexture, _stereoGpuSharedTexture);
            _device.ImmediateContext.Flush();
            copyWatch.Stop();

            _stereoGpuSharedMutex.Release(1);
            released = true;

            var frame = Interlocked.Increment(ref _stereoGpuFrameNumber);
            _stereoGpuPublisher.Publish(
                _stereoGpuSharedHandle,
                textureWidth,
                textureHeight,
                cefTexture.Description.Format,
                clientSize,
                panel,
                stagePixels,
                frame);

            _gpuShareStatus = "B GPU zero-copy";
            _gpuStereoV141Telemetry.Event(
                "b-gpu-published",
                serial,
                textureWidth,
                textureHeight,
                stagePixels.Width,
                stagePixels.Height,
                copyWatch.Elapsed.TotalMilliseconds,
                $"panel={panel.X}:{panel.Y}:{panel.Width}:{panel.Height}");

            BeginGpuStereoV141HideAndRestore(serial, true, "b-published");
            BeginInvokeSafe(UpdateWindowTitle);
            return true;
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("b-copy-error", serial, detail: ex.Message);
            BeginGpuStereoV141HideAndRestore(serial, false, "b-copy-error");
            return true;
        }
        finally
        {
            if (!released)
            {
                try { _stereoGpuSharedMutex.Release(0); } catch { }
            }
        }
    }

    private void CompleteGpuStereoV141CleanAPaintLocked(bool aGpuPublished)
    {
        if (_gpuStereoV141State != GpuStereoV141State.CaptureCleanAPaint) return;

        var serial = _gpuStereoV141Serial;
        if (!aGpuPublished)
        {
            _gpuStereoV141Telemetry.Event("clean-a-publish-busy", serial);
            ScheduleGpuStereoV141Invalidate();
            return;
        }

        var success = _gpuStereoV141PairSucceeded;
        _gpuStereoV141Telemetry.Event("clean-a-published", serial, detail: success ? "pair-ok" : "pair-failed");

        _gpuStereoV141State = GpuStereoV141State.Idle;
        _gpuStereoV141Serial = -1;
        _gpuStereoV141StageCss = RectangleF.Empty;
        _gpuStereoV141ViewCss = SizeF.Empty;
        _gpuStereoV141PanelSnapshot = Rectangle.Empty;
        _gpuStereoV141ClientSnapshot = Size.Empty;
        _gpuStereoV141PairSucceeded = false;

        ThreadPool.QueueUserWorkItem(_ =>
            ExecuteGpuStereoV141Script(
                $"window.ggqGpuResumeAfterCleanA && window.ggqGpuResumeAfterCleanA({serial},{(success ? "true" : "false")});"));
    }

    private void SetGpuStereoV141UiSuspended(bool suspended)
    {
        ExecuteGpuStereoV141Script(
            $"window.ggqGpuSetSuspended && window.ggqGpuSetSuspended({(suspended ? "true" : "false")});");

        if (!suspended) return;

        _stereoGpuPublisher.SetInactive();
        long serial;
        GpuStereoV141State state;
        lock (_d3dLock)
        {
            serial = _gpuStereoV141Serial;
            state = _gpuStereoV141State;
        }

        if (serial >= 0 && state != GpuStereoV141State.Idle)
        {
            BeginGpuStereoV141HideAndRestore(serial, false, "ui-suspended");
        }
    }

    private void DeactivateGpuStereoV141()
    {
        _stereoGpuPublisher.SetInactive();
        long serial;
        GpuStereoV141State state;
        lock (_d3dLock)
        {
            serial = _gpuStereoV141Serial;
            state = _gpuStereoV141State;
        }

        if (serial >= 0 && state != GpuStereoV141State.Idle)
        {
            BeginGpuStereoV141HideAndRestore(serial, false, "stereo-inactive");
        }
    }

    private void EnsureStereoGpuSharedTextureLocked(Texture2DDescription source)
    {
        if (_device is null) return;

        if (_stereoGpuSharedTexture is not null &&
            _stereoGpuSharedMutex is not null &&
            _stereoGpuSharedTexture.Description.Width == source.Width &&
            _stereoGpuSharedTexture.Description.Height == source.Height &&
            _stereoGpuSharedTexture.Description.Format == source.Format)
        {
            return;
        }

        if (_stereoGpuSharedMutex is not null)
            _retiredSharedResources.Add(_stereoGpuSharedMutex);
        if (_stereoGpuSharedTexture is not null)
            _retiredSharedResources.Add(_stereoGpuSharedTexture);

        _stereoGpuSharedMutex = null;
        _stereoGpuSharedTexture = null;
        _stereoGpuSharedHandle = IntPtr.Zero;

        _stereoGpuSharedTexture = new Texture2D(
            _device,
            new Texture2DDescription
            {
                Width = source.Width,
                Height = source.Height,
                MipLevels = 1,
                ArraySize = 1,
                Format = source.Format,
                SampleDescription = new SampleDescription(1, 0),
                Usage = ResourceUsage.Default,
                BindFlags = BindFlags.ShaderResource,
                CpuAccessFlags = CpuAccessFlags.None,
                OptionFlags = ResourceOptionFlags.SharedKeyedmutex
            });

        _stereoGpuSharedMutex = _stereoGpuSharedTexture.QueryInterface<KeyedMutex>();
        using var dxgiResource =
            _stereoGpuSharedTexture.QueryInterface<SharpDX.DXGI.Resource>();
        _stereoGpuSharedHandle = dxgiResource.SharedHandle;
    }

    private void DisposeGpuStereoV141ResourcesLocked()
    {
        _stereoGpuSharedMutex?.Dispose();
        _stereoGpuSharedTexture?.Dispose();
        _stereoGpuSharedMutex = null;
        _stereoGpuSharedTexture = null;
        _stereoGpuSharedHandle = IntPtr.Zero;
    }
}
'''
p.write_text(host, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Main bridge: add stage-hidden callback and disable the injected Quest
#    virtual keyboard without disturbing the auth popup lifecycle.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
main = p.read_text(encoding='utf-8')

bridge_marker = '''                gpuStereoStagePresented: function (payload) {
                  post({ type: 'gpuStereoStagePresented', payload: String(payload || '') });
                },'''
req(main, bridge_marker, 'v0.14.2: gpuStereoStagePresented bridge missing')
main = main.replace(
    bridge_marker,
    bridge_marker + '''
                gpuStereoStageHidden: function (payload) {
                  post({ type: 'gpuStereoStageHidden', payload: String(payload || '') });
                },''',
    1)

switch_marker = '''                case "gpuStereoStagePresented":
                    HandleGpuStereoV141StagePresented(root);
                    break;'''
req(main, switch_marker, 'v0.14.2: gpuStereoStagePresented switch missing')
main = main.replace(
    switch_marker,
    switch_marker + '''
                case "gpuStereoStageHidden":
                    HandleGpuStereoV141StageHidden(root);
                    break;''',
    1)

keyboard_marker = '              window.__ggqVrKeyboardInstalled = true;\n'
req(main, keyboard_marker, 'v0.14.2: Quest keyboard install marker missing')
main = main.replace(
    keyboard_marker,
    keyboard_marker +
    "              try { var oldKeyboard=document.getElementById('ggq-vr-keyboard'); if(oldKeyboard) oldKeyboard.remove(); } catch (_) {}\n"
    "              return; // v0.14.2: Quest virtual keyboard disabled; use the physical PC keyboard.\n",
    1)

main = main.replace('0.14.1-zero-copy-b', '0.14.2-safe-gpu-b')
main = main.replace('GeoGebraForQuest PC v0.14.1', 'GeoGebraForQuest PC v0.14.2')
main = main.replace('v0.14.1', 'v0.14.2')
p.write_text(main, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) GPU paint path: after stage-hidden, allow a normal A paint through and do
#    not resume stereo until that clean frame has actually been GPU-published.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.Graphics.cs')
g = p.read_text(encoding='utf-8')
req(g, 'TryConsumeGpuStereoV141PaintLocked(cefTexture)', 'v0.14.2: GPU-B paint hook missing')

target_marker = '''                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;

                _device.ImmediateContext.CopyResource(cefTexture, target);'''
req(g, target_marker, 'v0.14.2: A texture copy marker missing')
g = g.replace(
    target_marker,
    '''                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;
                var aGpuPublishedV142 = false;

                _device.ImmediateContext.CopyResource(cefTexture, target);''',
    1)

publish_marker = '                        CompleteGpuPublishLocked(cefTexture.Description);\n'
req(g, publish_marker, 'v0.14.2: A GPU publish completion marker missing')
g = g.replace(
    publish_marker,
    publish_marker + '                        aGpuPublishedV142 = true;\n',
    1)

frame_marker = '                var frame = Interlocked.Increment(ref _gpuFrameNumber);\n'
req(g, frame_marker, 'v0.14.2: A frame marker missing')
g = g.replace(
    frame_marker,
    '                CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142);\n\n' + frame_marker,
    1)
p.write_text(g, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) UI/stereo inactivity must affect the NEW GPU-B publisher, not only the old
#    compatibility MMF writer.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.InputStereo.cs')
i = p.read_text(encoding='utf-8')

inactive_marker = '        _sharedStereoFrames.SetInactive(rect, size);\n    }\n\n    private void SetStereoUiSuspended(bool suspended)'
req(i, inactive_marker, 'v0.14.2: SetStereoInactive marker missing')
i = i.replace(
    inactive_marker,
    '        _sharedStereoFrames.SetInactive(rect, size);\n'
    '        DeactivateGpuStereoV141();\n'
    '    }\n\n'
    '    private void SetStereoUiSuspended(bool suspended)',
    1)

suspend_marker = '''    private void SetStereoUiSuspended(bool suspended)
    {
        _stereoUiSuspended = suspended;
        if (!suspended) return;'''
req(i, suspend_marker, 'v0.14.2: SetStereoUiSuspended marker missing')
i = i.replace(
    suspend_marker,
    '''    private void SetStereoUiSuspended(bool suspended)
    {
        _stereoUiSuspended = suspended;
        SetGpuStereoV141UiSuspended(suspended);
        if (!suspended) return;''',
    1)
p.write_text(i, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) Version/build output and diagnostic name.
# ---------------------------------------------------------------------------
for file in ('pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    q = Path(file)
    text = q.read_text(encoding='utf-8')
    text = text.replace('0.14.1-zero-copy-b', '0.14.2-safe-gpu-b')
    text = text.replace(r'0\.14\.1-zero-copy-b', r'0\.14\.2-safe-gpu-b')
    text = text.replace('v0.14.1', 'v0.14.2')
    text = text.replace(r'v0\.14\.1', r'v0\.14\.2')
    if file.endswith('.csproj'):
        text = re.sub(r'<Version>[^<]+</Version>', '<Version>0.14.2</Version>', text, count=1)
        text = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.14.2.0</FileVersion>', text, count=1)
        text = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.14.2.0</AssemblyVersion>', text, count=1)
    q.write_text(text, encoding='utf-8')

p = Path('pc/GpuStereoV141Telemetry.cs')
t = p.read_text(encoding='utf-8')
t = t.replace('GeoGebraForQuestPC.Performance.GPU-v0141.csv',
              'GeoGebraForQuestPC.Performance.GPU-v0142.csv')
p.write_text(t, encoding='utf-8')

p = Path('pc/LogBundle.cs')
l = p.read_text(encoding='utf-8')
l = l.replace('GeoGebraForQuestPC.Performance.GPU-v0141.csv',
              'GeoGebraForQuestPC.Performance.GPU-v0142.csv')
p.write_text(l, encoding='utf-8')


# ---------------------------------------------------------------------------
# 7) Final hard assertions. These guard against accidentally shipping another
#    v0.14.1-style contaminated-A build.
# ---------------------------------------------------------------------------
runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
main = Path('pc/MainFormV11.cs').read_text(encoding='utf-8')
graphics = Path('pc/MainFormV11.Graphics.cs').read_text(encoding='utf-8')
input_stereo = Path('pc/MainFormV11.InputStereo.cs').read_text(encoding='utf-8')
host = Path('pc/MainFormV141.GpuStereo.cs').read_text(encoding='utf-8')

required = (
    (runtime, 'window.ggqGpuResumeAfterCleanA'),
    (runtime, 'window.ggqGpuSetSuspended'),
    (runtime, "bridge('gpuStereoStageHidden'"),
    (main, 'case "gpuStereoStageHidden":'),
    (main, 'Quest virtual keyboard disabled'),
    (graphics, 'CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142)'),
    (input_stereo, 'DeactivateGpuStereoV141();'),
    (input_stereo, 'SetGpuStereoV141UiSuspended(suspended);'),
    (host, 'AwaitStageHidden'),
    (host, 'CaptureCleanAPaint'),
    (host, '_gpuStereoV141PanelSnapshot'),
    (host, 'clean-a-published'),
    (host, '_stereoGpuPublisher.SetInactive()'),
)
for text, marker in required:
    req(text, marker, 'v0.14.2 final invariant missing: ' + marker)
for forbidden in ('getImageData(', 'readPixels(', "type: 'stereoRawPair'", 'ggqRawStereoAck'):
    if forbidden in runtime:
        raise SystemExit('v0.14.2 forbidden CPU pixel path remains: ' + forbidden)

print('GeoGebraForQuest PC v0.14.2 safe GPU-B latch + clean-A restore + UI suspend + keyboard disable applied')
