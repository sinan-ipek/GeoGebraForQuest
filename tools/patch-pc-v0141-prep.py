#!/usr/bin/env python3
from pathlib import Path

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
print('v0.14.1 prep: shutdown/log bundle marker normalized')
