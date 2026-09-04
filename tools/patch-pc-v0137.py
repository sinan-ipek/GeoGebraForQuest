from pathlib import Path
import re

# v0.13.7 runs after v0.13.6.

# 1) Never let OAuth window.close destroy the main XR browser. Instead, cancel
#    the close and ask MainForm to navigate the SAME browser back to GeoGebra.
p = Path('pc/SameSurfaceLifeSpanHandler.cs')
t = p.read_text(encoding='utf-8')
old = r'''    protected override bool DoClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        // A real OAuth popup is redirected into the single XR CEF surface. Once
        // the provider calls window.close(), let that browser close cleanly. The
        // MainForm will recreate the local GeoGebra browser with the SAME live
        // RequestContext, keeping cookies/session while avoiding a dead black view.
        return false;
    }

    protected override void OnBeforeClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        if (_authRedirected && !browser.IsPopup)
        {
            try { _recoverMainBrowser?.Invoke(); } catch { }
        }
        base.OnBeforeClose(chromiumWebBrowser, browser);
    }'''
new = r'''    protected override bool DoClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        // The login URL is hosted in our main XR browser. Never allow a provider's
        // window.close() to close that main browser; doing so kills the CEF texture
        // while OpenXR keeps rendering the cursor over a black panel.
        if (_authRedirected && !browser.IsPopup)
        {
            try { _recoverMainBrowser?.Invoke(); } catch { }
            return true; // cancel close; keep the CEF render surface alive
        }
        return base.DoClose(chromiumWebBrowser, browser);
    }

    protected override void OnBeforeClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        base.OnBeforeClose(chromiumWebBrowser, browser);
    }'''
if old not in t:
    raise SystemExit('v0.13.6 close/recovery block not found')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

# 2) Recovery no longer disposes/recreates the ChromiumWebBrowser. It simply
#    returns the still-live browser to the local app using the same RequestContext.
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
old_recovery = '''    private int _authBrowserRecoveryPending;\n\n    private void RecoverMainBrowserAfterAuthClose()\n    {\n        if (_closing || Interlocked.Exchange(ref _authBrowserRecoveryPending, 1) != 0) return;\n        BeginInvokeSafe(() =>\n        {\n            try\n            {\n                if (_closing) return;\n                var old = _browser;\n                _browser = null;\n                try { old?.Dispose(); } catch { }\n                _cefPageText = \"CEF oturum yenileniyor\";\n                UpdateWindowTitle();\n                CreateBrowser();\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = \"CEF auth recovery: \" + ShortError(ex);\n                UpdateWindowTitle();\n            }\n            finally\n            {\n                Interlocked.Exchange(ref _authBrowserRecoveryPending, 0);\n            }\n        });\n    }'''
new_recovery = '''    private int _authBrowserRecoveryPending;\n\n    private void RecoverMainBrowserAfterAuthClose()\n    {\n        if (_closing || Interlocked.Exchange(ref _authBrowserRecoveryPending, 1) != 0) return;\n        BeginInvokeSafe(() =>\n        {\n            try\n            {\n                if (_closing) return;\n                var browser = _browser?.GetBrowser();\n                if (browser is null) return;\n                _cefPageText = \"CEF oturumdan dönüyor\";\n                UpdateWindowTitle();\n                browser.MainFrame.LoadUrl(LocalAppUrl);\n                try { browser.GetHost().Invalidate(PaintElementType.View); } catch { }\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = \"CEF auth return: \" + ShortError(ex);\n                UpdateWindowTitle();\n            }\n            finally\n            {\n                Interlocked.Exchange(ref _authBrowserRecoveryPending, 0);\n            }\n        });\n    }'''
if old_recovery not in t:
    raise SystemExit('v0.13.6 recovery method not found')
t = t.replace(old_recovery, new_recovery, 1)

# 3) The GeoGebra-specific QuestBridge/stereo runtime must only run on the local
#    GeoGebra document. External auth pages receive only the login keyboard/focus UI.
old_exec = '        e.Frame.ExecuteJavaScriptAsync(script);\n\n        // External sign-in pages are usable without removing the headset.'
new_exec = '''        if (e.Url.StartsWith(\"https://appassets.androidplatform.net/\", StringComparison.OrdinalIgnoreCase))\n        {\n            e.Frame.ExecuteJavaScriptAsync(script);\n        }\n\n        // External sign-in pages are usable without removing the headset.'''
if old_exec not in t:
    raise SystemExit('main stereo script execution marker not found')
t = t.replace(old_exec, new_exec, 1)

# 4) If an auth provider leaves the main browser at about:blank instead of issuing
#    a close request, immediately return to the local app rather than showing black.
marker = '''        _cefPageText = ShortPageText(e.Url);\n        BeginInvokeSafe(UpdateWindowTitle);\n\n        var runtimeUrl = JsonSerializer.Serialize(PcStereoRuntimeUrl);'''
replacement = '''        _cefPageText = ShortPageText(e.Url);\n        BeginInvokeSafe(UpdateWindowTitle);\n\n        if (e.Url.Equals(\"about:blank\", StringComparison.OrdinalIgnoreCase))\n        {\n            RecoverMainBrowserAfterAuthClose();\n            return;\n        }\n\n        var runtimeUrl = JsonSerializer.Serialize(PcStereoRuntimeUrl);'''
if marker not in t:
    raise SystemExit('BrowserFrameLoadEnd status marker not found')
t = t.replace(marker, replacement, 1)

# 5) Version labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.6-login-focus-recovery', '0.13.7-auth-no-close')
    s = s.replace(r'0\\.13\\.6-login-focus-recovery', r'0\\.13\\.7-auth-no-close')
    s = s.replace('v0.13.6 ·', 'v0.13.7 ·')
    s = s.replace('[GGQ-PC v0.13.6]', '[GGQ-PC v0.13.7]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.7</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.7.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.7.0</AssemblyVersion>', s, count=1)
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.7 auth no-close recovery applied')
