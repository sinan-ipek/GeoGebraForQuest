using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace GeoGebraForQuest.PC;

internal sealed class MainForm : Form
{
    private const string LocalHost = "appassets.androidplatform.net";
    private const string LocalAppUrl = "https://appassets.androidplatform.net/assets/web/index.html";
    private const string PcStereoRuntimeUrl =
        "https://appassets.androidplatform.net/pc-stereo-layout.js?v=0.5.0-highres-sbs";
    private const string RemoteLoginCallback =
        "https://www.geogebra.org/apps/latest/web3d/html/ggtcallback.html";

    private readonly WebView2 _webView = new() { Dock = DockStyle.Fill };
    private readonly StereoSharedFrameWriter _sharedFrames = new();
    private readonly XrCompanionManager _xrCompanion = new();
    private readonly object _pendingFrameLock = new();
    private readonly object _geometryLock = new();

    private CoreWebView2Environment? _environment;
    private (string Left, string Right)? _pendingFrames;
    private Rectangle _stereo3DClientBounds = Rectangle.Empty;
    private bool _stereo3DActive;
    private int _decodeWorkerActive;
    private long _frameNumber;
    private bool _closing;
    private string _xrStatusText = "Quest hazırlanıyor";

    public MainForm()
    {
        Text = "GeoGebraForQuest PC v0.5.0 · High-Res SBS · Exp46";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(1000, 650);
        KeyPreview = true;

        Controls.Add(_webView);

        _xrCompanion.StatusChanged += XrStatusChanged;

        Shown += async (_, _) =>
        {
            await InitializeWebViewAsync();
            _xrCompanion.Start();
            UpdateWindowTitle();
        };

        KeyDown += MainFormKeyDown;
        Resize += (_, _) => PublishCurrentGeometryInactiveDuringResize();

        FormClosing += (_, _) => _closing = true;
        FormClosed += (_, _) =>
        {
            _xrCompanion.Dispose();
            _sharedFrames.Dispose();
            _webView.Dispose();
        };
    }

