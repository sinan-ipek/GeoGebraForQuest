from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.13 mouse-only diagnostic build.
# Goal: remove the entire XR ray/controller -> CEF input path while preserving
# the PC mouse/keyboard path, stereo rendering and XR presentation unchanged.
# This isolates whether the stepped point/slider motion is caused by XR input
# sampling/routing rather than by stereo capture/presentation.
# ---------------------------------------------------------------------------

# 1) PC host: do not poll/inject XR pointer/controller input into CEF.
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
require(t, '            _inputTimer.Start();', 'v0.13.13: XR input timer start marker missing')
t = t.replace(
    '            _inputTimer.Start();',
    '            // v0.13.13 mouse-only test: XR controller input is deliberately disabled.\n'
    '            // PC mouse/keyboard remain the only GeoGebra input source.\n'
    '            _inputTimer.Stop();',
    1)
p.write_text(t, encoding='utf-8')

# 2) XR companion: do not evaluate the Touch ray and do not publish controller
# coordinates/buttons. Keep the render loop and PC mouse cursor transport intact.
p = Path('pc-xr/main-v11.cpp')
x = p.read_text(encoding='utf-8')
old_pointer = '''                float cursorX = 0.0f;
                float cursorY = 0.0f;
                const bool cursorValid = !showSplash && UpdatePointer(
                    frameState.predictedDisplayTime,
                    baseRect,
                    cursorX,
                    cursorY);'''
new_pointer = '''                float cursorX = 0.0f;
                float cursorY = 0.0f;
                // v0.13.13 mouse-only test: no Touch ray, no controller cursor,
                // no controller events are fed back into CEF.
                const bool cursorValid = false;
                inputWriter_.Publish(false, 0.0f, 0.0f, false);'''
require(x, old_pointer, 'v0.13.13: XR cursor/update block missing')
x = x.replace(old_pointer, new_pointer, 1)
p.write_text(x, encoding='utf-8')

# 3) Version/package labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.12-login-stereo-keyboard-xr-splash', '0.13.13-mouse-only-test')
    s = s.replace(r'0\.13\.12-login-stereo-keyboard-xr-splash', r'0\.13\.13-mouse-only-test')
    s = s.replace('v0.13.12', 'v0.13.13')

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.13</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.13.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.13.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.12-login-stereo-keyboard-xr-splash-win-x64',
            'GeoGebraForQuest-PC-v0.13.13-mouse-only-test-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.13 mouse-only test patch applied')
