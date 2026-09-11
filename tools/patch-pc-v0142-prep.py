#!/usr/bin/env python3
from pathlib import Path

p = Path('tools/patch-pc-v0142-safe.py')
s = p.read_text(encoding='utf-8')

old = '''publish_marker = '                        CompleteGpuPublishLocked(cefTexture.Description);\\n'
req(g, publish_marker, 'v0.14.2: A GPU publish completion marker missing')
g = g.replace(
    publish_marker,
    publish_marker + '                        aGpuPublishedV142 = true;\\n',
    1)
'''

new = r'''# Generated v0.13.x telemetry revisions can wrap the arguments of
# CompleteGpuPublishLocked across lines. Scope the search to OnAcceleratedPaint
# and attach the clean-A success flag structurally rather than by whitespace.
paint_start = g.find('    public void OnAcceleratedPaint(')
paint_end = g.find('\n    private void EnsurePcTextureLocked', paint_start)
if paint_start < 0 or paint_end < 0:
    raise SystemExit('v0.14.2: OnAcceleratedPaint boundaries missing')
paint = g[paint_start:paint_end]
m = re.search(
    r'(?P<indent>^[ \\t]*)CompleteGpuPublishLocked\\((?P<args>.*?)\\);',
    paint,
    re.MULTILINE | re.DOTALL)
if not m:
    raise SystemExit('v0.14.2: A GPU publish completion call missing')
indent = m.group('indent')
replacement = m.group(0) + '\n' + indent + 'aGpuPublishedV142 = true;'
paint = paint[:m.start()] + replacement + paint[m.end():]
g = g[:paint_start] + paint + g[paint_end:]
'''

if old not in s:
    raise SystemExit('v0.14.2 prep: old A publish marker block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('v0.14.2 prep: resilient OnAcceleratedPaint A-publish matcher applied')
