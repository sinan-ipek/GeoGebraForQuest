#!/usr/bin/env python3
from pathlib import Path

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

# The generated v0.13.x Graphics file is popup-aware. Preserve that exact popup
# branch and inject the v0.14.1 temporary-staging latch only after the View gate.
# patch-pc-v0141-host.py originally assumed an older simpler OnAcceleratedPaint
# layout, so adapt that patch itself before executing it.
p = Path('tools/patch-pc-v0141-host.py')
h = p.read_text(encoding='utf-8')

old = '''p = Path('pc/MainFormV11.Graphics.cs')
graphics = p.read_text(encoding='utf-8')
marker = \'\'\'                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                EnsurePcTextureLocked(cefTexture.Description);
\'\'\'
req(graphics, marker, 'v0.14.1: accelerated paint marker missing')
graphics = graphics.replace(
    marker,
    \'\'\'                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                if (TryConsumeGpuStereoV141PaintLocked(cefTexture))
                {
                    return;
                }

                // Ordinary A paint remains on the proven v0.13.35 path.
                EnsurePcTextureLocked(cefTexture.Description);
\'\'\',
    1)
p.write_text(graphics, encoding='utf-8')
'''

new = '''p = Path('pc/MainFormV11.Graphics.cs')
graphics = p.read_text(encoding='utf-8')
marker = \'\'\'                if (type != PaintElementType.View) return;

                EnsurePcTextureLocked(cefTexture.Description);
\'\'\'
req(graphics, marker, 'v0.14.1: popup-aware View paint marker missing')
graphics = graphics.replace(
    marker,
    \'\'\'                if (type != PaintElementType.View) return;

                if (TryConsumeGpuStereoV141PaintLocked(cefTexture))
                {
                    return;
                }

                // Ordinary A paint remains on the proven popup-aware v0.13.35 path.
                EnsurePcTextureLocked(cefTexture.Description);
\'\'\',
    1)
p.write_text(graphics, encoding='utf-8')
'''

if old not in h:
    raise SystemExit('v0.14.1 prep: host Graphics patch block not found')
h = h.replace(old, new, 1)
p.write_text(h, encoding='utf-8')

print('v0.14.1 prep: popup-aware accelerated-paint latch adapter applied')
