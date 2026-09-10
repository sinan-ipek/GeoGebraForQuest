#!/usr/bin/env python3
"""Normalize the v0.13.36 shutdown block for the v0.13.39 patch.

v0.13.36 intentionally inserts explanatory comments between
_performanceTelemetry.Dispose() and LogBundle.Create().  The first v0.13.39
patch expected those two calls to be adjacent.  This prep is build-only: it
removes only those comments and changes no runtime behavior.
"""

from pathlib import Path

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
print("v0.13.39 prep: log bundle shutdown marker normalized")
