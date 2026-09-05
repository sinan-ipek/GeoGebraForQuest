from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.16 cursor hotspot fix.
#
# The XR overlay cursor texture is a rotated triangular pointer. Until now the
# logical mouse coordinate was placed at the CENTER of the cursor quad, while the
# visible pointer tip is near the lower-left quarter of the 40x40 texture.
# Therefore the visible tip and the actual GeoGebra click/hit-test point did not
# coincide.
#
# Keep mouse coordinates/input untouched. Only reposition the visual cursor quad
# so that the triangle TIP is anchored exactly at the logical mouse coordinate.
# ---------------------------------------------------------------------------

p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

old = '''                PanelRect cursor{
                    mouseX - kCursorSizeMeters * 0.5f,
                    mouseX + kCursorSizeMeters * 0.5f,
                    mouseY + kCursorSizeMeters * 0.5f,
                    mouseY - kCursorSizeMeters * 0.5f};'''

new = '''                // The generated 40x40 triangle is rotated 45 degrees and its
                // visible tip lies at approximately (u=0.25, v=0.75) in texture
                // coordinates. Anchor that tip, not the quad centre, to the real
                // mouse coordinate. This makes what the user points at exactly what
                // GeoGebra receives for hover/click/point placement.
                constexpr float kCursorHotspotU = 0.25f;
                constexpr float kCursorHotspotV = 0.75f;
                const float cursorLeft =
                    mouseX - kCursorSizeMeters * kCursorHotspotU;
                const float cursorTop =
                    mouseY + kCursorSizeMeters * kCursorHotspotV;
                PanelRect cursor{
                    cursorLeft,
                    cursorLeft + kCursorSizeMeters,
                    cursorTop,
                    cursorTop - kCursorSizeMeters};'''

require(t, old, 'v0.13.16: centred mouse cursor quad block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

# Version/package labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.15-stereo-hit-alignment', '0.13.16-cursor-hotspot')
    s = s.replace(r'0\.13\.15-stereo-hit-alignment', r'0\.13\.16-cursor-hotspot')
    s = s.replace('v0.13.15', 'v0.13.16')

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.16</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.16.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.16.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.15-stereo-hit-alignment-win-x64',
            'GeoGebraForQuest-PC-v0.13.16-cursor-hotspot-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.16 cursor hotspot fix applied')
