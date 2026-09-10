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

# v0.14.1 intentionally asks CEF for 120 accelerated frames/s. The inherited
# v0.13 build script contains a historical guard that requires exactly 60 fps;
# update only that guard, not the runtime behavior itself.
p = Path('pc/build.ps1')
b = p.read_text(encoding='utf-8')
old_guard = 'if ($browserText -notmatch "WindowlessFrameRate = 60") {'
if old_guard not in b:
    raise SystemExit('v0.14.1 prep: inherited CEF 60 fps build guard missing')
b = b.replace(
    old_guard,
    'if ($browserText -notmatch "WindowlessFrameRate = 120") {',
    1)
b = b.replace(
    'CEF 60 fps tavanı korunmuyor.',
    'CEF 120 fps hedefi etkin değil.',
    1)

# v0.13.31 also hard-coded the old 16 ms CPU/raw cadence as a build invariant.
# v0.14.1 removes the serialized raw-ACK transport and deliberately uses a 1 ms
# request cadence; CEF's 120 fps accelerated-paint rate is the practical cap.
old_cadence = 'if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 16")) {'
if old_cadence not in b:
    raise SystemExit('v0.14.1 prep: inherited 16 ms raw cadence build guard missing')
b = b.replace(
    old_cadence,
    'if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 1")) {',
    1)
b = b.replace(
    '16 ms raw cadence eksik.',
    '1 ms zero-copy request cadence eksik.',
    1)
p.write_text(b, encoding='utf-8')

print('v0.14.1 prep: popup-aware latch + CEF 120 + zero-copy cadence guards applied')
