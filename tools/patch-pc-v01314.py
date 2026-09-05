from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.14 UI cursor handoff.
# Keep mouse-only input from v0.13.13. The XR overlay cursor is shown only
# outside the active stereo 3D viewport. Inside the 3D viewport we let the
# GeoGebra-rendered/native 3D cursor remain visually dominant, avoiding the
# parasitic double-cursor effect. Outside the 3D viewport the XR overlay remains
# available so menus/toolbars at the full panel edges are still reachable.
# ---------------------------------------------------------------------------

p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

# Make the UI overlay white instead of cyan so the handoff is visually neutral.
require(t, 'constexpr std::uint32_t fill = 0xFF00DDF5u;',
        'v0.13.14: cyan cursor fill marker missing')
t = t.replace('constexpr std::uint32_t fill = 0xFF00DDF5u;',
              'constexpr std::uint32_t fill = 0xFFFFFFFFu;', 1)

pattern = re.compile(
    r'''        const MousePointerState mouse = mouseReader_\.ReadLatest\(\);\n'''
    r'''        bool unifiedCursorValid = false;\n'''
    r'''        float unifiedCursorX = 0\.0f;\n'''
    r'''        float unifiedCursorY = 0\.0f;\n\n'''
    r'''        if \(cursorValid\) \{.*?'''
    r'''        if \(unifiedCursorValid && cursorTexture_\.Valid\(\)\) \{.*?'''
    r'''            context->OMSetBlendState\(nullptr, blendFactor, 0xffffffffu\);\n'''
    r'''        \}\n''',
    re.S)

m = pattern.search(t)
if not m:
    raise SystemExit('v0.13.14: unified cursor render block missing')

new_cursor = r'''        const MousePointerState mouse = mouseReader_.ReadLatest();
        if (mouse.valid && cursorTexture_.Valid()) {
            const float baseWidth = baseRect.right - baseRect.left;
            const float baseHeight = baseRect.top - baseRect.bottom;
            const float hitX = baseRect.left + baseWidth * mouse.u;
            const float hitY = baseRect.top - baseHeight * mouse.v;

            // The visible white GeoGebra/3D cursor is meaningful only inside the
            // active 3D viewport. Do not draw our flat XR overlay there. This avoids
            // two cursors occupying different depths. Outside the 3D viewport the
            // XR UI cursor remains active so the full toolbar/menu surface is usable.
            bool mouseInsideStereo3D = false;
            if (stereoVisible && stereoRect != nullptr) {
                const float frontToBase =
                    kScreenDistanceMeters / kStereoDistanceMeters;
                PanelRect hoverHole = ScalePanelRect(*stereoRect, frontToBase);
                hoverHole = ClampPanelRect(hoverHole, baseRect);
                mouseInsideStereo3D =
                    hitX >= hoverHole.left && hitX <= hoverHole.right &&
                    hitY <= hoverHole.top && hitY >= hoverHole.bottom;
            }

            if (!mouseInsideStereo3D) {
                const float scale =
                    kCursorDistanceMeters / kScreenDistanceMeters;
                const float mouseX = hitX * scale;
                const float mouseY = hitY * scale;
                PanelRect cursor{
                    mouseX - kCursorSizeMeters * 0.5f,
                    mouseX + kCursorSizeMeters * 0.5f,
                    mouseY + kCursorSizeMeters * 0.5f,
                    mouseY - kCursorSizeMeters * 0.5f};
                const float blendFactor[4] = {0, 0, 0, 0};
                context->OMSetBlendState(
                    cursorBlend_.Get(), blendFactor, 0xffffffffu);
                DrawQuad(
                    context, view, cursor, -kCursorDistanceMeters,
                    cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);
                context->OMSetBlendState(nullptr, blendFactor, 0xffffffffu);
            }
        }
'''

t = t[:m.start()] + new_cursor + t[m.end():]
p.write_text(t, encoding='utf-8')

# Version/package labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.13-mouse-only-test', '0.13.14-ui-cursor-handoff')
    s = s.replace(r'0\.13\.13-mouse-only-test', r'0\.13\.14-ui-cursor-handoff')
    s = s.replace('v0.13.13', 'v0.13.14')

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.14</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.14.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.14.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.13-mouse-only-test-win-x64',
            'GeoGebraForQuest-PC-v0.13.14-ui-cursor-handoff-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.14 UI cursor handoff patch applied')
