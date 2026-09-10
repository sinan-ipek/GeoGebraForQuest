using System.Diagnostics;
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
        CaptureStagePaint
    }

    private readonly StereoGpuTexturePublisher _stereoGpuPublisher = new();
    private readonly GpuStereoV141Telemetry _gpuStereoV141Telemetry = new();
    private GpuStereoV141State _gpuStereoV141State = GpuStereoV141State.Idle;
    private long _gpuStereoV141Serial = -1;
    private RectangleF _gpuStereoV141StageCss = RectangleF.Empty;
    private SizeF _gpuStereoV141ViewCss = SizeF.Empty;
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

                bool begin = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoV141State == GpuStereoV141State.Idle)
                    {
                        _gpuStereoV141Serial = serial;
                        _gpuStereoV141State = GpuStereoV141State.AwaitStagePresented;
                        begin = true;
                    }
                }
                if (!begin) return;

                _gpuStereoV141Telemetry.Event("pair-ready", serial);
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

                try
                {
                    _browser?.GetBrowserHost()?.Invalidate(PaintElementType.View);
                }
                catch
                {
                }

                ArmGpuStereoV141Watchdog(serial, GpuStereoV141State.CaptureStagePaint);
            }
        }
        catch (Exception ex)
        {
            _gpuStereoV141Telemetry.Event("stage-presented-error", detail: ex.Message);
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

    private void ArmGpuStereoV141Watchdog(long serial, GpuStereoV141State expected)
    {
        _ = Task.Run(async () =>
        {
            await Task.Delay(900).ConfigureAwait(false);
            if (_closing) return;

            bool timeout = false;
            lock (_d3dLock)
            {
                if (_gpuStereoV141Serial == serial &&
                    _gpuStereoV141State == expected)
                {
                    _gpuStereoV141State = GpuStereoV141State.Idle;
                    timeout = true;
                }
            }

            if (!timeout) return;

            _gpuStereoV141Telemetry.Event(
                "phase-timeout",
                serial,
                detail: expected.ToString());
            ExecuteGpuStereoV141Script(
                $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial},false);");
        });
    }

    private bool TryConsumeGpuStereoV141PaintLocked(Texture2D cefTexture)
    {
        if (_gpuStereoV141State == GpuStereoV141State.Idle) return false;

        // While the temporary SBS stage is visible, every CEF paint is hidden from
        // the physical PC swapchain and from the ordinary A publisher. Only the
        // explicitly armed frame below is copied into the B GPU share.
        if (_gpuStereoV141State != GpuStereoV141State.CaptureStagePaint)
        {
            return true;
        }

        var serial = _gpuStereoV141Serial;
        var view = _gpuStereoV141ViewCss;
        var stage = _gpuStereoV141StageCss;
        if (view.Width < 2 || view.Height < 2 || stage.Width < 4 || stage.Height < 2)
        {
            return true;
        }

        EnsureStereoGpuSharedTextureLocked(cefTexture.Description);
        if (_stereoGpuSharedTexture is null ||
            _stereoGpuSharedMutex is null ||
            _stereoGpuSharedHandle == IntPtr.Zero)
        {
            return true;
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

        if (!active || panel.Width < 2 || panel.Height < 2 ||
            clientSize.Width < 2 || clientSize.Height < 2)
        {
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
        if ((stagePixels.Width & 1) != 0)
        {
            stagePixels.Width -= 1;
        }
        if (stagePixels.Width < 4 || stagePixels.Height < 2)
        {
            return true;
        }

        try
        {
            _stereoGpuSharedMutex.Acquire(0, 0);
        }
        catch
        {
            _gpuStereoV141Telemetry.Event("b-mutex-busy", serial);
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

            _gpuStereoV141State = GpuStereoV141State.Idle;
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

            ThreadPool.QueueUserWorkItem(_ =>
                ExecuteGpuStereoV141Script(
                    $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial},true);"));
            BeginInvokeSafe(UpdateWindowTitle);
            return true;
        }
        finally
        {
            if (!released)
            {
                try
                {
                    _stereoGpuSharedMutex.Release(0);
                }
                catch
                {
                }
            }
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
        {
            _retiredSharedResources.Add(_stereoGpuSharedMutex);
        }
        if (_stereoGpuSharedTexture is not null)
        {
            _retiredSharedResources.Add(_stereoGpuSharedTexture);
        }

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
