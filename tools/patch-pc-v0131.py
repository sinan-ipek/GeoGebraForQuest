from pathlib import Path
import re


def rep(path, old, new, count=None):
    p = Path(path)
    t = p.read_text(encoding='utf-8')
    n = t.count(old)
    if n == 0:
        raise SystemExit(f'Missing fragment in {path}: {old[:120]!r}')
    if count is not None and n != count:
        raise SystemExit(f'Expected {count}, got {n} in {path}: {old[:120]!r}')
    p.write_text(t.replace(old, new), encoding='utf-8')

# 1) Slightly LOWER XR supersampling. Keep high-res CEF and stereo sources intact;
# only reduce the final per-eye OpenXR target to avoid unnecessary resampling.
rep('pc-xr/main-v13fixed.cpp',
    'constexpr float kRenderQualityScale = 1.25f;',
    'constexpr float kRenderQualityScale = 1.15f;', 1)
rep('pc-xr/main-v13fixed.cpp',
    'v0.13 eye target = OpenXR recommended x1.25, clamped to Quest3 physical/runtime max',
    'v0.13.1 eye target = OpenXR recommended x1.15, clamped to Quest3 physical/runtime max', 1)

# 2) Close the visual seam between A and B. B was 20 mm behind A; move it to
# 6 mm and add a tiny overscan. A's opaque rim masks the overlap, so no visible
# stretching should escape the 3D hole.
p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')
old = '''            constexpr float behindDistance = kScreenDistanceMeters + 0.02f;\n            const float baseToBehind = behindDistance / kScreenDistanceMeters;\n            const PanelRect behindStereo =\n                ScalePanelRect(baseHole, baseToBehind);'''
new = '''            constexpr float behindDistance = kScreenDistanceMeters + 0.006f;\n            const float baseToBehind = behindDistance / kScreenDistanceMeters;\n            PanelRect behindStereo = ScalePanelRect(baseHole, baseToBehind);\n\n            // Slight hidden overscan prevents a dark seam at the cutout edge.\n            // The front A panel masks this overlap.\n            const float overscanX =\n                (behindStereo.right - behindStereo.left) * 0.006f;\n            const float overscanY =\n                (behindStereo.top - behindStereo.bottom) * 0.006f;\n            behindStereo.left -= overscanX;\n            behindStereo.right += overscanX;\n            behindStereo.top += overscanY;\n            behindStereo.bottom -= overscanY;'''
if old not in t:
    raise SystemExit('behindDistance block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

# 3) Quest/runtime STOPPING must actually terminate the XR companion. Previously
# STOPPING merely ended the session and the helper kept waiting because the PC
# host process was still alive.
p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')
old = '''                        sessionRunning_ = false;\n                        triggerDown_ = false;\n                        inputWriter_.Publish(false, 0.0f, 0.0f, false);'''
new = '''                        sessionRunning_ = false;\n                        triggerDown_ = false;\n                        inputWriter_.Publish(false, 0.0f, 0.0f, false);\n                        // Runtime STOPPING means the headset has closed this XR app.\n                        // Do not leave the companion process alive behind the scenes.\n                        exitRequested_ = true;\n                        Log("XR STOPPING -> companion exit requested");'''
if old not in t:
    raise SystemExit('STOPPING session block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

# Version/package labels after the v0.13 base patch has run. Normalize whatever
# exact 0.13.x spelling the base script produced.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.13-fixed-xr-surface', '0.13.1-tuning-exit')
    t = t.replace(r'0\.13-fixed-xr-surface', r'0\.13\.1-tuning-exit')
    t = t.replace('v0.13 ·', 'v0.13.1 ·')
    t = t.replace('[GGQ-PC v0.13]', '[GGQ-PC v0.13.1]')
    if file.endswith('.csproj'):
        t = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.1</Version>', t, count=1)
        t = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.1.0</FileVersion>', t, count=1)
        t = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.1.0</AssemblyVersion>', t, count=1)
    p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.1 tuning applied')
