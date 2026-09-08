from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.27 XR compile/cursor-handoff fix
#
# v0.13.27 replaced the old A/B render block with a single FULL_SBS panel, but
# the proven v0.13.14/v0.13.19 cursor handoff code below that block still uses
# stereoVisible + stereoRect/uiOverlayRects to decide whether the flat XR cursor
# should be hidden over the bare 3D viewport and re-enabled over GeoGebra UI.
#
# Keep that proven interaction policy without re-introducing B geometry:
#   * FULL_SBS remains the ONLY application content panel.
#   * stereoRect is computed only as an interaction/hit rectangle.
#   * uiOverlayRects are used only for cursor handoff.
#   * no second content panel or depth sandwich is restored.
# ---------------------------------------------------------------------------

# 1) Renderer: restore the local boolean required by the existing cursor code.
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

single_panel_marker = '''        // GGQ v0.13.27: one content panel. full-SBS is A_L|A_R and sits on
        // the exact A plane. There is no secondary B geometry and no transparent hole.
'''
require(s, single_panel_marker, 'v0.13.27 XR compilefix: single-panel marker missing')

if '        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;\n' not in s:
    s = s.replace(
        single_panel_marker,
        '''        // Interaction-only stereoVisible: this does NOT draw a B panel.
        // It exists solely for the proven cursor handoff logic below.
        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;

''' + single_panel_marker,
        1)

p.write_text(s, encoding='utf-8')


# 2) XR main: keep an A-plane 3D interaction rectangle and UI overlay rectangles
# for cursor handoff while FULL_SBS remains the only visual content source.
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

compose_block = '''                ID3D11ShaderResourceView* fullSbsSrv = nullptr;
                if (!showSplash && baseTexture_.Valid()) {
                    const bool leftReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 3 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        leftReady ? sbsTexture_.Srv() : nullptr,
                        leftReady ? &sbsFrame_ : nullptr);
                }
'''
require(s, compose_block, 'v0.13.27 XR compilefix: full-SBS compose block missing')

interaction_block = compose_block + '''
                // Interaction-only geometry for the already-solved cursor handoff.
                // MakeStereoRect historically returns the 3D rectangle at the old
                // stereo distance; RenderEye converts it back to the exact A plane.
                // Nothing is rendered at that old stereo distance in v0.13.27.
                PanelRect cursorStereoRect{};
                const bool cursorStereoValid =
                    !showSplash && sbsFrame_.active &&
                    MakeStereoRect(baseRect, cursorStereoRect);
                std::array<PanelRect, kMaxUiOverlayRects> uiOverlayRects{};
                const int uiOverlayCount = cursorStereoValid
                    ? MakeUiOverlayRects(baseRect, uiOverlayRects)
                    : 0;
'''
s = s.replace(compose_block, interaction_block, 1)

old_args = '''                        baseRect,
                        fullSbsSrv,
                        nullptr,
                        nullptr,
                        0,
                        eye == 1,'''
require(s, old_args, 'v0.13.27 XR compilefix: RenderEye full-SBS args missing')

new_args = '''                        baseRect,
                        fullSbsSrv,
                        cursorStereoValid ? &cursorStereoRect : nullptr,
                        cursorStereoValid ? uiOverlayRects.data() : nullptr,
                        uiOverlayCount,
                        eye == 1,'''
s = s.replace(old_args, new_args, 1)

p.write_text(s, encoding='utf-8')


# 3) Hard invariants: we fixed cursor handoff only; old visual B must stay gone.
render = Path('pc-xr/v11-render.hpp').read_text(encoding='utf-8')
main = Path('pc-xr/main-v11.cpp').read_text(encoding='utf-8')

for needle in (
    'const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;',
    'GGQ v0.13.27: one content panel',
    'rightEye ? 0.5f : 0.0f',
):
    require(render, needle, f'v0.13.27 XR compilefix invariant missing: {needle}')

for needle in (
    'PanelRect cursorStereoRect{};',
    'const bool cursorStereoValid =',
    'cursorStereoValid ? &cursorStereoRect : nullptr',
    'cursorStereoValid ? uiOverlayRects.data() : nullptr',
):
    require(main, needle, f'v0.13.27 XR compilefix main invariant missing: {needle}')

# Old B visual geometry must not reappear in the active single-panel content block.
if 'constexpr float behindDistance = kScreenDistanceMeters + 0.02f;' in render:
    raise SystemExit('v0.13.27 XR compilefix regression: old behind-B visual geometry returned')

print('v0.13.27 XR compile + proven cursor-handoff fix applied')
