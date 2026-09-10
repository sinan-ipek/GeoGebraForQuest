#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('pc/MainFormV11.Graphics.cs')
s = p.read_text(encoding='utf-8')

# Normalize only the tiny marker consumed by patch-pc-v0141-host.py. Do not
# change behavior here. Different historical patch stacks leave harmless
# whitespace differences around OpenSharedResource1/EnsurePcTextureLocked.
pattern = re.compile(
    r'''(?P<indent>[ \t]*)using\s+var\s+cefTexture\s*=\s*_device1\.OpenSharedResource1<Texture2D>\(\s*\n?\s*acceleratedPaintInfo\.SharedTextureHandle\s*\);\s*\n\s*EnsurePcTextureLocked\(cefTexture\.Description\);''',
    re.MULTILINE,
)

m = pattern.search(s)
if not m:
    raise SystemExit('v0.14.1 graphics prep: accelerated paint anchor not found')

indent = m.group('indent')
replacement = (
    indent + 'using var cefTexture = _device1.OpenSharedResource1<Texture2D>(\n'
    + indent + '    acceleratedPaintInfo.SharedTextureHandle);\n\n'
    + indent + 'EnsurePcTextureLocked(cefTexture.Description);'
)
s = s[:m.start()] + replacement + s[m.end():]
p.write_text(s, encoding='utf-8')
print('v0.14.1 graphics prep: accelerated paint marker normalized')
