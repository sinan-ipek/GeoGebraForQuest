using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace GeoGebraForQuest.PC;

internal sealed class MainForm : Form
{
    private const string LocalHost = "appassets.androidplatform.net";
    private const string LocalAppUrl = "https://appassets.androidplatform.net/assets/web/index.html";
    private const string StereoLayoutUrl = "https://appassets.androidplatform.net/assets/web/quest-stereo-layout.js";
    private const string RemoteLoginCallback = "https://www.geogebra.org/apps/latest/web3d/html/ggtcallback.html";

    private readonly WebView2 _webView = new() { Dock = DockStyle.Fill };
    private readonly StereoPanelControl _stereoPanel = new() { Dock = DockStyle.Fill };
    private readonly SplitContainer _split = new()
    {
        Dock = DockStyle.Fill,
        Orientation = Orientation.Vertical,
        FixedPanel = FixedPanel.None,
        Panel1MinSize = 640,
        Panel2MinSize = 320,
        SplitterWidth = 6
    };
    private readonly ToolStripStatusLabel _status = new() { Text = "Başlatılıyor…" };
    private readonly ToolStripStatusLabel _frameStatus = new() { Spring = true, TextAlign = ContentAlignment.MiddleRight };

    private CoreWebView2Environment? _environment;
    private long _frameNumber;
    private int _decodeWorkerActive;
    private readonly object _pendingFrameLock = new();
    private (string Left, string Right)? _pendingFrames;

