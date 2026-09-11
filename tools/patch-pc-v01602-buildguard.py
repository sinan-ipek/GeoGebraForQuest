#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('pc/build.ps1')
b = p.read_text(encoding='utf-8')

pattern = re.compile(
    r'if \(\$mainFormText -notmatch "[^"]+"\) \{(?=\n\s*throw "[^"]*stereo runtime cache-busting)',
    re.MULTILINE,
)
replacement = 'if ($mainFormText -notmatch "0\\.16\\.0-gpu-eye-pair") {'
b2, count = pattern.subn(replacement, b, count=1)
if count != 1:
    raise SystemExit('v0.16.2 buildguard: cache-busting guard not found exactly once')

p.write_text(b2, encoding='utf-8')
print('[GGQ] v0.16.2 cache-busting build guard updated')
