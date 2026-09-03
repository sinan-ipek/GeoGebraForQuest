using System.Runtime.InteropServices;
using CefSharp;
using CefSharp.Enums;
using CefSharp.Structs;
using SharpDX;
using SharpDX.D3DCompiler;
using SharpDX.Direct3D;
using SharpDX.Direct3D11;
using SharpDX.DXGI;
using D3D11Buffer = SharpDX.Direct3D11.Buffer;
using D3D11Device = SharpDX.Direct3D11.Device;
using D3D11Device1 = SharpDX.Direct3D11.Device1;
using D3D11Resource = SharpDX.Direct3D11.Resource;
using CefRange = CefSharp.Structs.Range;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private static readonly VertexDx11[] FullScreenTriangle =
    {
        new(new Vector4(-1, 1, 0, 1), new Vector2(0, 0)),
        new(new Vector4(3, 1, 0, 1), new Vector2(2, 0)),
        new(new Vector4(-1, -3, 0, 1), new Vector2(0, 2))
    };

    private void CreateD3D()
    {
        lock (_d3dLock)
        {
            _device = new D3D11Device(
                DriverType.Hardware,
                DeviceCreationFlags.BgraSupport);
            _device1 = _device.QueryInterface<D3D11Device1>();

            using var dxgiDevice = _device.QueryInterface<SharpDX.DXGI.Device>();
            using var adapter = dxgiDevice.Adapter;
            _factory = adapter.GetParent<Factory2>();

            CreateSwapChainLocked();
            CreateShadersLocked();
        }
    }

    private void CreateSwapChainLocked()
    {
        if (_device is null || _factory is null) return;

        _renderTarget?.Dispose();
        _renderTarget = null;
        _swapChain?.Dispose();
        _swapChain = null;

        var desc = new SwapChainDescription1
        {
            Width = Math.Max(2, ClientSize.Width),
            Height = Math.Max(2, ClientSize.Height),
            Format = Format.B8G8R8A8_UNorm,
            Stereo = false,
            SampleDescription = new SampleDescription(1, 0),
            Usage = Usage.RenderTargetOutput,
            BufferCount = 2,
            Scaling = Scaling.Stretch,
            SwapEffect = SwapEffect.FlipDiscard,
            AlphaMode = AlphaMode.Ignore,
            Flags = SwapChainFlags.None
        };

        _swapChain = new SwapChain1(_factory, _device, Handle, ref desc);
        RecreateRenderTargetLocked();
    }

    private void RecreateRenderTargetLocked()
    {
        if (_device is null || _swapChain is null) return;
        _renderTarget?.Dispose();
        using var backBuffer = D3D11Resource.FromSwapChain<Texture2D>(_swapChain, 0);
        _renderTarget = new RenderTargetView(_device, backBuffer);
        _device.ImmediateContext.Rasterizer.SetViewport(
            new Viewport(
                0,
                0,
                Math.Max(2, ClientSize.Width),
                Math.Max(2, ClientSize.Height),
                0,
                1));
    }

    private void ResizeSwapChainLocked()
    {
        if (_swapChain is null || _device is null) return;
        var context = _device.ImmediateContext;
        context.ClearState();
        context.Flush();
        _renderTarget?.Dispose();
        _renderTarget = null;
        _swapChain.ResizeBuffers(
            2,
            Math.Max(2, ClientSize.Width),
            Math.Max(2, ClientSize.Height),
            Format.B8G8R8A8_UNorm,
            SwapChainFlags.None);
        RecreateRenderTargetLocked();
        _swapChainResizePending = false;
    }

    private void CreateShadersLocked()
    {
        if (_device is null) return;

        const string shader = """
            Texture2D tex0 : register(t0);
            SamplerState samp0 : register(s0);
            struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD; };
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            PSIn VSMain(VSIn input) { PSIn o; o.pos=input.pos; o.uv=input.uv; return o; }
            float4 PSMain(PSIn input) : SV_Target {
                float4 c = tex0.Sample(samp0, input.uv);
                return float4(c.rgb, 1.0);
            }
            """;

        using var vsBytecode = ShaderBytecode.Compile(shader, "VSMain", "vs_4_0_level_9_1");
        using var psBytecode = ShaderBytecode.Compile(shader, "PSMain", "ps_4_0_level_9_1");
        _vertexShader = new VertexShader(_device, vsBytecode);
        _pixelShader = new PixelShader(_device, psBytecode);
        using var signature = ShaderSignature.GetInputSignature(vsBytecode);
        _inputLayout = new InputLayout(
            _device,
            signature,
            new[]
            {
                new InputElement("POSITION", 0, Format.R32G32B32A32_Float, 0, 0),
                new InputElement("TEXCOORD", 0, Format.R32G32_Float, 16, 0)
            });

        using var stream = DataStream.Create(FullScreenTriangle, false, false);
        _vertexBuffer = new D3D11Buffer(
            _device,
            stream,
            new BufferDescription
            {
                BindFlags = BindFlags.VertexBuffer,
                SizeInBytes = Marshal.SizeOf<VertexDx11>() * FullScreenTriangle.Length
            });

        _sampler = new SamplerState(
            _device,
            new SamplerStateDescription
            {
                Filter = Filter.MinMagMipLinear,
                AddressU = TextureAddressMode.Clamp,
                AddressV = TextureAddressMode.Clamp,
                AddressW = TextureAddressMode.Clamp,
                MaximumLod = float.MaxValue
            });

        _rasterizer = new RasterizerState(
            _device,
            new RasterizerStateDescription
            {
                FillMode = FillMode.Solid,
                CullMode = CullMode.None,
                IsDepthClipEnabled = true
            });
    }

    private void RenderLoop()
    {
        long lastPresentedFrame = -1;

        while (!_closing)
        {
            try
            {
                var currentFrame = Interlocked.Read(ref _gpuFrameNumber);
                bool resizePending;
                lock (_d3dLock) resizePending = _swapChainResizePending;

                if (currentFrame == lastPresentedFrame && !resizePending)
                {
                    Thread.Sleep(1);
                    continue;
                }

                lock (_d3dLock)
                {
                    if (_device is null || _swapChain is null || _renderTarget is null)
                    {
                        Thread.Sleep(2);
                        continue;
                    }

                    if (_swapChainResizePending) ResizeSwapChainLocked();

                    var context = _device.ImmediateContext;
                    context.OutputMerger.SetRenderTargets(_renderTarget);
                    context.ClearRenderTargetView(_renderTarget, new Color4(0, 0, 0, 1));
                    context.Rasterizer.State = _rasterizer;
                    context.InputAssembler.PrimitiveTopology = PrimitiveTopology.TriangleList;
                    context.InputAssembler.InputLayout = _inputLayout;
                    if (_vertexBuffer is not null)
                    {
                        context.InputAssembler.SetVertexBuffers(
                            0,
                            new VertexBufferBinding(
                                _vertexBuffer,
                                Marshal.SizeOf<VertexDx11>(),
                                0));
                    }
                    context.VertexShader.Set(_vertexShader);
                    context.PixelShader.Set(_pixelShader);
                    context.PixelShader.SetSampler(0, _sampler);

                    var srv = _pcSrvs[_currentPcTexture];
                    if (srv is not null)
                    {
                        context.PixelShader.SetShaderResource(0, srv);
                        context.Draw(FullScreenTriangle.Length, 0);
                        context.PixelShader.SetShaderResource(0, null);
                    }

                    _swapChain.Present(0, PresentFlags.None);
                    lastPresentedFrame = currentFrame;
                }
            }
            catch (Exception ex)
            {
                if (!_closing)
                {
                    _presentStatus = "Present: " + ShortError(ex);
                    BeginInvokeSafe(UpdateWindowTitle);
                    Thread.Sleep(25);
                }
            }
        }
    }

    public void OnAcceleratedPaint(
        PaintElementType type,
        Rect dirtyRect,
        AcceleratedPaintInfo acceleratedPaintInfo)
    {
        if (_closing || type != PaintElementType.View ||
            _device is null || _device1 is null) return;

        try
        {
            lock (_d3dLock)
            {
                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                EnsurePcTextureLocked(cefTexture.Description);
                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;

                _device.ImmediateContext.CopyResource(cefTexture, target);
                _currentPcTexture = next;

                try
                {
                    if (TryQueueGpuPublishLocked(cefTexture))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(cefTexture.Description);
                        if (_gpuShareStatus != "A-share GPU")
                        {
                            _gpuShareStatus = "A-share GPU";
                            BeginInvokeSafe(UpdateWindowTitle);
                        }
                    }
                }
                catch (Exception shareError)
                {
                    try { _xrSharedMutex?.Release(0); } catch { }
                    var status = "A-share: " + ShortError(shareError);
                    if (!string.Equals(_gpuShareStatus, status, StringComparison.Ordinal))
                    {
                        _gpuShareStatus = status;
                        BeginInvokeSafe(UpdateWindowTitle);
                    }
                }

                var frame = Interlocked.Increment(ref _gpuFrameNumber);
                if ((frame % 120) == 0)
                {
                    BeginInvokeSafe(UpdateWindowTitle);
                }
            }
        }
        catch (Exception ex)
        {
            if (!_closing)
            {
                _gpuPaintStatus = "GPU paint: " + ShortError(ex);
                BeginInvokeSafe(UpdateWindowTitle);
            }
        }
    }

    private void EnsurePcTextureLocked(Texture2DDescription source)
    {
        if (_device is null) return;
        for (var i = 0; i < 2; i++)
        {
            var old = _pcTextures[i];
            if (old is not null &&
                old.Description.Width == source.Width &&
                old.Description.Height == source.Height &&
                old.Description.Format == source.Format) continue;

            _pcSrvs[i]?.Dispose();
            _pcSrvs[i] = null;
            old?.Dispose();

            var desc = new Texture2DDescription
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
                OptionFlags = ResourceOptionFlags.None
            };
            _pcTextures[i] = new Texture2D(_device, desc);
            _pcSrvs[i] = new ShaderResourceView(_device, _pcTextures[i]);
        }
    }

    private bool TryQueueGpuPublishLocked(Texture2D cefTexture)
    {
        if (_device is null) return false;
        var source = cefTexture.Description;

        if (_xrSharedTexture is null ||
            _xrSharedTexture.Description.Width != source.Width ||
            _xrSharedTexture.Description.Height != source.Height ||
            _xrSharedTexture.Description.Format != source.Format)
        {
            if (_xrSharedMutex is not null) _retiredSharedResources.Add(_xrSharedMutex);
            if (_xrSharedTexture is not null) _retiredSharedResources.Add(_xrSharedTexture);

            _xrSharedTexture = new Texture2D(
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
            _xrSharedMutex = _xrSharedTexture.QueryInterface<KeyedMutex>();
            using var dxgiResource =
                _xrSharedTexture.QueryInterface<SharpDX.DXGI.Resource>();
            _xrSharedHandle = dxgiResource.SharedHandle;
        }

        if (_xrSharedTexture is null ||
            _xrSharedMutex is null ||
            _xrSharedHandle == IntPtr.Zero) return false;

        try
        {
            _xrSharedMutex.Acquire(0, 0);
        }
        catch
        {
            return false;
        }

        try
        {
            _device.ImmediateContext.CopyResource(cefTexture, _xrSharedTexture);
            return true;
        }
        catch
        {
            try { _xrSharedMutex.Release(0); } catch { }
            throw;
        }
    }

    private void CompleteGpuPublishLocked(Texture2DDescription source)
    {
        if (_xrSharedMutex is null || _xrSharedHandle == IntPtr.Zero) return;
        _xrSharedMutex.Release(1);
        _gpuPublisher.Publish(
            _xrSharedHandle,
            source.Width,
            source.Height,
            source.Format);
    }

    private static string ShortError(Exception ex)
    {
        var text = ex.Message.Replace('\r', ' ').Replace('\n', ' ').Trim();
        if (text.Length > 120) text = text[..120] + "…";
        return text;
    }

    private float GetBrowserDeviceScaleFactor()
    {
        var dpi = DeviceDpi > 0 ? DeviceDpi : 96;
        return Math.Clamp(dpi / 96.0F, 1.0F, 4.0F);
    }

    public ScreenInfo? GetScreenInfo() => new()
    {
        DeviceScaleFactor = GetBrowserDeviceScaleFactor()
    };

    public bool GetScreenPoint(int viewX, int viewY, out int screenX, out int screenY)
    {
        screenX = viewX;
        screenY = viewY;
        return false;
    }

    public Rect GetViewRect()
    {
        System.Drawing.Size size;
        lock (_geometryLock) size = _browserSize;
        return new Rect(0, 0, Math.Max(2, size.Width), Math.Max(2, size.Height));
    }

    public void OnPaint(
        PaintElementType type,
        Rect dirtyRect,
        IntPtr buffer,
        int width,
        int height)
    {
    }

    public void OnCursorChange(IntPtr cursor, CursorType type, CursorInfo customCursorInfo)
    {
        BeginInvokeSafe(() =>
            Cursor = type == CursorType.Hand ? Cursors.Hand : Cursors.Default);
    }

    public void OnPopupShow(bool show)
    {
        SetStereoUiSuspended(show);
    }

    public void OnPopupSize(Rect rect) { }
    public void OnImeCompositionRangeChanged(CefRange selectedRange, Rect[] characterBounds) { }
    public bool StartDragging(IDragData dragData, DragOperationsMask mask, int x, int y) => false;
    public void UpdateDragCursor(DragOperationsMask operation) { }
    public void OnVirtualKeyboardRequested(IBrowser browser, TextInputMode inputMode) { }

    [StructLayout(LayoutKind.Sequential)]
    private readonly struct VertexDx11
    {
        public readonly Vector4 Position;
        public readonly Vector2 TexCoord;

        public VertexDx11(Vector4 position, Vector2 texCoord)
        {
            Position = position;
            TexCoord = texCoord;
        }
    }
}
