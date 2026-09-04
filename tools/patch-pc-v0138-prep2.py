from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
pattern = re.compile(
    r'        if \(e\.Url\.Equals\("about:blank", StringComparison\.OrdinalIgnoreCase\)\)\s*\{.*?\n        \}',
    re.DOTALL,
)
canonical = '''        if (e.Url.Equals("about:blank", StringComparison.OrdinalIgnoreCase))\n        {\n            RecoverMainBrowserAfterAuthClose();\n            return;\n        }'''
t, n = pattern.subn(canonical, t, count=1)
if n != 1:
    raise SystemExit('could not normalize v0.13.7 about:blank block')
p.write_text(t, encoding='utf-8')
print('v0.13.8 prep normalized about:blank block')
