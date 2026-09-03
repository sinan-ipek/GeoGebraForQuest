using System.Drawing.Imaging;
using System.Text.Json;
using CefSharp;
using CefSharp.Enums;
using KeyEvent = CefSharp.KeyEvent;
using KeyEventArgs = System.Windows.Forms.KeyEventArgs;
using MouseEventArgs = System.Windows.Forms.MouseEventArgs;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private void QueueStereoFrames(string left, string right)
    {
        // Always keep only the newest completed pair. If JPEG decode falls behind,
        // stale stereo frames are discarded instead of building latency.
        lock (_pendingFrameLock) _pendingFrames = (left, right);
        if (Interlocked.CompareExchange(ref _decodeWorkerActive, 1, 0) == 0)
        {
            _ = Task.Run(DecodeStereoLoop);
        }
    }

    private void DecodeStereoLoop()
    {
        try
        {
            while (!_closing)
            {
                (string Left, string Right)? pair;
                lock (_pendingFrameLock)
                {
                    pair = _pendingFrames;
                    _pendingFrames = null;
                }
                if (pair is null) break;

                Bitmap? left = null;
                Bitmap? right = null;
                try
                {
                    // The two eye JPEGs are independent. v0.12 decoded them serially on
                    // one worker core; decode both at the same time without changing the
                    // proven stereo transport or frame ordering.
                    Parallel.Invoke(
                        () => left = DecodeDataUrl(pair.Value.Left),
                        () => right = DecodeDataUrl(pair.Value.Right));

                    if (left is null || right is null)
                        throw new InvalidDataException("Stereo göz karelerinden biri decode edilemedi.");

                    var frame = Interlocked.Increment(ref _stereoFrameNumber);

                    bool active;
                    Rectangle rect;
                    Size size;
                    lock (_geometryLock)
                    {
                        active = _stereo3DActive;
                        rect = _stereo3DRenderBounds;
                        size = _browserSize;
                    }

                    if (active && rect.Width > 1 && rect.Height > 1 &&
                        size.Width > 1 && size.Height > 1)
                    {
                        _sharedStereoFrames.WriteFrames(left, right, rect, size, frame);
                    }

                    if ((frame % 30) == 0)
                    {
                        BeginInvokeSafe(UpdateWindowTitle);
                    }
                }
                finally
                {
                    left?.Dispose();
                    right?.Dispose();
                }
            }
        }
        catch (Exception ex)
        {
            _cefPageText = "Stereo decode: " + ex.Message;
            BeginInvokeSafe(UpdateWindowTitle);
        }
        finally
        {
            Interlocked.Exchange(ref _decodeWorkerActive, 0);
            lock (_pendingFrameLock)
            {
                if (!_closing && _pendingFrames is not null &&
                    Interlocked.CompareExchange(ref _decodeWorkerActive, 1, 0) == 0)
                {
                    _ = Task.Run(DecodeStereoLoop);
                }
            }
        }
    }

    private static Bitmap DecodeDataUrl(string dataUrl)
    {
        var comma = dataUrl.IndexOf(',');
        if (comma < 0 || comma >= dataUrl.Length - 1)
            throw new InvalidDataException("Geçersiz stereo image data URL");

        var bytes = Convert.FromBase64String(dataUrl[(comma + 1)..]);
        using var stream = new MemoryStream(bytes, writable: false);
        using var source = Image.FromStream(stream, false, false);

        // Produce the exact BGRA-friendly format required by the SBS writer once here.
        // v0.11 created another full-size 32-bit copy inside WriteFrames on every eye/frame.
        var result = new Bitmap(source.Width, source.Height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(result);
        graphics.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceCopy;
        graphics.DrawImageUnscaled(source, 0, 0);
        return result;
    }

    private void SetStereoInactive()
    {
        Rectangle rect;
        Size size;
        lock (_geometryLock)
        {
            rect = _stereo3DRenderBounds;
            size = _browserSize;
            _stereo3DActive = false;
        }
        _sharedStereoFrames.SetInactive(rect, size);
    }

    private void RequestResize()
    {
        if (_closing || !IsHandleCreated) return;
        UpdateBrowserSize();
        lock (_d3dLock) _swapChainResizePending = true;
    }

    private void UpdateBrowserSize()
    {
        var clientW = Math.Max(320, ClientSize.Width);
        var clientH = Math.Max(240, ClientSize.Height);

        var capScale = Math.Min(
            MaxBrowserWidth / (float)clientW,
            MaxBrowserHeight / (float)clientH);
        var scale = Math.Min(BrowserSupersample, capScale);

        // Do not let huge desktop resolutions create a 4K+ CEF surface just because
        // the window is 4K. Conversely, never shrink below half-resolution.
        scale = Math.Clamp(scale, 0.5f, BrowserSupersample);

        var size = new Size(
            Math.Max(320, (int)Math.Round(clientW * scale)),
            Math.Max(240, (int)Math.Round(clientH * scale)));

        lock (_geometryLock) _browserSize = size;
        try { _ = _browser?.ResizeAsync(size.Width, size.Height); } catch { }
    }

    private void PumpXrPointer()
    {
        if (_browser is null || _closing) return;
        if (!_xrInput.TryRead(out var sample)) return;

        Size size;
        lock (_geometryLock) size = _browserSize;
        var host = _browser.GetBrowserHost();
        if (host is null) return;

        if (!sample.Valid)
        {
            if (_xrPointerWasValid)
            {
                host.SendMouseMoveEvent(0, 0, true, CefEventFlags.None);
                _xrPointerWasValid = false;
            }
            if (_xrTriggerDown)
            {
                host.SendMouseClickEvent(
                    0, 0, MouseButtonType.Left, true, 1, CefEventFlags.None);
                _xrTriggerDown = false;
            }
            return;
        }

        var x = Math.Clamp(
            (int)Math.Round(sample.U * (size.Width - 1)),
            0,
            size.Width - 1);
        var y = Math.Clamp(
            (int)Math.Round(sample.V * (size.Height - 1)),
            0,
            size.Height - 1);

        host.SendMouseMoveEvent(x, y, false, CefEventFlags.None);
        _xrPointerWasValid = true;

        if (sample.TriggerDown != _xrTriggerDown)
        {
            host.SendMouseClickEvent(
                x,
                y,
                MouseButtonType.Left,
                mouseUp: !sample.TriggerDown,
                clickCount: 1,
                modifiers: CefEventFlags.None);
            _xrTriggerDown = sample.TriggerDown;
        }
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        if (_browser is null) return;
        var p = FormToBrowser(e.Location);
        _browser.GetBrowserHost()?.SendMouseMoveEvent(
            p.X, p.Y, false, GetMouseModifiers(e.Button));
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        base.OnMouseDown(e);
        Focus();
        if (_browser is null) return;
        var button = ToCefButton(e.Button);
        if (button is null) return;
        var p = FormToBrowser(e.Location);
        _browser.GetBrowserHost()?.SendMouseClickEvent(
            p.X, p.Y, button.Value, false, 1, GetMouseModifiers(e.Button));
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        base.OnMouseUp(e);
        if (_browser is null) return;
        var button = ToCefButton(e.Button);
        if (button is null) return;
        var p = FormToBrowser(e.Location);
        _browser.GetBrowserHost()?.SendMouseClickEvent(
            p.X, p.Y, button.Value, true, 1, GetMouseModifiers(e.Button));
    }

    protected override void OnMouseWheel(MouseEventArgs e)
    {
        base.OnMouseWheel(e);
        if (_browser is null) return;
        var p = FormToBrowser(e.Location);
        _browser.GetBrowserHost()?.SendMouseWheelEvent(
            new MouseEvent(p.X, p.Y, CefEventFlags.None),
            0,
            e.Delta);
    }

    protected override void OnKeyPress(KeyPressEventArgs e)
    {
        base.OnKeyPress(e);
        _browser?.GetBrowserHost()?.SendKeyEvent(new KeyEvent
        {
            Type = KeyEventType.Char,
            WindowsKeyCode = e.KeyChar
        });
    }

    protected override void OnKeyUp(KeyEventArgs e)
    {
        base.OnKeyUp(e);
        _browser?.GetBrowserHost()?.SendKeyEvent(new KeyEvent
        {
            Type = KeyEventType.KeyUp,
            WindowsKeyCode = e.KeyValue,
            Modifiers = GetKeyModifiers(e)
        });
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
            _browser?.Reload();
            return;
        }
        if (e.KeyCode == Keys.F9)
        {
            e.SuppressKeyPress = true;
            if (_xrCompanion.IsRunning) _xrCompanion.Stop();
            else _xrCompanion.Start();
            return;
        }

        _browser?.GetBrowserHost()?.SendKeyEvent(new KeyEvent
        {
            Type = KeyEventType.RawKeyDown,
            WindowsKeyCode = e.KeyValue,
            Modifiers = GetKeyModifiers(e)
        });
    }

    private Point FormToBrowser(Point p)
    {
        Size size;
        lock (_geometryLock) size = _browserSize;
        return new Point(
            Math.Clamp(
                (int)Math.Round(p.X * size.Width /
                    (double)Math.Max(1, ClientSize.Width)),
                0,
                size.Width - 1),
            Math.Clamp(
                (int)Math.Round(p.Y * size.Height /
                    (double)Math.Max(1, ClientSize.Height)),
                0,
                size.Height - 1));
    }

    private static MouseButtonType? ToCefButton(MouseButtons button) => button switch
    {
        MouseButtons.Left => MouseButtonType.Left,
        MouseButtons.Middle => MouseButtonType.Middle,
        MouseButtons.Right => MouseButtonType.Right,
        _ => null
    };

    private static CefEventFlags GetMouseModifiers(MouseButtons buttons)
    {
        var flags = CefEventFlags.None;
        if ((buttons & MouseButtons.Left) != 0)
            flags |= CefEventFlags.LeftMouseButton;
        if ((buttons & MouseButtons.Middle) != 0)
            flags |= CefEventFlags.MiddleMouseButton;
        if ((buttons & MouseButtons.Right) != 0)
            flags |= CefEventFlags.RightMouseButton;
        if ((Control.ModifierKeys & Keys.Shift) != 0)
            flags |= CefEventFlags.ShiftDown;
        if ((Control.ModifierKeys & Keys.Control) != 0)
            flags |= CefEventFlags.ControlDown;
        if ((Control.ModifierKeys & Keys.Alt) != 0)
            flags |= CefEventFlags.AltDown;
        return flags;
    }

    private static CefEventFlags GetKeyModifiers(KeyEventArgs e)
    {
        var flags = CefEventFlags.None;
        if (e.Shift) flags |= CefEventFlags.ShiftDown;
        if (e.Control) flags |= CefEventFlags.ControlDown;
        if (e.Alt) flags |= CefEventFlags.AltDown;
        return flags;
    }

    private async Task OpenLocalFileAsync()
    {
        if (_browser is null) return;
        using var dialog = new OpenFileDialog
        {
            Title = "GeoGebra dosyası aç",
            Filter = "GeoGebra dosyası (*.ggb)|*.ggb|Tüm dosyalar (*.*)|*.*",
            CheckFileExists = true
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        try
        {
            var base64 = Convert.ToBase64String(
                await File.ReadAllBytesAsync(dialog.FileName));
            var encoded = JsonSerializer.Serialize(base64);
            var response = await _browser.EvaluateScriptAsync($$"""
                (function(){
                  if (!window.ggbApplet || typeof window.ggbApplet.setBase64 !== 'function') return 'NOT_READY';
                  window.ggbApplet.setBase64({{encoded}});
                  return 'OK';
                })();
                """);
            if (!response.Success || response.Result?.ToString() != "OK")
                throw new InvalidOperationException("GeoGebra henüz hazır değil.");
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this, ex.Message, "Dosya açılamadı",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private async Task SaveLocalFileAsync()
    {
        if (_browser is null) return;
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
            var response = await _browser.EvaluateScriptAsync("""
                (function(){
                  if (!window.ggbApplet || typeof window.ggbApplet.getBase64 !== 'function') return 'NOT_READY';
                  return window.ggbApplet.getBase64();
                })();
                """);
            var base64 = response.Success ? response.Result?.ToString() : null;
            if (string.IsNullOrWhiteSpace(base64) || base64 == "NOT_READY")
                throw new InvalidOperationException("GeoGebra henüz hazır değil.");

            await File.WriteAllBytesAsync(
                dialog.FileName,
                Convert.FromBase64String(base64));
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this, ex.Message, "Dosya kaydedilemedi",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
