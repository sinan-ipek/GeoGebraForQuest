from pathlib import Path
import re

p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

canonical = r'''        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;
        if (stereoVisible) {
            // The old v0.12 geometry was calculated for a panel 2 cm IN FRONT of A.
            // Convert it back to A's exact 3D viewport, then place B 2 cm BEHIND A
            // while preserving the same angular boundary in the headset.
            const float frontToBase =
                kScreenDistanceMeters / kStereoDistanceMeters;
            PanelRect baseHole = ScalePanelRect(*stereoRect, frontToBase);
            baseHole = ClampPanelRect(baseHole, baseRect);

            constexpr float behindDistance = kScreenDistanceMeters + 0.02f;
            const float baseToBehind = behindDistance / kScreenDistanceMeters;
            const PanelRect behindStereo =
                ScalePanelRect(baseHole, baseToBehind);

            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;

            // B first. It is geometrically behind A.
            DrawQuad(
                context, view, behindStereo, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);

            // A second, but with the exact 3D viewport omitted. This is the XR-only
            // transparent 3D window: PC still receives the untouched full CEF image.
            if (baseSrv) {
                DrawBaseWithHole(
                    context, view, baseRect, baseHole, baseSrv);
            }
        } else if (baseSrv) {
            // When a GeoGebra menu/dialog covers 3D, JS marks B inactive. Then A is
            // completely opaque again, so menus can never be hidden behind B.
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
        }
'''

pattern = r'        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;\n.*?(?=        const MousePointerState mouse)'
out, count = re.subn(pattern, canonical, s, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f'v0.13.26 prep: XR stereo region replacements={count}')

p.write_text(out, encoding='utf-8')
print('v0.13.26 prep: XR stereo block normalized')
