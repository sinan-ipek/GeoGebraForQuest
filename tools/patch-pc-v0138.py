from pathlib import Path
import re

# v0.13.8 runs after v0.13.7. It replaces the fragile same-tab OAuth redirect
# with a real child CEF popup that renders into the same XR texture.

# ---------------------------------------------------------------------------
# 1) Real popup lifespan handler. Preserve parent/child opener semantics.
# ---------------------------------------------------------------------------
p = Path('pc/SameSurfaceLifeSpanHandler.cs')
p.write_text(r'''using CefSharp;
using CefSharp.Handler;

namespace GeoGebraForQuest.PC;

internal sealed class SameSurfaceLifeSpanHandler : LifeSpanHandler
{
    private readonly Func<string, IWebBrowser?>? _createPopupBrowser;
    private readonly Action<IWebBrowser>? _popupClosed;

    public SameSurfaceLifeSpanHandler(
        Func<string, IWebBrowser?>? createPopupBrowser,
        Action<IWebBrowser>? popupClosed)
    {
        _createPopupBrowser = createPopupBrowser;
        _popupClosed = popupClosed;
    }

    protected override bool OnBeforePopup(
        IWebBrowser chromiumWebBrowser,
        IBrowser browser,
        IFrame frame,
        string targetUrl,
        string targetFrameName,
        WindowOpenDisposition targetDisposition,
        bool userGesture,
        IPopupFeatures popupFeatures,
        IWindowInfo windowInfo,
        IBrowserSettings browserSettings,
        ref bool noJavascriptAccess,
        out IWebBrowser newBrowser)
    {
        // Keep a REAL CEF popup so window.opener/window.close, cookies, redirects
        // and the OAuth parent-child relationship work exactly as expected.
        // The popup is windowless and shares the same D3D render handler, so Quest
        // still sees one surface rather than a native desktop window.
        windowInfo.SetAsWindowless(IntPtr.Zero);
        windowInfo.WindowlessRenderingEnabled = true;
        windowInfo.SharedTextureEnabled = true;
        browserSettings.WindowlessFrameRate = 60;
        noJavascriptAccess = false;

        newBrowser = _createPopupBrowser?.Invoke(targetUrl)!;
        return newBrowser is null;
    }

    protected override bool DoClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        // Popups are allowed to close normally. The root GeoGebra browser is never
        // replaced or navigated during authentication.
        if (browser.IsPopup) return false;
        return base.DoClose(chromiumWebBrowser, browser);
    }

    protected override void OnBeforeClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        if (browser.IsPopup)
        {
            try { _popupClosed?.Invoke(chromiumWebBrowser); } catch { }
        }
        base.OnBeforeClose(chromiumWebBrowser, browser);
    }
}
''', encoding='utf-8')

# ---------------------------------------------------------------------------
# 2) D3D browser can act as either root or popup shell.
# ---------------------------------------------------------------------------
p = Path('pc/D3DChromiumWebBrowser.cs')
t = p.read_text(encoding='utf-8')
old_sig = '''        IRenderHandler renderHandler,\n        int initialWidth,\n        int initialHeight,\n        Action? recoverMainBrowser = null)'''
new_sig = '''        IRenderHandler renderHandler,\n        int initialWidth,\n        int initialHeight,\n        Func<string, IWebBrowser?>? createPopupBrowser = null,\n        Action<IWebBrowser>? popupClosed = null)'''
if old_sig not in t:
    raise SystemExit('v0.13.7 D3D constructor signature not found')
t = t.replace(old_sig, new_sig, 1)
old_life = 'LifeSpanHandler = new SameSurfaceLifeSpanHandler(recoverMainBrowser);'
new_life = 'LifeSpanHandler = new SameSurfaceLifeSpanHandler(createPopupBrowser, popupClosed);'
if old_life not in t:
    raise SystemExit('v0.13.7 lifespan assignment not found')
t = t.replace(old_life, new_life, 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 3) MainForm keeps root alive and temporarily routes render/input to popup.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

field_marker = '''    private IRequestContext? _requestContext;\n    private D3DChromiumWebBrowser? _browser;'''
field_new = '''    private IRequestContext? _requestContext;\n    // _browser is the currently interactive surface. During auth it points to\n    // the real popup; otherwise it points to _rootBrowser.\n    private D3DChromiumWebBrowser? _browser;\n    private D3DChromiumWebBrowser? _rootBrowser;\n    private D3DChromiumWebBrowser? _authPopupBrowser;'''
if field_marker not in t:
    raise SystemExit('browser field marker not found')
t = t.replace(field_marker, field_new, 1)

old_ctor = '''            this,\n            initialSize.Width,\n            initialSize.Height,\n            RecoverMainBrowserAfterAuthClose);'''
new_ctor = '''            this,\n            initialSize.Width,\n            initialSize.Height,\n            CreateAuthPopupBrowser,\n            AuthPopupClosed);\n        _rootBrowser = _browser;'''
if old_ctor not in t:
    raise SystemExit('v0.13.7 root browser constructor call not found')
t = t.replace(old_ctor, new_ctor, 1)

