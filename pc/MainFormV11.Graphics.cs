using System.Runtime.InteropServices;
using CefSharp;
using CefSharp.Enums;
using CefSharp.Structs;
using SharpDX;
using SharpDX.D3DCompiler;
using SharpDX.Direct3D;
using SharpDX.Direct3D11;
using SharpDX.DXGI;
using SharpDX.Mathematics.Interop;
using D3D11Buffer = SharpDX.Direct3D11.Buffer;
using D3D11Device = SharpDX.Direct3D11.Device;
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
            _device1 = _device.QueryInterface<Device1>();
            _deviceMultithread = _device.QueryInterfaceOrNull<DeviceMultithread>();
            _deviceMultithread?.SetMultithreadProtected(true);

            using var dxgiDevice = _device.QueryInterface<SharpDX.DXGI.Device>();
            using var adapter = dxgiDevice.Adapter;
            _factory = adapter.GetParent<Factory2>();

            CreateSwapChainLocked();
            CreateShadersLocked();
            _copyQuery = new Query(
                _device,
                new QueryDescription { Type = QueryType.Event, Flags = QueryFlags.None });
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
            struct VSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            PSIn VSMain(VSIn input) { PSIn o; o.pos=input.pos; o.uv=input.uv; return o; }
            float4 PSMain(PSIn input) : SV_Target { return tex0.Sample(samp0, input.uv); }
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
                new InputElement("SV_POSITION", 0, Format.R32G32B32A32_Float, 0, 0),
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
    }

    private void RenderLoop()
    {
        while (!_closing)
        {
            try
            {
                _browser?.GetBrowserHost()?.SendExternalBeginFrame();

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

                    _swapChain.Present(1, PresentFlags.None);
                }
            }
            catch (Exception ex)
            {
                if (!_closing)
                {
                    BeginInvokeSafe(() =>
                        Text = "GeoGebraForQuest PC v0.11 · Present: " + ex.Message);
                    Thread.Sleep(50);
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

        var xrCopyQueued = false;
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

                xrCopyQueued = TryQueueGpuPublishLocked(cefTexture);
                _device.ImmediateContext.CopyResource(cefTexture, target);
                WaitForGpuLocked();
                _currentPcTexture = next;

                if (xrCopyQueued)
                {
                    CompleteGpuPublishLocked(cefTexture.Description);
                    xrCopyQueued = false;
                }

                Interlocked.Increment(ref _gpuFrameNumber);
            }
        }
        catch (Exception ex)
        {
            if (xrCopyQueued)
            {
                try { _xrSharedMutex?.Release(0); } catch { }
            }
            if (!_closing)
            {
                BeginInvokeSafe(() =>
                    Text = "GeoGebraForQuest PC v0.11 · GPU paint: " + ex.Message);
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

    private void WaitForGpuLocked()
    {
        if (_device is null || _copyQuery is null) return;
        var context = _device.ImmediateContext;
        context.End(_copyQuery);
        context.Flush();
        RawBool finished = context.GetData<RawBool>(
            _copyQuery,
            AsynchronousFlags.DoNotFlush);
        while (!_closing && !finished)
        {
            Thread.Yield();
            finished = context.GetData<RawBool>(
                _copyQuery,
                AsynchronousFlags.DoNotFlush);
        }
    }

    public ScreenInfo? GetScreenInfo() => new() { DeviceScaleFactor = 1.0F };

    public bool GetScreenPoint(int viewX, int viewY, out int screenX, out int screenY)
    {
        screenX = viewX;
        screenY = viewY;
        return false;
    }

    public Rect GetViewRect()
    {
        Size size;
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
        // SharedTextureEnabled=true: CPU paint path is deliberately unused.
    }

    public void OnCursorChange(IntPtr cursor, CursorType type, CursorInfo customCursorInfo)
    {
        BeginInvokeSafe(() =>
            Cursor = type == CursorType.Hand ? Cursors.Hand : Cursors.Default);
    }

    public void OnPopupShow(bool show) { }
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
