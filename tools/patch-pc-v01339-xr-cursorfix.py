#!/usr/bin/env python3
"""Compile fix for v0.13.39 XR full-window GPU stereo.

v0.13.27 carried interaction-only cursor-handoff variables next to the old
FullSbsComposer block. v0.13.39 intentionally removes that compositor block
because the host now publishes complete [A_L|A_R], but the existing RenderEye
call still references those variables.

For v0.13.39 there is no CPU stereo/MMF geometry snapshot to drive the old
3D-only cursor handoff. Keep the full-window native cursor path active and pass
an explicitly inactive interaction rectangle. This changes no stereo pixels,
no eye geometry, and no GPU transport.
"""

from pathlib import Path

p = Path("pc-xr/main-v11.cpp")
s = p.read_text(encoding="utf-8")

if "const bool cursorStereoValid = false;" not in s:
    marker = (
        "                ID3D11ShaderResourceView* fullSbsSrv =\n"
        "                    (!showSplash && baseTexture_.Valid())\n"
        "                        ? baseTexture_.Srv() : nullptr;\n\n"
        "                float cursorX = 0.0f;"
    )
    replacement = (
        "                ID3D11ShaderResourceView* fullSbsSrv =\n"
        "                    (!showSplash && baseTexture_.Valid())\n"
        "                        ? baseTexture_.Srv() : nullptr;\n\n"
        "                // v0.13.39: the full browser is already one complete per-eye\n"
        "                // panel. The old B-only cursor handoff depended on the CPU\n"
        "                // stereo snapshot that this architecture deliberately removes.\n"
        "                PanelRect cursorStereoRect{};\n"
        "                const bool cursorStereoValid = false;\n"
        "                std::array<PanelRect, kMaxUiOverlayRects> uiOverlayRects{};\n"
        "                const int uiOverlayCount = 0;\n\n"
        "                float cursorX = 0.0f;"
    )
    if marker not in s:
        raise SystemExit("v0.13.39 XR cursorfix: fullSbsSrv/cursor marker missing")
    s = s.replace(marker, replacement, 1)

for needle in (
    "PanelRect cursorStereoRect{};",
    "const bool cursorStereoValid = false;",
    "std::array<PanelRect, kMaxUiOverlayRects> uiOverlayRects{};",
    "const int uiOverlayCount = 0;",
):
    if needle not in s:
        raise SystemExit(f"v0.13.39 XR cursorfix invariant missing: {needle}")

p.write_text(s, encoding="utf-8")
print("v0.13.39 XR cursor compile regression fixed")