    public MainForm()
    {
        Text = "GeoGebraForQuest PC · v0.1.0";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(1200, 720);
        KeyPreview = true;

        var toolStrip = BuildToolStrip();
        var statusStrip = new StatusStrip();
        statusStrip.Items.Add(_status);
        statusStrip.Items.Add(_frameStatus);

        _split.Panel1.Controls.Add(_webView);
        _split.Panel2.Controls.Add(_stereoPanel);

        Controls.Add(_split);
        Controls.Add(statusStrip);
        Controls.Add(toolStrip);

        toolStrip.Dock = DockStyle.Top;
        statusStrip.Dock = DockStyle.Bottom;

        Shown += async (_, _) =>
        {
            _split.SplitterDistance = Math.Max(700, (int)(ClientSize.Width * 0.70));
            await InitializeWebViewAsync();
        };

        FormClosed += (_, _) =>
        {
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

        var open = new ToolStripButton("Yerel Aç") { ToolTipText = ".ggb dosyası aç" };
        var save = new ToolStripButton("Farklı Kaydet") { ToolTipText = "Mevcut GeoGebra dosyasını .ggb olarak kaydet" };
        var reload = new ToolStripButton("Yenile");
        var toggleStereo = new ToolStripButton("B Paneli") { Checked = true, CheckOnClick = true };
        var devTools = new ToolStripButton("DevTools");

        open.Click += async (_, _) => await OpenLocalFileAsync();
        save.Click += async (_, _) => await SaveLocalFileAsync();
        reload.Click += (_, _) => _webView.CoreWebView2?.Reload();
        toggleStereo.CheckedChanged += (_, _) => _split.Panel2Collapsed = !toggleStereo.Checked;
        devTools.Click += (_, _) => _webView.CoreWebView2?.OpenDevToolsWindow();

        bar.Items.Add(open);
        bar.Items.Add(save);
        bar.Items.Add(new ToolStripSeparator());
        bar.Items.Add(reload);
        bar.Items.Add(toggleStereo);
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
            var assetIndex = Path.Combine(AppContext.BaseDirectory, "assets", "web", "index.html");
            var geoGebraBoot = Path.Combine(AppContext.BaseDirectory, "assets", "web", "GeoGebra", "web3d", "web3d.nocache.js");

            if (!File.Exists(assetIndex) || !File.Exists(geoGebraBoot))
            {
                MessageBox.Show(
                    this,
                    "Yerel GeoGebra Web3D paketi bulunamadı.\n\n" +
                    "Önce depo kökünde şu komutu çalıştırın:\n" +
                    "powershell -ExecutionPolicy Bypass -File .\\tools\\build-geogebra-pc.ps1\n\n" +
                    "Ardından PC projesini tekrar build edin.",
                    "GeoGebraForQuest PC",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                _status.Text = "GeoGebra Web3D paketi eksik";
                return;
            }

            var userData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "GeoGebraForQuestPC",
                "WebView2");
            Directory.CreateDirectory(userData);

            _environment = await CoreWebView2Environment.CreateAsync(null, userData);
            await _webView.EnsureCoreWebView2Async(_environment);

            ConfigureCoreWebView(_webView.CoreWebView2, isMain: true);
            await InstallBridgeAsync(_webView.CoreWebView2);
            _webView.CoreWebView2.Navigate(LocalAppUrl);
            _status.Text = "Yerel GeoGebra yükleniyor…";
        }
        catch (Exception ex)
        {
            _status.Text = "Başlatma hatası";
            MessageBox.Show(this, ex.ToString(), "GeoGebraForQuest PC başlatma hatası", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ConfigureCoreWebView(CoreWebView2 core, bool isMain)
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

        core.NavigationStarting += HandleNavigationStarting;
        core.NewWindowRequested += HandleNewWindowRequested;

        if (isMain)
        {
            core.WebMessageReceived += HandleWebMessageReceived;
            core.NavigationCompleted += async (_, args) =>
            {
                if (!args.IsSuccess)
                {
                    _status.Text = $"Sayfa yükleme hatası: {args.WebErrorStatus}";
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
                getStereoDebugStatus: function () {
                  return JSON.stringify({ platform: 'GeoGebraForQuest PC', version: '0.1.0' });
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

        var stereoUrlJson = JsonSerializer.Serialize(StereoLayoutUrl);
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

                window.addEventListener('resize', resizeGeoGebra, { passive: true });
                if (window.ResizeObserver) {
                  var ro = new ResizeObserver(resizeGeoGebra);
                  ro.observe(document.documentElement);
                  if (document.body) ro.observe(document.body);
                }
                setInterval(resizeGeoGebra, 1000);
                setTimeout(resizeGeoGebra, 500);
                setTimeout(resizeGeoGebra, 1800);
              }

              if (!document.getElementById('ggq-pc-stereo-layout')) {
                var stereo = document.createElement('script');
                stereo.id = 'ggq-pc-stereo-layout';
                stereo.src = {{stereoUrlJson}};
                stereo.async = false;
                stereo.onerror = function () {
                  try { window.chrome.webview.postMessage({ type: 'runtimeError', message: 'quest-stereo-layout.js yüklenemedi' }); } catch (e) {}
                };
                (document.head || document.documentElement).appendChild(stereo);
              }
            })();
            """;

        await _webView.CoreWebView2.ExecuteScriptAsync(script);
    }

    private void HandleNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri)) return;
        if (!uri.Host.Equals(LocalHost, StringComparison.OrdinalIgnoreCase)) return;
        if (!uri.AbsolutePath.EndsWith("/ggtcallback.html", StringComparison.OrdinalIgnoreCase)) return;

        e.Cancel = true;
        var target = RemoteLoginCallback + uri.Query;
        if (sender is CoreWebView2 core)
        {
            core.Navigate(target);
        }
    }

    private async void HandleNewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        if (_environment is null) return;
        var deferral = e.GetDeferral();
        try
        {
            var popup = new PopupForm(_environment, ConfigurePopupCore);
            await popup.InitializeAsync();
            e.NewWindow = popup.WebView.CoreWebView2;
            e.Handled = true;
            popup.Show(this);
        }
        catch (Exception ex)
        {
            e.Handled = false;
            _status.Text = "Popup açılamadı: " + ex.Message;
        }
        finally
        {
            deferral.Complete();
        }
    }

    private void ConfigurePopupCore(CoreWebView2 core)
    {
        ConfigureCoreWebView(core, isMain: false);
    }

    private void HandleWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            using var document = JsonDocument.Parse(e.WebMessageAsJson);
            var root = document.RootElement;
            if (!root.TryGetProperty("type", out var typeElement)) return;
            var type = typeElement.GetString();

            switch (type)
            {
                case "panelReady":
                    _status.Text = "GeoGebra hazır";
                    break;

                case "stereoInactive":
                    _stereoPanel.ClearFrames("Stereo Panel (B) · 3D grafik kapalı");
                    _frameStatus.Text = "Stereo inactive";
                    break;

                case "stereoEyes":
                    if (!root.TryGetProperty("left", out var leftElement) ||
                        !root.TryGetProperty("right", out var rightElement)) return;
                    var left = leftElement.GetString();
                    var right = rightElement.GetString();
                    if (string.IsNullOrWhiteSpace(left) || string.IsNullOrWhiteSpace(right)) return;
                    QueueStereoFrames(left, right);
                    break;

                case "runtimeError":
                    if (root.TryGetProperty("message", out var message))
                    {
                        _status.Text = message.GetString() ?? "PC runtime hatası";
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
            while (true)
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

                    if (IsDisposed)
                    {
                        left.Dispose();
                        right.Dispose();
                        return;
                    }

                    BeginInvoke(() =>
                    {
                        _stereoPanel.SetFrames(left, right, number);
                        _frameStatus.Text = $"Stereo frames: {number}";
                    });
                }
                catch (Exception ex)
                {
                    if (!IsDisposed)
                    {
                        BeginInvoke(() => _frameStatus.Text = "Stereo decode: " + ex.Message);
                    }
                }
            }
        }
        finally
        {
            Interlocked.Exchange(ref _decodeWorkerActive, 0);
            lock (_pendingFrameLock)
            {
                if (_pendingFrames is not null && Interlocked.CompareExchange(ref _decodeWorkerActive, 1, 0) == 0)
                {
                    _ = Task.Run(DecodeFrameLoop);
                }
            }
        }
    }

    private static Bitmap DecodeDataUrl(string dataUrl)
    {
        var comma = dataUrl.IndexOf(',');
        if (comma < 0 || comma == dataUrl.Length - 1) throw new InvalidDataException("Geçersiz image data URL");
        var bytes = Convert.FromBase64String(dataUrl[(comma + 1)..]);
        using var stream = new MemoryStream(bytes, writable: false);
        using var source = Image.FromStream(stream, useEmbeddedColorManagement: false, validateImageData: false);
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
            _status.Text = "Dosya açılıyor…";
            var bytes = await File.ReadAllBytesAsync(dialog.FileName);
            var base64 = Convert.ToBase64String(bytes);
            var base64Json = JsonSerializer.Serialize(base64);
            var result = await _webView.CoreWebView2.ExecuteScriptAsync($$"""
                (function () {
                  if (!window.ggbApplet || typeof window.ggbApplet.setBase64 !== 'function') return 'NOT_READY';
                  window.ggbApplet.setBase64({{base64Json}});
                  return 'OK';
                })();
                """);
            var state = JsonSerializer.Deserialize<string>(result);
            if (state != "OK") throw new InvalidOperationException("GeoGebra henüz hazır değil.");
            _status.Text = "Açıldı: " + Path.GetFileName(dialog.FileName);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Dosya açılamadı", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _status.Text = "Dosya açılamadı";
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
                  if (!window.ggbApplet || typeof window.ggbApplet.getBase64 !== 'function') return 'NOT_READY';
                  return window.ggbApplet.getBase64();
                })();
                """);
            var base64 = JsonSerializer.Deserialize<string>(result);
            if (string.IsNullOrWhiteSpace(base64) || base64 == "NOT_READY")
            {
                throw new InvalidOperationException("GeoGebra henüz hazır değil.");
            }

            var bytes = Convert.FromBase64String(base64);
            await File.WriteAllBytesAsync(dialog.FileName, bytes);
            _status.Text = "Kaydedildi: " + Path.GetFileName(dialog.FileName);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Dosya kaydedilemedi", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _status.Text = "Dosya kaydedilemedi";
        }
    }
}
