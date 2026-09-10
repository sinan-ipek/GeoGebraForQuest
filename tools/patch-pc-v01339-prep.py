#!/usr/bin/env python3
"""Build-compatibility prep for the v0.13.39 GPU full-window experiment.

This file changes no intended stereo architecture. It normalizes brittle
textual assumptions inherited from the generated patch chain and preserves the
existing RenderEye call contract after the legacy CPU stereo block is removed.
"""

from pathlib import Path
import re


# ---------------------------------------------------------------------------
# Host shutdown marker normalization. Runtime behavior is unchanged.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
s = p.read_text(encoding="utf-8")

old = (
    "        _performanceTelemetry.Dispose();\n"
    "        // v0.13.36: one user-facing diagnostics bundle. XR is already\n"
    "        // stopped above and host telemetry writers are now closed.\n"
    "        LogBundle.Create();\n"
)
new = (
    "        _performanceTelemetry.Dispose();\n"
    "        LogBundle.Create();\n"
)

if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit("v0.13.39 prep: v0.13.36 log bundle shutdown block not found")

p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# XR logical width normalization.
# v0.13.12 MakeBaseRect supports native XR splash width/height overrides.
# Preserve those overrides, but halve only the normal full-SBS base texture.
# ---------------------------------------------------------------------------
p = Path("pc-xr/main-v11.cpp")
xr = p.read_text(encoding="utf-8")

if "baseTexture_.Width() / 2" not in xr:
    splash_old = (
        "        const int width = std::max(1, "
        "widthOverride > 0 ? widthOverride : baseTexture_.Width());"
    )
    splash_new = (
        "        // v0.13.39: normal baseTexture_ is native [A_L|A_R] = 2W x H;\n"
        "        // native splash dimensions are already single-eye dimensions.\n"
        "        const int width = std::max(1, widthOverride > 0\n"
        "            ? widthOverride : baseTexture_.Width() / 2);"
    )
    plain_old = "        const int width = std::max(1, baseTexture_.Width());"
    plain_new = (
        "        // v0.13.39: baseTexture_ is native [A_L|A_R] = 2W x H.\n"
        "        const int width = std::max(1, baseTexture_.Width() / 2);"
    )

    if splash_old in xr:
        xr = xr.replace(splash_old, splash_new, 1)
    elif plain_old in xr:
        xr = xr.replace(plain_old, plain_new, 1)
    else:
        pattern = re.compile(
            r"(?m)^(?P<indent>[ \t]*)const int width = std::max\(1,\s*"
            r"(?:(?:widthOverride\s*>\s*0\s*\?\s*widthOverride\s*:\s*)?)"
            r"baseTexture_\.Width\(\)\);\s*$"
        )
        match = pattern.search(xr)
        if not match:
            raise SystemExit("v0.13.39 prep: MakeBaseRect baseTexture width line not found")
        indent = match.group("indent")
        original = match.group(0)
        if "widthOverride" in original:
            replacement = (
                indent + "// v0.13.39: normal baseTexture_ is native [A_L|A_R] = 2W x H;\n" +
                indent + "// native splash dimensions remain single-eye dimensions.\n" +
                indent + "const int width = std::max(1, widthOverride > 0\n" +
                indent + "    ? widthOverride : baseTexture_.Width() / 2);"
            )
        else:
            replacement = (
                indent + "// v0.13.39: baseTexture_ is native [A_L|A_R] = 2W x H.\n" +
                indent + "const int width = std::max(1, baseTexture_.Width() / 2);"
            )
        xr = xr[:match.start()] + replacement + xr[match.end():]

p.write_text(xr, encoding="utf-8")


# ---------------------------------------------------------------------------
# Normalize the v0.13.39 patch itself before it runs.
# ---------------------------------------------------------------------------
p = Path("tools/patch-pc-v01339.py")
patch = p.read_text(encoding="utf-8")

# Diagnostic label: final invariant expects this exact case.
patch = patch.replace(
    'xr = xr.replace("A GPU frame consumed seq=", "FULL-SBS GPU frame consumed seq=")',
    'xr = xr.replace("A GPU frame consumed seq=", "Full-SBS GPU frame consumed seq=")',
    1,
)

# v0.13.27's RenderEye call still passes interaction-only cursor-handoff
# arguments. The variables used to live beside FullSbsComposer and were
# accidentally deleted when v0.13.39 removed that block. v0.13.39 has no CPU
# stereo snapshot driving the old B-only handoff, so preserve the call contract
# with an explicitly inactive interaction rectangle. The normal full-window XR
# cursor remains active; stereo pixels/eye geometry are untouched.
old_emit = (
    '    "                ID3D11ShaderResourceView* fullSbsSrv =\\n"\n'
    '    "                    (!showSplash && baseTexture_.Valid())\\n"\n'
    '    "                        ? baseTexture_.Srv() : nullptr;\\n" +\n'
)
new_emit = (
    '    "                ID3D11ShaderResourceView* fullSbsSrv =\\n"\n'
    '    "                    (!showSplash && baseTexture_.Valid())\\n"\n'
    '    "                        ? baseTexture_.Srv() : nullptr;\\n"\n'
    '    "                PanelRect cursorStereoRect{};\\n"\n'
    '    "                const bool cursorStereoValid = false;\\n"\n'
    '    "                std::array<PanelRect, kMaxUiOverlayRects> uiOverlayRects{};\\n"\n'
    '    "                const int uiOverlayCount = 0;\\n" +\n'
)
if old_emit in patch:
    patch = patch.replace(old_emit, new_emit, 1)
elif "const bool cursorStereoValid = false;" not in patch:
    raise SystemExit("v0.13.39 prep: fullSbsSrv emit block not found in patch")

p.write_text(patch, encoding="utf-8")

print("v0.13.39 prep: shutdown + XR width + cursor contract + log label normalized")
