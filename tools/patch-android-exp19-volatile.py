#!/usr/bin/env python3
"""Exp19 final guard: make Spatial input recovery cross-thread visible.

SpatialGeoGebraActivity requests recovery from Android lifecycle callbacks while
QuestControllerShortcutSystem consumes the recovery counter on the Spatial system
thread. Mark the counter volatile so a resume/file-picker edge cannot be missed
because of JVM cross-thread visibility.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp19-volatile.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
text = path.read_text(encoding="utf-8")

if "@Volatile\n    private var inputRecoveryFrames = 0" in text:
    print("[GGQ] exp19 volatile input recovery already present")
    raise SystemExit(0)

anchor = "    private var inputRecoveryFrames = 0\n"
replacement = "    @Volatile\n    private var inputRecoveryFrames = 0\n"

if anchor not in text:
    raise RuntimeError("exp19 volatile recovery counter anchor not found")

text = text.replace(anchor, replacement, 1)

for required in (
    "EXP19_INPUT_RECOVERY_WINDOW",
    "@Volatile\n    private var inputRecoveryFrames = 0",
    "internal fun requestInputRecovery(frames: Int = 180)",
    "forceInputRecovery || !controller.laserEnabled",
):
    if required not in text:
        raise RuntimeError(f"exp19 volatile requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp19 Spatial input recovery counter made volatile")
