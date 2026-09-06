from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.20 controlled performance test
#
# Change ONLY the stereo-B capture request interval from 33 ms (~30 fps target)
# to 16 ms (~62.5 fps target). Keep stereo resolution, JPEG quality, UI overlay
# policy, XR rendering and input behavior unchanged so the user's A/B comparison
# isolates capture cadence as much as possible.
# ---------------------------------------------------------------------------

p = Path('pc/pc-stereo-layout.js')
t = p.read_text(encoding='utf-8')

old = '  var CAPTURE_INTERVAL_MS = 33;'
new = '  var CAPTURE_INTERVAL_MS = 16;'
require(t, old, 'v0.13.20: 33 ms capture interval marker missing')
t = t.replace(old, new, 1)

# Add a durable marker for CI / diagnostics without changing runtime behavior.
marker = "  var CAPTURE_INTERVAL_MS = 16;\n"
t = t.replace(
    marker,
    marker + "  // v0.13.20: controlled ~60 fps stereo-B capture cadence test.\n",
    1)

p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# Version / cache-buster / package labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.19-hybrid-overlay-modal', '0.13.20-60fps-test')
    s = s.replace(r'0\.13\.19-hybrid-overlay-modal', r'0\.13\.20-60fps-test')
    s = s.replace('v0.13.19', 'v0.13.20')

    if file.endswith('MainFormV11.cs'):
        s = re.sub(
            r'(pc-stereo-layout\.js\?v=)[^"\']+',
            r'\g<1>0.13.20-60fps-test',
            s,
            count=1)

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.20</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.20.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.20.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.19-hybrid-overlay-modal-win-x64',
            'GeoGebraForQuest-PC-v0.13.20-60fps-test-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.20 ~60 fps stereo capture test patch applied')
