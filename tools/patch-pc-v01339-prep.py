#!/usr/bin/env python3
"""Build-compatibility prep for the v0.13.39 GPU full-window experiment.

This file changes no intended architecture. It only normalizes brittle textual
assumptions inherited from the generated patch chain:

1. v0.13.36 places explanatory comments between host telemetry disposal and
   LogBundle.Create(); v0.13.39 originally expected the calls to be adjacent.
2. v0.13.12 changed MakeBaseRect to support native XR splash width/height
   overrides. v0.13.39 still needs the normal application path to use exactly
   half of the final native [A_L|A_R] GPU texture width, while splash overrides
   must remain unchanged.
3. A diagnostic label's case is normalized so the patch's own final invariant
   checks the same string that it writes.
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
# v0.13.12 MakeBaseRect can be either:
#   std::max(1, baseTexture_.Width())
# or
#   std::max(1, widthOverride > 0 ? widthOverride : baseTexture_.Width())
# Preserve splash widthOverride, but halve only the normal full-SBS texture.
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
        # Formatting-tolerant fallback scoped to the width declaration.
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
# Patch self-check label normalization.
# ---------------------------------------------------------------------------
p = Path("tools/patch-pc-v01339.py")
patch = p.read_text(encoding="utf-8")
patch = patch.replace(
    'xr = xr.replace("A GPU frame consumed seq=", "FULL-SBS GPU frame consumed seq=")',
    'xr = xr.replace("A GPU frame consumed seq=", "Full-SBS GPU frame consumed seq=")',
    1,
)
p.write_text(patch, encoding="utf-8")

print("v0.13.39 prep: shutdown marker + splash-aware XR width + log label normalized")
