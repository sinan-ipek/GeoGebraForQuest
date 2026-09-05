from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.15 stereo hit-alignment fix.
#
# v0.13.1 enlarged the B quad by 0.6% on every side to hide the thin seam at
# the A/B cutout boundary. That also enlarged the visible stereo image itself,
# while mouse hit-testing stayed in the original CEF/A coordinate system.
# Result: a point could look visually under the cursor in B but require a small
# radial mouse offset to hit it.
#
# Keep the seam protection, but split it into two passes:
#   1) an enlarged guard quad under the real image;
#   2) the exact angular stereo quad drawn on top with the unmodified UV map.
# The guard is visible only in sub-pixel/raster cracks around the cutout edge;
# the full visible 3D area now has a 1:1 angular mapping with the logical CEF
# viewport used for mouse hit-testing.
# ---------------------------------------------------------------------------

p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

old_geometry = '''            constexpr float behindDistance = kScreenDistanceMeters + 0.006f;
            const float baseToBehind = behindDistance / kScreenDistanceMeters;
            PanelRect behindStereo = ScalePanelRect(baseHole, baseToBehind);

            // Slight hidden overscan prevents a dark seam at the cutout edge.
            // The front A panel masks this overlap.
            const float overscanX =
                (behindStereo.right - behindStereo.left) * 0.006f;
            const float overscanY =
                (behindStereo.top - behindStereo.bottom) * 0.006f;
            behindStereo.left -= overscanX;
            behindStereo.right += overscanX;
            behindStereo.top += overscanY;
            behindStereo.bottom -= overscanY;'''

new_geometry = '''            constexpr float behindDistance = kScreenDistanceMeters + 0.006f;
            const float baseToBehind = behindDistance / kScreenDistanceMeters;

            // Exact stereo quad: this is the only B geometry that should be visible
            // inside the 3D hole. Its angular boundary is exactly the same as the
            // original CEF/GeoGebra 3D viewport used for mouse hit-testing.
            const PanelRect behindStereoExact =
                ScalePanelRect(baseHole, baseToBehind);

            // Seam guard: slightly enlarge a second quad underneath the exact one.
            // A is drawn afterwards and masks the guard outside the hole. Because the
            // exact quad is drawn on top, this guard cannot scale/shift the visible B
            // content and therefore cannot alter mouse-to-object alignment.
            PanelRect behindStereoGuard = behindStereoExact;
            const float overscanX =
                (behindStereoGuard.right - behindStereoGuard.left) * 0.006f;
            const float overscanY =
                (behindStereoGuard.top - behindStereoGuard.bottom) * 0.006f;
            behindStereoGuard.left -= overscanX;
            behindStereoGuard.right += overscanX;
            behindStereoGuard.top += overscanY;
            behindStereoGuard.bottom -= overscanY;'''

require(t, old_geometry, 'v0.13.15: v0.13.1 overscan geometry block missing')
t = t.replace(old_geometry, new_geometry, 1)

old_draw = '''            // B first. It is geometrically behind A.
            DrawQuad(
                context, view, behindStereo, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);'''

new_draw = '''            // Guard first: only covers possible sub-pixel seams around the cutout.
            DrawQuad(
                context, view, behindStereoGuard, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);

            // Exact B second: preserves the original GeoGebra viewport mapping.
            // With no depth buffer attached, the later draw deterministically
            // overwrites the guard throughout the real stereo viewport.
            DrawQuad(
                context, view, behindStereoExact, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);'''

require(t, old_draw, 'v0.13.15: stereo B draw block missing')
t = t.replace(old_draw, new_draw, 1)
p.write_text(t, encoding='utf-8')

# Version/package labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.14-ui-cursor-handoff', '0.13.15-stereo-hit-alignment')
    s = s.replace(r'0\.13\.14-ui-cursor-handoff', r'0\.13\.15-stereo-hit-alignment')
    s = s.replace('v0.13.14', 'v0.13.15')

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.15</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.15.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.15.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.14-ui-cursor-handoff-win-x64',
            'GeoGebraForQuest-PC-v0.13.15-stereo-hit-alignment-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.15 stereo hit-alignment fix applied')
