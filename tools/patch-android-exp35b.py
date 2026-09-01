#!/usr/bin/env python3
"""Exp35b: make right-thumb zoom repeat independent of controller iteration order."""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp35b.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
text = path.read_text(encoding="utf-8")

if "EXP35_RIGHT_THUMB_DETERMINISTIC_ZOOM" not in text:
    raise RuntimeError("exp35b requires exp35 shortcut patch first")

text = text.replace("    private var lastThumbZoomDirection = 0\n", "", 1)

old = '''                if (
                    thumbDirection != lastThumbZoomDirection ||
                    now - lastThumbZoomAtMs >= thumbZoomRepeatMs
                ) {
                    activity.onQuestRightThumbZoom(zoomIn = thumbDirection > 0)
                    lastThumbZoomAtMs = now
                }
            }
            if (thumbDirection == 0) {
                lastThumbZoomDirection = 0
            } else {
                lastThumbZoomDirection = thumbDirection
            }
'''
new = '''                if (now - lastThumbZoomAtMs >= thumbZoomRepeatMs) {
                    activity.onQuestRightThumbZoom(zoomIn = thumbDirection > 0)
                    lastThumbZoomAtMs = now
                }
            }
'''
if old not in text:
    raise RuntimeError("exp35b old direction-sensitive repeat block not found")
text = text.replace(old, new, 1)

if "lastThumbZoomDirection" in text:
    raise RuntimeError("exp35b direction state residue remains")
if "now - lastThumbZoomAtMs >= thumbZoomRepeatMs" not in text:
    raise RuntimeError("exp35b time-only repeat guard missing")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp35b right-thumb repeat isolated from left-controller iteration")