# Replace the same-tab recovery method with real popup creation/close callbacks.
old_recovery = '''    private int _authBrowserRecoveryPending;\n\n    private void RecoverMainBrowserAfterAuthClose()\n    {\n        if (_closing || Interlocked.Exchange(ref _authBrowserRecoveryPending, 1) != 0) return;\n        BeginInvokeSafe(() =>\n        {\n            try\n            {\n                if (_closing) return;\n                var browser = _browser?.GetBrowser();\n                if (browser is null) return;\n                _cefPageText = \"CEF oturumdan dönüyor\";\n                UpdateWindowTitle();\n                browser.MainFrame.LoadUrl(LocalAppUrl);\n                try { browser.GetHost().Invalidate(PaintElementType.View); } catch { }\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = \"CEF auth return: \" + ShortError(ex);\n                UpdateWindowTitle();\n            }\n            finally\n            {\n                Interlocked.Exchange(ref _authBrowserRecoveryPending, 0);\n            }\n        });\n    }'''
new_recovery = '''    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)\n    {\n        if (_closing || _requestContext is null) return null;\n        try\n        {\n            Size size;\n            lock (_geometryLock) size = _browserSize;\n\n            var popup = new D3DChromiumWebBrowser(\n                string.Empty,\n                _requestContext,\n                this,\n                size.Width,\n                size.Height,\n                CreateAuthPopupBrowser,\n                AuthPopupClosed);\n\n            // Popup load events still need our Quest login keyboard/focus helper.\n            // BrowserFrameLoadEnd injects stereo runtime only on LocalAppUrl, so auth\n            // pages never receive GeoGebra-specific scripts.\n            popup.FrameLoadEnd += BrowserFrameLoadEnd;\n            popup.LoadError += (_, args) =>\n            {\n                if (_closing || args.ErrorCode == CefErrorCode.Aborted) return;\n                _cefPageText = $\"CEF popup HATA {args.ErrorCode}: {args.ErrorText}\";\n                BeginInvokeSafe(UpdateWindowTitle);\n            };\n\n            _authPopupBrowser = popup;\n            _browser = popup;\n\n            // The render handler is shared by root and popup. Hide the root while\n            // auth is visible so its background paints cannot overwrite popup frames.\n            try { _rootBrowser?.GetBrowserHost()?.WasHidden(true); } catch { }\n            SetStereoUiSuspended(true);\n            _cefPageText = \"CEF giriş penceresi\";\n            BeginInvokeSafe(UpdateWindowTitle);\n            return popup;\n        }\n        catch (Exception ex)\n        {\n            _cefPageText = \"CEF popup create: \" + ShortError(ex);\n            BeginInvokeSafe(UpdateWindowTitle);\n            return null;\n        }\n    }\n\n    private void AuthPopupClosed(IWebBrowser popupWebBrowser)\n    {\n        BeginInvokeSafe(() =>\n        {\n            if (_closing) return;\n            if (_authPopupBrowser is not null &&\n                !ReferenceEquals(_authPopupBrowser, popupWebBrowser)) return;\n\n            var oldPopup = _authPopupBrowser;\n            _authPopupBrowser = null;\n            _browser = _rootBrowser;\n            SetStereoUiSuspended(false);\n\n            try\n            {\n                var host = _rootBrowser?.GetBrowserHost();\n                host?.WasHidden(false);\n                host?.SetFocus(true);\n                host?.Invalidate(PaintElementType.View);\n            }\n            catch { }\n\n            try { oldPopup?.Dispose(); } catch { }\n            _cefPageText = \"CEF GeoGebra · giriş penceresi kapandı\";\n            UpdateWindowTitle();\n        });\n    }'''
if old_recovery not in t:
    raise SystemExit('v0.13.7 auth recovery method not found')
t = t.replace(old_recovery, new_recovery, 1)

# about:blank is normal for a popup while it is closing. Never navigate the root.
old_blank = '''        if (e.Url.Equals(\"about:blank\", StringComparison.OrdinalIgnoreCase))\n        {\n            RecoverMainBrowserAfterAuthClose();\n            return;\n        }'''
new_blank = '''        if (e.Url.Equals(\"about:blank\", StringComparison.OrdinalIgnoreCase))\n        {\n            return;\n        }'''
if old_blank not in t:
    raise SystemExit('v0.13.7 about:blank recovery block not found')
t = t.replace(old_blank, new_blank, 1)

# Shutdown must close both managed browser objects, even if auth is active.
old_shutdown = '''        try\n        {\n            _browser?.GetBrowserHost()?.CloseBrowser(true);\n            _browser?.Dispose();\n        }\n        catch { }\n        _browser = null;'''
new_shutdown = '''        try\n        {\n            _authPopupBrowser?.GetBrowserHost()?.CloseBrowser(true);\n            _authPopupBrowser?.Dispose();\n        }\n        catch { }\n        try\n        {\n            _rootBrowser?.GetBrowserHost()?.CloseBrowser(true);\n            _rootBrowser?.Dispose();\n        }\n        catch { }\n        _authPopupBrowser = null;\n        _rootBrowser = null;\n        _browser = null;'''
if old_shutdown not in t:
    raise SystemExit('shutdown browser block not found')
t = t.replace(old_shutdown, new_shutdown, 1)

p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 4) Version labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.7-auth-no-close', '0.13.8-real-auth-popup')
    s = s.replace(r'0\\.13\\.7-auth-no-close', r'0\\.13\\.8-real-auth-popup')
    s = s.replace('v0.13.7 ·', 'v0.13.8 ·')
    s = s.replace('[GGQ-PC v0.13.7]', '[GGQ-PC v0.13.8]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.8</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.8.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.8.0</AssemblyVersion>', s, count=1)
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.8 real auth popup applied')
