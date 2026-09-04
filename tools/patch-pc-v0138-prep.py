from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
pattern = re.compile(
    r'    private int _authBrowserRecoveryPending;.*?\n    private void BrowserFrameLoadEnd\(object\? sender, FrameLoadEndEventArgs e\)\n    \{',
    re.DOTALL,
)
canonical = '''    private int _authBrowserRecoveryPending;\n\n    private void RecoverMainBrowserAfterAuthClose()\n    {\n        if (_closing || Interlocked.Exchange(ref _authBrowserRecoveryPending, 1) != 0) return;\n        BeginInvokeSafe(() =>\n        {\n            try\n            {\n                if (_closing) return;\n                var browser = _browser?.GetBrowser();\n                if (browser is null) return;\n                _cefPageText = \"CEF oturumdan dönüyor\";\n                UpdateWindowTitle();\n                browser.MainFrame.LoadUrl(LocalAppUrl);\n                try { browser.GetHost().Invalidate(PaintElementType.View); } catch { }\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = \"CEF auth return: \" + ShortError(ex);\n                UpdateWindowTitle();\n            }\n            finally\n            {\n                Interlocked.Exchange(ref _authBrowserRecoveryPending, 0);\n            }\n        });\n    }\n\n    private void BrowserFrameLoadEnd(object? sender, FrameLoadEndEventArgs e)\n    {'''
t, n = pattern.subn(canonical, t, count=1)
if n != 1:
    raise SystemExit('could not normalize v0.13.7 auth recovery block')
p.write_text(t, encoding='utf-8')
print('v0.13.8 prep normalized auth recovery block')