    private async void MainFormKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Control && e.KeyCode == Keys.O)
        {
            e.SuppressKeyPress = true;
            await OpenLocalFileAsync();
            return;
        }

        if (e.Control && e.KeyCode == Keys.S)
        {
            e.SuppressKeyPress = true;
            await SaveLocalFileAsync();
            return;
        }

        if (e.KeyCode == Keys.F5)
        {
            e.SuppressKeyPress = true;
            _webView.CoreWebView2?.Reload();
            return;
        }

        if (e.KeyCode == Keys.F9)
        {
            e.SuppressKeyPress = true;
            if (_xrCompanion.IsRunning)
            {
                _xrCompanion.Stop();
            }
            else
            {
                _xrCompanion.Start();
            }
            UpdateWindowTitle();
            return;
        }

        if (e.KeyCode == Keys.F12)
        {
            e.SuppressKeyPress = true;
            _webView.CoreWebView2?.OpenDevToolsWindow();
        }
    }

    private async Task InitializeWebViewAsync()
    {
        try
        {
            var index = Path.Combine(AppContext.BaseDirectory, "assets", "web", "index.html");
            var boot = Path.Combine(
                AppContext.BaseDirectory,
                "assets",
                "web",
                "GeoGebra",
                "web3d",
                "web3d.nocache.js");
            var pcStereoRuntime = Path.Combine(AppContext.BaseDirectory, "pc-stereo-layout.js");

            if (!File.Exists(index) || !File.Exists(boot) || !File.Exists(pcStereoRuntime))
            {
                MessageBox.Show(
                    this,
                    "GeoGebraForQuest PC v0.5.0 paketi eksik.\n\n" +
                    "index.html, web3d.nocache.js ve pc-stereo-layout.js dosyaları birlikte bulunmalıdır.",
                    "GeoGebraForQuest PC",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }

            var userData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "GeoGebraForQuestPC",
                "WebView2");
            Directory.CreateDirectory(userData);

            _environment = await CoreWebView2Environment.CreateAsync(null, userData);
            await _webView.EnsureCoreWebView2Async(_environment);

            ConfigureCore(_webView.CoreWebView2, isMain: true);
            await InstallBridgeAsync(_webView.CoreWebView2);

            _webView.CoreWebView2.Navigate(LocalAppUrl);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                ex.ToString(),
                "GeoGebraForQuest PC başlatma hatası",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private void ConfigureCore(CoreWebView2 core, bool isMain)
    {
        core.SetVirtualHostNameToFolderMapping(
            LocalHost,
            AppContext.BaseDirectory,
            CoreWebView2HostResourceAccessKind.Allow);

        core.Settings.IsScriptEnabled = true;
        core.Settings.AreDefaultContextMenusEnabled = true;
        core.Settings.AreDevToolsEnabled = true;
        core.Settings.AreBrowserAcceleratorKeysEnabled = true;
        core.Settings.IsZoomControlEnabled = true;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreHostObjectsAllowed = true;

        core.NavigationStarting += NavigationStarting;
        core.NewWindowRequested += NewWindowRequested;

        if (isMain)
        {
            core.WebMessageReceived += WebMessageReceived;
            core.NavigationCompleted += async (_, e) =>
            {
                if (!e.IsSuccess)
                {
                    Text = $"GeoGebraForQuest PC v0.5.0 · Sayfa hatası: {e.WebErrorStatus}";
                    return;
                }

                await InjectPcRuntimeAsync();
            };
        }
    }

    private async Task InstallBridgeAsync(CoreWebView2 core)
    {
        const string script = """
            (function () {
              if (window.QuestBridge && window.QuestBridge.__pcBridgeV5) return;

              function send(message) {
                try { window.chrome.webview.postMessage(message); } catch (e) {}
              }

              window.QuestBridge = {
                __pcBridgeV5: true,
                updateStereoLayout: function (json) {
                  send({ type: 'stereoLayout', payload: String(json || '') });
                },
                updateStereoEyes: function (left, right) {
                  send({ type: 'stereoEyes', left: String(left || ''), right: String(right || '') });
                },
                stereoInactive: function () {
                  send({ type: 'stereoInactive' });
                },
                setDepthPointerActive: function () {},
                getStereoDebugStatus: function () {
                  return JSON.stringify({
                    platform: 'GeoGebraForQuest PC',
                    version: '0.5.0-exp46-highres-sbs',
                    presentation: 'PC normal GeoGebra; Quest normal GeoGebra + high-resolution SBS 3D overlay'
                  });
                },
                panelReady: function () {
                  send({ type: 'panelReady' });
                }
              };
            })();
            """;

        await core.AddScriptToExecuteOnDocumentCreatedAsync(script);
    }

    private async Task InjectPcRuntimeAsync()
    {
        if (_webView.CoreWebView2 is null) return;

        var stereoUrl = JsonSerializer.Serialize(PcStereoRuntimeUrl);
        var script = $$"""
            (function () {
              if (!window.__ggqPcResizeInstalled) {
                window.__ggqPcResizeInstalled = true;

                function resizeGeoGebra() {
                  try {
                    if (window.ggbApplet && typeof window.ggbApplet.setSize === 'function') {
                      window.ggbApplet.setSize(
                        Math.max(320, Math.floor(window.innerWidth)),
                        Math.max(240, Math.floor(window.innerHeight))
                      );
                    }
                  } catch (e) {}
                }

                addEventListener('resize', resizeGeoGebra, { passive: true });
                if (window.ResizeObserver) {
                  var observer = new ResizeObserver(resizeGeoGebra);
                  observer.observe(document.documentElement);
                  if (document.body) observer.observe(document.body);
                }
                setInterval(resizeGeoGebra, 1000);
                setTimeout(resizeGeoGebra, 400);
                setTimeout(resizeGeoGebra, 1600);
              }

              if (!document.getElementById('ggq-pc-stereo-v5')) {
                var tag = document.createElement('script');
                tag.id = 'ggq-pc-stereo-v5';
                tag.src = {{stereoUrl}};
                tag.async = false;
                tag.onerror = function () {
                  try {
                    window.chrome.webview.postMessage({
                      type: 'runtimeError',
                      message: 'pc-stereo-layout.js yüklenemedi'
                    });
                  } catch (e) {}
                };
                (document.head || document.documentElement).appendChild(tag);
              }
            })();
            """;

        await _webView.CoreWebView2.ExecuteScriptAsync(script);
    }

    private void NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri)) return;
        if (!uri.Host.Equals(LocalHost, StringComparison.OrdinalIgnoreCase)) return;
        if (!uri.AbsolutePath.EndsWith("/ggtcallback.html", StringComparison.OrdinalIgnoreCase)) return;

        e.Cancel = true;
        if (sender is CoreWebView2 core)
        {
            core.Navigate(RemoteLoginCallback + uri.Query);
        }
    }

    private async void NewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        if (_environment is null) return;

        var deferral = e.GetDeferral();
        try
        {
            var popup = new PopupForm(_environment, core => ConfigureCore(core, isMain: false));
            await popup.InitializeAsync();
            e.NewWindow = popup.WebView.CoreWebView2;
            e.Handled = true;
            popup.Show(this);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Popup açılamadı", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            deferral.Complete();
        }
    }

    private void WebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            using var json = JsonDocument.Parse(e.WebMessageAsJson);
            var root = json.RootElement;
            if (!root.TryGetProperty("type", out var typeNode)) return;

            switch (typeNode.GetString())
            {
                case "panelReady":
                    UpdateWindowTitle();
                    break;

                case "stereoInactive":
                    SetStereoInactive();
                    break;

                case "stereoLayout":
                    if (root.TryGetProperty("payload", out var payloadNode))
                    {
                        HandleStereoLayout(payloadNode.GetString());
                    }
                    break;

                case "stereoEyes":
                    if (!root.TryGetProperty("left", out var leftNode) ||
                        !root.TryGetProperty("right", out var rightNode)) return;

                    var left = leftNode.GetString();
                    var right = rightNode.GetString();
                    if (!string.IsNullOrWhiteSpace(left) && !string.IsNullOrWhiteSpace(right))
                    {
                        QueueStereoFrames(left, right);
                    }
                    break;

                case "runtimeError":
                    if (root.TryGetProperty("message", out var messageNode))
                    {
                        Text = "GeoGebraForQuest PC v0.5.0 · " +
                            (messageNode.GetString() ?? "Runtime hatası");
                    }
                    break;
            }
        }
        catch (Exception ex)
        {
            Text = "GeoGebraForQuest PC v0.5.0 · Bridge: " + ex.Message;
        }
    }

    private void HandleStereoLayout(string? payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return;

        try
        {
            using var layout = JsonDocument.Parse(payload);
            var root = layout.RootElement;
            var active = root.TryGetProperty("active", out var activeNode) && activeNode.GetBoolean();

            if (!active || !root.TryGetProperty("stereo", out var stereoNode))
            {
                SetStereoInactive();
                return;
            }

            var viewWidth = root.TryGetProperty("viewWidth", out var vw) ? vw.GetDouble() : 0;
            var viewHeight = root.TryGetProperty("viewHeight", out var vh) ? vh.GetDouble() : 0;
            if (viewWidth < 2 || viewHeight < 2) return;

            var left = stereoNode.GetProperty("left").GetDouble();
            var top = stereoNode.GetProperty("top").GetDouble();
            var width = stereoNode.GetProperty("width").GetDouble();
            var height = stereoNode.GetProperty("height").GetDouble();
            if (width < 2 || height < 2) return;

            var scaleX = _webView.ClientSize.Width / viewWidth;
            var scaleY = _webView.ClientSize.Height / viewHeight;

            var webRect = new Rectangle(
                (int)Math.Round(left * scaleX),
                (int)Math.Round(top * scaleY),
                Math.Max(2, (int)Math.Round(width * scaleX)),
                Math.Max(2, (int)Math.Round(height * scaleY)));

            var screenOrigin = _webView.PointToScreen(webRect.Location);
            var clientOrigin = PointToClient(screenOrigin);
            var formRect = new Rectangle(clientOrigin, webRect.Size);

            lock (_geometryLock)
            {
                _stereo3DClientBounds = formRect;
                _stereo3DActive = true;
            }
        }
        catch (Exception ex)
        {
            Text = "GeoGebraForQuest PC v0.5.0 · 3D konum: " + ex.Message;
        }
    }

    private void SetStereoInactive()
    {
        Rectangle bounds;
        lock (_geometryLock)
        {
            bounds = _stereo3DClientBounds;
            _stereo3DActive = false;
        }

        _sharedFrames.SetInactive(bounds, ClientSize);
        UpdateWindowTitle();
    }

    private void PublishCurrentGeometryInactiveDuringResize()
    {
        if (_closing || IsDisposed) return;

        Rectangle bounds;
        lock (_geometryLock)
        {
            bounds = _stereo3DClientBounds;
            _stereo3DActive = false;
        }

        _sharedFrames.SetInactive(bounds, ClientSize);
    }

    private void QueueStereoFrames(string left, string right)
    {
        lock (_pendingFrameLock)
        {
            _pendingFrames = (left, right);
        }

        if (Interlocked.CompareExchange(ref _decodeWorkerActive, 1, 0) == 0)
        {
            _ = Task.Run(DecodeFrameLoop);
        }
    }

    private void DecodeFrameLoop()
    {
        try
        {
            while (!_closing)
            {
                (string Left, string Right)? current;
                lock (_pendingFrameLock)
                {
                    current = _pendingFrames;
                    _pendingFrames = null;
                }

                if (current is null) break;

                Bitmap? left = null;
                Bitmap? right = null;

                try
                {
                    left = DecodeDataUrl(current.Value.Left);
                    right = DecodeDataUrl(current.Value.Right);
                    var number = Interlocked.Increment(ref _frameNumber);
                    var geometry = GetGeometrySnapshot();

                    if (geometry.Active &&
                        geometry.PanelBounds.Width > 1 &&
                        geometry.PanelBounds.Height > 1 &&
                        geometry.ClientSize.Width > 1 &&
                        geometry.ClientSize.Height > 1)
                    {
                        _sharedFrames.WriteFrames(
                            left,
                            right,
                            geometry.PanelBounds,
                            geometry.ClientSize,
                            number);
                    }

                    left.Dispose();
                    right.Dispose();
                    left = null;
                    right = null;

                    if (!_closing && !IsDisposed && number % 20 == 0)
                    {
                        try { BeginInvoke((Action)UpdateWindowTitle); } catch { }
                    }
                }
                catch (Exception ex)
                {
                    left?.Dispose();
                    right?.Dispose();
                    if (!_closing && !IsDisposed)
                    {
                        try
                        {
                            BeginInvoke((Action)(() =>
                                Text = "GeoGebraForQuest PC v0.5.0 · Stereo decode: " + ex.Message));
                        }
                        catch { }
                    }
                }
            }
        }
        finally
        {
            Interlocked.Exchange(ref _decodeWorkerActive, 0);
            lock (_pendingFrameLock)
            {
                if (!_closing &&
                    _pendingFrames is not null &&
                    Interlocked.CompareExchange(ref _decodeWorkerActive, 1, 0) == 0)
                {
                    _ = Task.Run(DecodeFrameLoop);
                }
            }
        }
    }

    private (bool Active, Rectangle PanelBounds, Size ClientSize) GetGeometrySnapshot()
    {
        if (_closing || IsDisposed) return (false, Rectangle.Empty, Size.Empty);

        if (InvokeRequired)
        {
            try
            {
                return ((bool Active, Rectangle PanelBounds, Size ClientSize))Invoke(
                    new Func<(bool Active, Rectangle PanelBounds, Size ClientSize)>(GetGeometrySnapshot));
            }
            catch
            {
                return (false, Rectangle.Empty, Size.Empty);
            }
        }

        lock (_geometryLock)
        {
            return (_stereo3DActive, _stereo3DClientBounds, ClientSize);
        }
    }

    private static Bitmap DecodeDataUrl(string dataUrl)
    {
        var comma = dataUrl.IndexOf(',');
        if (comma < 0 || comma == dataUrl.Length - 1)
        {
            throw new InvalidDataException("Geçersiz image data URL");
        }

        var bytes = Convert.FromBase64String(dataUrl[(comma + 1)..]);
        using var stream = new MemoryStream(bytes, writable: false);
        using var source = Image.FromStream(stream, false, false);
        return new Bitmap(source);
    }

    private async Task OpenLocalFileAsync()
    {
        if (_webView.CoreWebView2 is null) return;

        using var dialog = new OpenFileDialog
        {
            Title = "GeoGebra dosyası aç",
            Filter = "GeoGebra dosyası (*.ggb)|*.ggb|Tüm dosyalar (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        try
        {
            var base64 = Convert.ToBase64String(await File.ReadAllBytesAsync(dialog.FileName));
            var encoded = JsonSerializer.Serialize(base64);
            var result = await _webView.CoreWebView2.ExecuteScriptAsync($$"""
                (function () {
                  if (!window.ggbApplet || typeof window.ggbApplet.setBase64 !== 'function') {
                    return 'NOT_READY';
                  }
                  window.ggbApplet.setBase64({{encoded}});
                  return 'OK';
                })();
                """);

            var state = JsonSerializer.Deserialize<string>(result);
            if (state != "OK") throw new InvalidOperationException("GeoGebra henüz hazır değil.");
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                ex.Message,
                "Dosya açılamadı",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private async Task SaveLocalFileAsync()
    {
        if (_webView.CoreWebView2 is null) return;

        using var dialog = new SaveFileDialog
        {
            Title = "GeoGebra dosyasını kaydet",
            Filter = "GeoGebra dosyası (*.ggb)|*.ggb",
            DefaultExt = "ggb",
            AddExtension = true,
            FileName = "GeoGebra.ggb"
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        try
        {
            var result = await _webView.CoreWebView2.ExecuteScriptAsync("""
                (function () {
                  if (!window.ggbApplet || typeof window.ggbApplet.getBase64 !== 'function') {
                    return 'NOT_READY';
                  }
                  return window.ggbApplet.getBase64();
                })();
                """);

            var base64 = JsonSerializer.Deserialize<string>(result);
            if (string.IsNullOrWhiteSpace(base64) || base64 == "NOT_READY")
            {
                throw new InvalidOperationException("GeoGebra henüz hazır değil.");
            }

            await File.WriteAllBytesAsync(dialog.FileName, Convert.FromBase64String(base64));
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                ex.Message,
                "Dosya kaydedilemedi",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private void XrStatusChanged(string text)
    {
        if (_closing || IsDisposed) return;

        if (InvokeRequired)
        {
            try { BeginInvoke((Action)(() => XrStatusChanged(text))); } catch { }
            return;
        }

        _xrStatusText = text;
        UpdateWindowTitle();
    }

    private void UpdateWindowTitle()
    {
        if (_closing || IsDisposed) return;

        bool active;
        Rectangle bounds;
        lock (_geometryLock)
        {
            active = _stereo3DActive;
            bounds = _stereo3DClientBounds;
        }

        var stereo = active
            ? $"3D stereo hedefi {bounds.Width}×{bounds.Height} · kare {_frameNumber}"
            : "3D stereo bekleniyor";

        Text = $"GeoGebraForQuest PC v0.5.0 · High-Res SBS · {stereo} · Quest: {_xrStatusText}";
    }
}
