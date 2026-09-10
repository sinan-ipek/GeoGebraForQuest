#!/usr/bin/env python3
"""Build-compatibility prep for the v0.13.39 GPU full-window experiment.

This file changes no intended architecture. It only normalizes two brittle
textual assumptions in the generated patch chain:

1. v0.13.36 places explanatory comments between host telemetry disposal and
   LogBundle.Create(); v0.13.39 originally expected the calls to be adjacent.
2. Different reconstructed XR baselines spell MakeBaseRect slightly
   differently. v0.13.39 requires one logical application-eye width to be
   exactly half of the final native [A_L|A_R] GPU texture width.

It also normalizes a diagnostic label's case so the patch's own final invariant
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
# The shared GPU texture produced by v0.13.39 is 2W x H = [A_L | A_R].
# MakeBaseRect must therefore use W, never 2W, for application aspect/geometry.
# Do this before the main patch so its old exact-string replacement can simply
# become a no-op on reconstructed baselines with slightly different formatting.
# ---------------------------------------------------------------------------
p = Path("pc-xr/main-v11.cpp")
xr = p.read_text(encoding="utf-8")

if "baseTexture_.Width() / 2" not in xr:
    pattern = re.compile(
        r"(?m)^(?P<indent>[ \t]*)const int width = "
        r"std::max\(1,\s*baseTexture_\.Width\(\)\);\s*$"
    )
    match = pattern.search(xr)
    if not match:
        raise SystemExit("v0.13.39 prep: MakeBaseRect baseTexture width line not found")
    indent = match.group("indent")
    replacement = (
        indent + "// v0.13.39: baseTexture_ will be native [A_L|A_R] = 2W x H.\n" +
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

print("v0.13.39 prep: shutdown marker + XR logical width + log label normalized")
