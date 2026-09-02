using System.Runtime.InteropServices;
using System.Text.Json;
using CefSharp;
using CefSharp.OffScreen;
using CefSharp.SchemeHandler;
using SharpDX.Direct3D11;
using SharpDX.DXGI;
using D3D11Buffer = SharpDX.Direct3D11.Buffer;
using D3D11Device = SharpDX.Direct3D11.Device;
using D3D11Device1 = SharpDX.Direct3D11.Device1;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm : Form, IRenderHandler
{
    private const string LocalHost = "appassets.androidplatform.net";
    private const string LocalAppUrl = "https://appassets.androidplatform.net/assets/web/index.html";
    private const string PcStereoRuntimeUrl =
        "https://appassets.androidplatform.net/pc-stereo-layout.js?v=0.11.0-cef-gpu-direct";

    private const float BrowserSupersample = 1.35f;
    private const int MaxBrowserWidth = 3072;
    private const int MaxBrowserHeight = 2048;

    private readonly object _d3dLock = new();
    private readonly object _pendingFrameLock = new();
    private readonly object _geometryLock = new();

    private readonly StereoSharedFrameWriter _sharedStereoFrames = new();
    private readonly GpuSharedTexturePublisher _gpuPublisher = new();
    private readonly XrInputSharedReader _xrInput = new();
    private readonly XrCompanionManager _xrCompanion = new();
    private readonly System.Windows.Forms.Timer _inputTimer = new() { Interval = 8 };

    private IRequestContext? _requestContext;
    private D3DChromiumWebBrowser? _browser;

    private D3D11Device? _device;
    private D3D11Device1? _device1;
    private Factory2? _factory;
    private SwapChain1? _swapChain;
    private RenderTargetView? _renderTarget;
    private Query? _copyQuery;
    private VertexShader? _vertexShader;
    private PixelShader? _pixelShader;
    private InputLayout? _inputLayout;
    private D3D11Buffer? _vertexBuffer;
    private SamplerState? _sampler;
    private readonly Texture2D?[] _pcTextures = new Texture2D?[2];
    private readonly ShaderResourceView?[] _pcSrvs = new ShaderResourceView?[2];
    private int _currentPcTexture;

    private Texture2D? _xrSharedTexture;
    private KeyedMutex? _xrSharedMutex;
    private IntPtr _xrSharedHandle;
    private readonly List<IDisposable> _retiredSharedResources = new();

    private Thread? _renderThread;
    private volatile bool _closing;
    private Size _browserSize = new(1280, 720);
    private bool _swapChainResizePending;

    private (string Left, string Right)? _pendingFrames;
    private Rectangle _stereo3DRenderBounds = Rectangle.Empty;
    private bool _stereo3DActive;
    private int _decodeWorkerActive;
    private long _stereoFrameNumber;
    private long _gpuFrameNumber;
    private string _xrStatusText = "Quest hazırlanıyor";
    private bool _xrTriggerDown;
    private bool _xrPointerWasValid;

    public MainForm()
    {
        Text = "GeoGebraForQuest PC · v0.11.0 · CEF GPU Direct";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(1000, 650);
        KeyPreview = true;
        BackColor = Color.Black;
        DoubleBuffered = false;

        _xrCompanion.StatusChanged += XrStatusChanged;
        _inputTimer.Tick += (_, _) => PumpXrPointer();
        Shown += MainFormShown;
        Resize += (_, _) => RequestResize();
        FormClosing += (_, _) => _closing = true;
        FormClosed += (_, _) => Shutdown();
        KeyDown += MainFormKeyDown;
    }

    private void MainFormShown(object? sender, EventArgs e)
    {
        try
        {
            CreateD3D();
            CreateBrowser();
            UpdateBrowserSize();

            _renderThread = new Thread(RenderLoop)
            {
                IsBackground = true,
                Name = "GGQ GPU Present"
            };
            _renderThread.Start();

            _inputTimer.Start();
            _xrCompanion.Start();
            UpdateWindowTitle();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                ex.ToString(),
                "GeoGebraForQuest PC v0.11 başlatma hatası",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private void CreateBrowser()
    {
        var root = AppContext.BaseDirectory;
        var index = Path.Combine(root, "assets", "web", "index.html");
        var runtime = Path.Combine(root, "pc-stereo-layout.js");
        if (!File.Exists(index) || !File.Exists(runtime))
        {
            throw new FileNotFoundException(
                "GeoGebra web assets veya pc-stereo-layout.js bulunamadı.");
        }

        var cache = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "GeoGebraForQuestPC",
            "CEF-Profile");
        Directory.CreateDirectory(cache);

        _requestContext = new RequestContext(new RequestContextSettings { CachePath = cache });
        _requestContext.RegisterSchemeHandlerFactory(
            "https",
            LocalHost,
            new FolderSchemeHandlerFactory(
                rootFolder: root,
                schemeName: "https",
                hostName: LocalHost,
                defaultPage: "index.html"));

        _browser = new D3DChromiumWebBrowser(_requestContext)
        {
            RenderHandler = this
        };
        _browser.JavascriptMessageReceived += BrowserJavascriptMessageReceived;
        _browser.FrameLoadEnd += BrowserFrameLoadEnd;
        _browser.LoadError += (_, args) =>
        {
            if (!_closing && args.ErrorCode != CefErrorCode.Aborted)
            {
                BeginInvokeSafe(() =>
                    Text = $"GeoGebraForQuest PC v0.11 · CEF load error: {args.ErrorText}");
            }
        };
        _browser.Load(LocalAppUrl);
    }

    private void BrowserFrameLoadEnd(object? sender, FrameLoadEndEventArgs e)
    {
        if (!e.Frame.IsMain || _closing) return;

        var runtimeUrl = JsonSerializer.Serialize(PcStereoRuntimeUrl);
        var script = $$"""
            (function () {
              function post(message) {
                try {
                  if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
                    window.CefSharp.PostMessage(message); return;
                  }
                  if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
                    window.cefSharp.postMessage(message);
                  }
                } catch (_) {}
              }

              window.QuestBridge = {
                __pcCefGpuV11: true,
                updateStereoLayout: function (json) {
                  post({ type: 'stereoLayout', payload: String(json || '') });
                },
                updateStereoEyes: function (left, right) {
                  post({ type: 'stereoEyes', left: String(left || ''), right: String(right || '') });
                },
                stereoInactive: function () { post({ type: 'stereoInactive' }); },
                setDepthPointerActive: function () {},
                panelReady: function () { post({ type: 'panelReady' }); },
                getStereoDebugStatus: function () {
                  return JSON.stringify({
                    platform: 'GeoGebraForQuest PC',
                    version: '0.11.0-cef-gpu-direct',
                    presentation: 'CEF D3D11 shared texture -> PC + OpenXR; B=Exp46 L/R'
                  });
                }
              };

              function resizeGeoGebra() {
                try {
                  if (window.ggbApplet && typeof window.ggbApplet.setSize === 'function') {
                    window.ggbApplet.setSize(
                      Math.max(320, Math.floor(window.innerWidth)),
                      Math.max(240, Math.floor(window.innerHeight))
                    );
                  }
                } catch (_) {}
              }
              addEventListener('resize', resizeGeoGebra, { passive: true });
              setTimeout(resizeGeoGebra, 250);
              setTimeout(resizeGeoGebra, 1200);

              var old = document.getElementById('ggq-pc-stereo-v11');
              if (old) old.remove();
              var tag = document.createElement('script');
              tag.id = 'ggq-pc-stereo-v11';
              tag.src = {{runtimeUrl}};
              tag.async = false;
              tag.onerror = function () {
                post({ type: 'runtimeError', message: 'pc-stereo-layout.js yüklenemedi' });
              };
              (document.head || document.documentElement).appendChild(tag);
            })();
            """;

        e.Frame.ExecuteJavaScriptAsync(script);
    }

    private void BrowserJavascriptMessageReceived(
        object? sender,
        JavascriptMessageReceivedEventArgs e)
    {
        try
        {
            var json = JsonSerializer.Serialize(e.Message);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("type", out var typeNode)) return;

            switch (typeNode.GetString())
            {
                case "panelReady":
                    BeginInvokeSafe(UpdateWindowTitle);
                    break;
                case "stereoInactive":
                    SetStereoInactive();
                    break;
                case "stereoLayout":
                    if (root.TryGetProperty("payload", out var payload))
                        HandleStereoLayout(payload.GetString());
                    break;
                case "stereoEyes":
                    if (!root.TryGetProperty("left", out var leftNode) ||
                        !root.TryGetProperty("right", out var rightNode)) return;
                    var left = leftNode.GetString();
                    var right = rightNode.GetString();
                    if (!string.IsNullOrWhiteSpace(left) &&
                        !string.IsNullOrWhiteSpace(right))
                        QueueStereoFrames(left, right);
                    break;
                case "runtimeError":
                    if (root.TryGetProperty("message", out var message))
                    {
                        BeginInvokeSafe(() =>
                            Text = "GeoGebraForQuest PC v0.11 · " + message.GetString());
                    }
                    break;
            }
        }
        catch (Exception ex)
        {
            BeginInvokeSafe(() =>
                Text = "GeoGebraForQuest PC v0.11 · JS bridge: " + ex.Message);
        }
    }

    private void HandleStereoLayout(string? payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            var active = root.TryGetProperty("active", out var activeNode) &&
                         activeNode.GetBoolean();
            if (!active || !root.TryGetProperty("stereo", out var stereo))
            {
                SetStereoInactive();
                return;
            }

            var viewWidth = root.TryGetProperty("viewWidth", out var vw) ? vw.GetDouble() : 0;
            var viewHeight = root.TryGetProperty("viewHeight", out var vh) ? vh.GetDouble() : 0;
            if (viewWidth < 2 || viewHeight < 2) return;

            var left = stereo.GetProperty("left").GetDouble();
            var top = stereo.GetProperty("top").GetDouble();
            var width = stereo.GetProperty("width").GetDouble();
            var height = stereo.GetProperty("height").GetDouble();
            if (width < 2 || height < 2) return;

            Size renderSize;
            lock (_geometryLock) renderSize = _browserSize;
            var sx = renderSize.Width / viewWidth;
            var sy = renderSize.Height / viewHeight;

            var rect = new Rectangle(
                (int)Math.Round(left * sx),
                (int)Math.Round(top * sy),
                Math.Max(2, (int)Math.Round(width * sx)),
                Math.Max(2, (int)Math.Round(height * sy)));

            lock (_geometryLock)
            {
                _stereo3DRenderBounds = rect;
                _stereo3DActive = true;
            }
        }
        catch (Exception ex)
        {
            BeginInvokeSafe(() =>
                Text = "GeoGebraForQuest PC v0.11 · 3D rect: " + ex.Message);
        }
    }

    private void XrStatusChanged(string text)
    {
        _xrStatusText = text;
        BeginInvokeSafe(UpdateWindowTitle);
    }

    private void UpdateWindowTitle()
    {
        if (_closing || IsDisposed) return;
        bool stereo;
        Rectangle rect;
        Size render;
        lock (_geometryLock)
        {
            stereo = _stereo3DActive;
            rect = _stereo3DRenderBounds;
            render = _browserSize;
        }

        Text = $"GeoGebraForQuest PC v0.11 · CEF GPU Direct · " +
               $"A {render.Width}×{render.Height} GPU#{_gpuFrameNumber} · " +
               (stereo
                   ? $"B {rect.Width}×{rect.Height} stereo#{_stereoFrameNumber}"
                   : "B bekleniyor") +
               $" · Quest: {_xrStatusText}";
    }

    private void Shutdown()
    {
        _closing = true;
        _inputTimer.Stop();
        _xrCompanion.Dispose();
        _gpuPublisher.SetInactive();
        _sharedStereoFrames.Dispose();
        _gpuPublisher.Dispose();
        _xrInput.Dispose();

        try
        {
            _browser?.GetBrowserHost()?.CloseBrowser(true);
            _browser?.Dispose();
        }
        catch { }
        _browser = null;

        if (_renderThread is not null && _renderThread.IsAlive)
        {
            try { _renderThread.Join(1500); } catch { }
        }

        lock (_d3dLock)
        {
            foreach (var srv in _pcSrvs) srv?.Dispose();
            foreach (var tex in _pcTextures) tex?.Dispose();
            _xrSharedMutex?.Dispose();
            _xrSharedTexture?.Dispose();
            foreach (var retired in _retiredSharedResources) retired.Dispose();
            _copyQuery?.Dispose();
            _sampler?.Dispose();
            _vertexBuffer?.Dispose();
            _inputLayout?.Dispose();
            _pixelShader?.Dispose();
            _vertexShader?.Dispose();
            _renderTarget?.Dispose();
            _swapChain?.Dispose();
            _factory?.Dispose();
            _device1?.Dispose();
            _device?.Dispose();
        }

        _requestContext?.Dispose();
    }

    private void BeginInvokeSafe(Action action)
    {
        if (_closing || IsDisposed || !IsHandleCreated) return;
        try
        {
            if (InvokeRequired) BeginInvoke(action); else action();
        }
        catch { }
    }
}
