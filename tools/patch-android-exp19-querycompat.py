#!/usr/bin/env python3
"""Exp19 compatibility fix for Meta Spatial Query filter results.

The filtered Query result is iterable but is not a Kotlin Collection, so
isNotEmpty() is unavailable. Consume at most one recovery-frame tick from inside
the controller loop instead. This preserves the intended 180-frame recovery
window and does not expire it while no local controller entity is present.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp19-querycompat.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
text = path.read_text(encoding="utf-8")

if "EXP19_QUERY_RESULT_COMPAT" in text:
    print("[GGQ] exp19 Query-result compatibility patch already present")
    raise SystemExit(0)

old = '''        val forceInputRecovery = inputRecoveryFrames > 0
        if (forceInputRecovery && controllers.isNotEmpty()) {
            inputRecoveryFrames--
        }

        for (entity in controllers) {
'''
new = '''        val forceInputRecovery = inputRecoveryFrames > 0
        // EXP19_QUERY_RESULT_COMPAT: Query.filter() is iterable but is not a Kotlin
        // Collection, so do not call isNotEmpty(). Consume one recovery tick only
        // after a real local controller entity is observed this Spatial frame.
        var recoveryFrameConsumed = false

        for (entity in controllers) {
            if (forceInputRecovery && !recoveryFrameConsumed) {
                inputRecoveryFrames--
                recoveryFrameConsumed = true
            }
'''

if old not in text:
    raise RuntimeError("exp19 Query-result compatibility anchor not found")
text = text.replace(old, new, 1)

for required in (
    "EXP19_QUERY_RESULT_COMPAT",
    "var recoveryFrameConsumed = false",
    "forceInputRecovery && !recoveryFrameConsumed",
    "inputRecoveryFrames--",
):
    if required not in text:
        raise RuntimeError(f"exp19 Query compatibility requirement missing: {required}")

if "controllers.isNotEmpty()" in text:
    raise RuntimeError("exp19 incompatible controllers.isNotEmpty() call remains")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp19 Meta Spatial Query-result compatibility installed")
