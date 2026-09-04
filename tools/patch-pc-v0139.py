from pathlib import Path
import re

# v0.13.9 runs after v0.13.8. The v0.13.8 real-popup architecture was correct,
# but it explicitly disposed the managed popup wrapper from the popup-close path.
# That close path is entered from CEF's native browser teardown. Re-entering
# Dispose there can tear down native objects twice and terminate the process.

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

# 1) Add lightweight lifecycle logging so a future failure leaves evidence.
field_marker = '''    private D3DChromiumWebBrowser? _authPopupBrowser;'''
field_new = '''    private D3DChromiumWebBrowser? _authPopupBrowser;
    private static readonly object AuthTraceLock = new();'''
if field_marker not in t:
    raise SystemExit('auth popup field marker not found')
t = t.replace(field_marker, field_new, 1)

helper_marker = '''    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)
    {'''
helper = '''    private static void AuthTrace(string message)
    {
        try
        {
            lock (AuthTraceLock)
            {
                var path = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuest-auth.log");
                File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{Environment.NewLine}");
            }
        }
        catch { }
    }

    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)
    {'''
if helper_marker not in t:
    raise SystemExit('CreateAuthPopupBrowser marker not found')
t = t.replace(helper_marker, helper, 1)

# 2) Trace popup creation and close handoff.
t = t.replace('''        try
        {
            Size size;''', '''        try
        {
            AuthTrace($"popup-create begin url={targetUrl}");
            Size size;''', 1)

t = t.replace('''            _authPopupBrowser = popup;
            _browser = popup;''', '''            _authPopupBrowser = popup;
            _browser = popup;
            AuthTrace("popup-create success; active surface switched to popup");''', 1)

t = t.replace('''        catch (Exception ex)
        {
            _cefPageText = "CEF popup create: " + ShortError(ex);''', '''        catch (Exception ex)
        {
            AuthTrace("popup-create exception: " + ex);
            _cefPageText = "CEF popup create: " + ShortError(ex);''', 1)

# 3) Most important fix: NEVER Dispose the managed popup wrapper from the
#    OnBeforeClose-derived callback. CEF owns the native popup teardown at this
#    point. We only drop our references and restore the still-live root browser.
old_close = '''    private void AuthPopupClosed(IWebBrowser popupWebBrowser)
    {
        BeginInvokeSafe(() =>
        {
            if (_closing) return;
            if (_authPopupBrowser is not null &&
                !ReferenceEquals(_authPopupBrowser, popupWebBrowser)) return;

            var oldPopup = _authPopupBrowser;
            _authPopupBrowser = null;
            _browser = _rootBrowser;
            SetStereoUiSuspended(false);

            try
            {
                var host = _rootBrowser?.GetBrowserHost();
                host?.WasHidden(false);
                host?.SetFocus(true);
                host?.Invalidate(PaintElementType.View);
            }
            catch { }

            try { oldPopup?.Dispose(); } catch { }
            _cefPageText = "CEF GeoGebra · giriş penceresi kapandı";
            UpdateWindowTitle();
        });
    }'''
new_close = '''    private void AuthPopupClosed(IWebBrowser popupWebBrowser)
    {
        AuthTrace("popup-close callback received");
        BeginInvokeSafe(() =>
        {
            try
            {
                if (_closing) return;
                if (_authPopupBrowser is not null &&
                    !ReferenceEquals(_authPopupBrowser, popupWebBrowser))
                {
                    AuthTrace("popup-close ignored: stale popup instance");
                    return;
                }

                // Do not Dispose popupWebBrowser here. OnBeforeClose means CEF is
                // already destroying its native browser. Disposing the wrapper from
                // this path can re-enter native teardown and crash the whole process.
                _authPopupBrowser = null;
                _browser = _rootBrowser;
                SetStereoUiSuspended(false);

                var host = _rootBrowser?.GetBrowserHost();
                if (host is not null)
                {
                    host.WasHidden(false);
                    host.SetFocus(true);
                    host.Invalidate(PaintElementType.View);
                }

                _cefPageText = "CEF GeoGebra · giriş tamamlandı";
                UpdateWindowTitle();
                AuthTrace("popup-close complete; root surface restored");
            }
            catch (Exception ex)
            {
                AuthTrace("popup-close restore exception: " + ex);
                _cefPageText = "CEF popup dönüş: " + ShortError(ex);
                UpdateWindowTitle();
            }
        });
    }'''
if old_close not in t:
    raise SystemExit('v0.13.8 AuthPopupClosed block not found')
t = t.replace(old_close, new_close, 1)

# 4) During final app shutdown, close popup first but do not Dispose it separately;
#    CloseBrowser(true) lets CEF perform one native teardown path.
old_shutdown = '''        try
        {
            _authPopupBrowser?.GetBrowserHost()?.CloseBrowser(true);
            _authPopupBrowser?.Dispose();
        }
        catch { }'''
new_shutdown = '''        try
        {
            _authPopupBrowser?.GetBrowserHost()?.CloseBrowser(true);
        }
        catch { }'''
if old_shutdown not in t:
    raise SystemExit('v0.13.8 popup shutdown block not found')
t = t.replace(old_shutdown, new_shutdown, 1)

# 5) Version labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.8-real-auth-popup', '0.13.9-popup-close-safety')
    s = s.replace(r'0\.13\.8-real-auth-popup', r'0\.13\.9-popup-close-safety')
    s = s.replace('v0.13.8 ·', 'v0.13.9 ·')
    s = s.replace('[GGQ-PC v0.13.8]', '[GGQ-PC v0.13.9]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.9</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.9.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.9.0</AssemblyVersion>', s, count=1)
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.9 popup close safety applied')
