from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
canonical = '''        if (e.Url.Equals("about:blank", StringComparison.OrdinalIgnoreCase))
        {
            RecoverMainBrowserAfterAuthClose();
            return;
        }'''
pattern = re.compile(
    r'        if \(e\.Url\.Equals\("about:blank", StringComparison\.OrdinalIgnoreCase\)\)\s*\{.*?\n        \}',
    re.DOTALL,
)
t, n = pattern.subn(canonical, t, count=1)
if n == 0:
    # Some earlier patch combinations already omit this guard. Reinsert the
    # canonical v0.13.7 form so the v0.13.8 patch can replace it deterministically.
    marker = '''        _cefPageText = ShortPageText(e.Url);
        BeginInvokeSafe(UpdateWindowTitle);'''
    if marker not in t:
        raise SystemExit('BrowserFrameLoadEnd status marker not found for about:blank prep')
    t = t.replace(marker, marker + '\n\n' + canonical, 1)
p.write_text(t, encoding='utf-8')
print('v0.13.8 prep normalized about:blank block')
