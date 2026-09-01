using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace GeoGebraForQuest.PC;

internal sealed class MainForm : Form
{
    private const string LocalHost = "appassets.androidplatform.net";
    private const string LocalAppUrl = "https://appassets.androidplatform.net/assets/web/index.html";
    private const string StereoLayoutUrl = "https://appassets.androidplatform.net/assets/web/quest-stereo-layout.js";
    private const string RemoteLoginCallback =
        "https://www.geogebra.org/apps/latest/web3d/html/ggtcallback.html";

    private readonly WebView2 _webView = new() { Dock = DockStyle.Fill };
    private readonly StereoPanelControl _stereoPanel = new() { Dock = DockStyle.Fill };
    private readonly SplitContainer _split = new()
    {
        Dock = DockStyle.Fill,
        Orientation = Orientation.Vertical,
        Panel1MinSize = 640,
        Panel2MinSize = 320,
        SplitterWidth = 6
    };

    private readonly ToolStripStatusLabel _status = new() { Text = "Başlatılıyor…" };
    private readonly ToolStripStatusLabel _xrStatus = new()
    {
        Spring = true,
        TextAlign = ContentAlignment.MiddleCenter,
        Text = "Quest: hazırlanıyor"
    };
    private readonly ToolStripStatusLabel _frameStatus = new()
    {
        TextAlign = ContentAlignment.MiddleRight,
        Text = "Stereo: bekleniyor"
    };

    private readonly StereoSharedFrameWriter _sharedFrames = new();
    private readonly XrCompanionManager _xrCompanion = new();
    private readonly object _pendingFrameLock = new();

    private CoreWebView2Environment? _environment;
    private ToolStripButton? _questButton;
    private (string Left, string Right)? _pendingFrames;
    private int _decodeWorkerActive;
    private long _frameNumber;
    private bool _closing;

    public MainForm()
    {
        Text = "GeoGebraForQuest PC · v0.1.0 · Exp46";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(1200, 720);
        KeyPreview = true;

        _xrCompanion.StatusChanged += XrStatusChanged;

        var tools = BuildToolStrip();
        var statusBar = new StatusStrip();
        statusBar.Items.Add(_status);
        statusBar.Items.Add(_xrStatus);
        statusBar.Items.Add(_frameStatus);

        _split.Panel1.Controls.Add(_webView);
        _split.Panel2.Controls.Add(_stereoPanel);

        Controls.Add(_split);
        Controls.Add(statusBar);
        Controls.Add(tools);

        tools.Dock = DockStyle.Top;
        statusBar.Dock = DockStyle.Bottom;

        Shown += async (_, _) =>
        {
            _split.SplitterDistance = Math.Max(700, (int)(ClientSize.Width * 0.70));
            await InitializeWebViewAsync();

            // The intended UX is automatic PC -> Quest connection. If Quest Link/Air Link
            // is not active, the OpenXR companion exits cleanly and the toolbar button can
            // be used to retry after the headset connection is established.
            _xrCompanion.Start();
            UpdateQuestButton();
        };

        Resize += (_, _) => PublishInactiveGeometryIfNeeded();
        _split.SplitterMoved += (_, _) => PublishInactiveGeometryIfNeeded();

        FormClosing += (_, _) => _closing = true;
        FormClosed += (_, _) =>
        {
            _xrCompanion.Dispose();
            _sharedFrames.Dispose();
            _webView.Dispose();
            _stereoPanel.Dispose();
        };
    }

