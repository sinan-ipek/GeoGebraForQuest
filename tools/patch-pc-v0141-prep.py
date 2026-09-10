#!/usr/bin/env python3
from pathlib import Path
import re

# Normalize the shutdown/log-bundle marker expected by the v0.14.1 host patch.
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

needle = '        _performanceTelemetry.Dispose();\n'
if needle not in s:
    raise SystemExit('v0.14.1 prep: performance telemetry shutdown marker missing')

if '        LogBundle.Create();\n' not in s:
    s = s.replace(
        needle,
        needle + '        LogBundle.Create();\n',
        1)

p.write_text(s, encoding='utf-8')

# Historical build patches leave harmless whitespace differences around the
# accelerated-paint anchor. Normalize only that anchor; no behavior changes here.
p = Path('pc/MainFormV11.Graphics.cs')
g = p.read_text(encoding='utf-8')

pattern = re.compile(
    r'''(?P<indent>[ \t]*)using\s+var\s+cefTexture\s*=\s*_device1\.OpenSharedResource1<Texture2D>\(\s*\n?\s*acceleratedPaintInfo\.SharedTextureHandle\s*\);\s*\n\s*EnsurePcTextureLocked\(cefTexture\.Description\);''',
    re.MULTILINE,
)
match = pattern.search(g)
if not match:
    raise SystemExit('v0.14.1 prep: accelerated paint anchor not found')

indent = match.group('indent')
replacement = (
    indent + 'using var cefTexture = _device1.OpenSharedResource1<Texture2D>(\n'
    + indent + '    acceleratedPaintInfo.SharedTextureHandle);\n\n'
    + indent + 'EnsurePcTextureLocked(cefTexture.Description);'
)
g = g[:match.start()] + replacement + g[match.end():]
p.write_text(g, encoding='utf-8')

print('v0.14.1 prep: shutdown and accelerated-paint markers normalized')