    private ToolStrip BuildToolStrip()
    {
        var bar = new ToolStrip
        {
            GripStyle = ToolStripGripStyle.Hidden,
            RenderMode = ToolStripRenderMode.System,
            Padding = new Padding(6, 3, 6, 3)
        };

        var open = new ToolStripButton("Yerel Aç")
        {
            ToolTipText = "Yerel .ggb dosyasını Windows dosya seçicisiyle aç"
        };
        var save = new ToolStripButton("Farklı Kaydet")
        {
            ToolTipText = "Etkin GeoGebra çalışmasını .ggb olarak kaydet"
        };
        var reload = new ToolStripButton("Yenile");
        var toggleStereo = new ToolStripButton("B Paneli")
        {
            Checked = true,
            CheckOnClick = true
        };
        var sbsPreview = new ToolStripButton("PC'de SBS")
        {
            Checked = false,
            CheckOnClick = true,
            ToolTipText = "Yalnız PC monitöründeki B önizlemesini L|R yapar; Quest stereo çıkışını değiştirmez"
        };
        _questButton = new ToolStripButton("Quest'e Bağlan")
        {
            ToolTipText = "Etkin OpenXR runtime üzerinden Meta Quest Link/Air Link bağlantısını başlat"
        };
        var devTools = new ToolStripButton("DevTools");

        open.Click += async (_, _) => await OpenLocalFileAsync();
        save.Click += async (_, _) => await SaveLocalFileAsync();
        reload.Click += (_, _) => _webView.CoreWebView2?.Reload();

        toggleStereo.CheckedChanged += (_, _) =>
        {
            _split.Panel2Collapsed = !toggleStereo.Checked;
            PublishInactiveGeometryIfNeeded();
        };

        sbsPreview.CheckedChanged += (_, _) =>
        {
            _stereoPanel.ShowSbsPreview = sbsPreview.Checked;
            _stereoPanel.Invalidate();
        };

        _questButton.Click += (_, _) =>
        {
            if (_xrCompanion.IsRunning)
            {
                _xrCompanion.Stop();
            }
            else
            {
                _xrCompanion.Start();
            }
            UpdateQuestButton();
        };

        devTools.Click += (_, _) => _webView.CoreWebView2?.OpenDevToolsWindow();

        bar.Items.Add(open);
        bar.Items.Add(save);
        bar.Items.Add(new ToolStripSeparator());
        bar.Items.Add(reload);
        bar.Items.Add(toggleStereo);
        bar.Items.Add(sbsPreview);
        bar.Items.Add(new ToolStripSeparator());
        bar.Items.Add(_questButton);
        bar.Items.Add(new ToolStripSeparator());
        bar.Items.Add(devTools);
        bar.Items.Add(new ToolStripSeparator());
        bar.Items.Add(new ToolStripLabel("A: GeoGebra Panel   B: Stereo Panel"));
        return bar;
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

            if (!File.Exists(index) || !File.Exists(boot))
            {
                _status.Text = "GeoGebra Web3D paketi eksik";
                MessageBox.Show(
                    this,
                    "Exp46 patched GeoGebra Web3D paketi bulunamadı.\n\n" +
                    "Bu dosya normal kullanıcı paketinde hazır gelir. Geliştirme build'inde " +
                    "önce Linux/CI Web3D build adımının çalışması gerekir.",
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

            _status.Text = "Yerel GeoGebra yükleniyor…";
            _webView.CoreWebView2.Navigate(LocalAppUrl);
        }
        catch (Exception ex)
        {
            _status.Text = "Başlatma hatası";
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
                    _status.Text = $"Sayfa hatası: {e.WebErrorStatus}";
                    return;
                }

                await InjectPcRuntimeAsync();
                _status.Text = "GeoGebra sayfası hazır · applet bekleniyor";
            };
        }
    }

    private async Task InstallBridgeAsync(CoreWebView2 core)
    {
        const string script = """
            (function () {
              if (window.QuestBridge && window.QuestBridge.__pcBridge) return;
              function send(message) {
                try { window.chrome.webview.postMessage(message); } catch (e) {}
              }
              window.QuestBridge = {
                __pcBridge: true,
                updateStereoLayout: function (json) {
                  send({ type: 'stereoLayout', payload: String(json || '') });
                },
                updateStereoEyes: function (left, right) {
                  send({ type: 'stereoEyes', left: String(left || ''), right: String(right || '') });
                },
                stereoInactive: function () {
                  send({ type: 'stereoInactive' });
                },
                setDepthPointerActive: function (active) {
                  send({ type: 'depthPointer', active: String(active || '') });
                },
                getStereoDebugStatus: function () {
                  return JSON.stringify({
                    platform: 'GeoGebraForQuest PC',
                    version: '0.1.0-exp46',
                    presentation: 'OpenXR quad + eye-specific B overlay'
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

        var stereoUrl = JsonSerializer.Serialize(StereoLayoutUrl);
        var script = $$"""
            (function () {
              if (!window.__ggqPcRuntimeInstalled) {
                window.__ggqPcRuntimeInstalled = true;

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
                setTimeout(resizeGeoGebra, 500);
                setTimeout(resizeGeoGebra, 1800);
              }

              if (!document.getElementById('ggq-pc-stereo-layout')) {
                var tag = document.createElement('script');
                tag.id = 'ggq-pc-stereo-layout';
                tag.src = {{stereoUrl}};
                tag.async = false;
                tag.onerror = function () {
                  try {
                    window.chrome.webview.postMessage({
                      type: 'runtimeError',
                      message: 'quest-stereo-layout.js yüklenemedi'
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

        // Local appassets is not a public OAuth callback origin. Hand the callback to
        // GeoGebra's public page while keeping the popup in the same WebView2 profile.
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
            _status.Text = "Popup açılamadı: " + ex.Message;
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
                    _status.Text = "GeoGebra hazır · Exp46 stereo bridge hazır";
                    break;

                case "stereoInactive":
                    _stereoPanel.ClearFrames("3D grafik kapalı");
                    _frameStatus.Text = "Stereo: inactive";
                    PublishInactiveGeometryIfNeeded();
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
                        _status.Text = messageNode.GetString() ?? "Runtime hatası";
                    }
                    break;
            }
        }
        catch (Exception ex)
        {
            _status.Text = "Bridge mesaj hatası: " + ex.Message;
        }
    }

    private void QueueStereoFrames(string left, string right)
    {
        lock (_pendingFrameLock)
        {
            // Keep only the newest frame pair. If JPEG decoding falls behind, old stereo
            // frames are intentionally dropped instead of building latency.
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

                try
                {
                    var left = DecodeDataUrl(current.Value.Left);
                    var right = DecodeDataUrl(current.Value.Right);
                    var number = Interlocked.Increment(ref _frameNumber);
                    var geometry = GetGeometrySnapshot();

                    _sharedFrames.WriteFrames(
                        left,
                        right,
                        geometry.PanelBounds,
                        geometry.ClientSize,
                        number);

                    if (_closing || IsDisposed)
                    {
                        left.Dispose();
                        right.Dispose();
                        return;
                    }

                    BeginInvoke((Action)(() =>
                    {
                        if (_closing)
                        {
                            left.Dispose();
                            right.Dispose();
                            return;
                        }

                        _stereoPanel.SetFrames(left, right, number);
                        _frameStatus.Text = $"Stereo: {number} · {left.Width}×{left.Height}/göz";
                    }));
                }
                catch (Exception ex)
                {
                    if (!_closing && !IsDisposed)
                    {
                        BeginInvoke((Action)(() => _frameStatus.Text = "Stereo decode: " + ex.Message));
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

    private (Rectangle PanelBounds, Size ClientSize) GetGeometrySnapshot()
    {
        if (_closing || IsDisposed) return (Rectangle.Empty, Size.Empty);

        if (InvokeRequired)
        {
            try
            {
                return ((Rectangle PanelBounds, Size ClientSize))Invoke(
                    new Func<(Rectangle PanelBounds, Size ClientSize)>(GetGeometrySnapshot));
            }
            catch
            {
                return (Rectangle.Empty, Size.Empty);
            }
        }

        if (_split.Panel2Collapsed || !_stereoPanel.Visible)
        {
            return (Rectangle.Empty, ClientSize);
        }

        var content = _stereoPanel.ContentRectangle;
        var screenOrigin = _stereoPanel.PointToScreen(content.Location);
        var clientOrigin = PointToClient(screenOrigin);
        return (new Rectangle(clientOrigin, content.Size), ClientSize);
    }

    private void PublishInactiveGeometryIfNeeded()
    {
        if (_closing || IsDisposed) return;
        var geometry = GetGeometrySnapshot();
        _sharedFrames.SetInactive(geometry.PanelBounds, geometry.ClientSize);
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
            _status.Text = "Dosya açılıyor…";
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
            _status.Text = "Açıldı: " + Path.GetFileName(dialog.FileName);
        }
        catch (Exception ex)
        {
            _status.Text = "Dosya açılamadı";
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
            _status.Text = "Dosya kaydediliyor…";
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
            _status.Text = "Kaydedildi: " + Path.GetFileName(dialog.FileName);
        }
        catch (Exception ex)
        {
            _status.Text = "Dosya kaydedilemedi";
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

        _xrStatus.Text = "Quest: " + text;
        UpdateQuestButton();
    }

    private void UpdateQuestButton()
    {
        if (_questButton is null) return;
        _questButton.Text = _xrCompanion.IsRunning ? "Quest'i Ayır" : "Quest'e Bağlan";
        _questButton.Checked = _xrCompanion.IsRunning;
    }
}
