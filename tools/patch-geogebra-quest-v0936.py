#!/usr/bin/env python3
"""Exp45: calibrate GeoGebra glasses projection for the fixed Quest panel.

The GeoGebra desktop glasses defaults (2500 px eye-to-screen distance and
200 px eye separation) provide strong binocular parallax but very weak
single-eye perspective on GeoGebraForQuest's 1080 dp / 1.50 m panel.

At the panel's nominal 1.50 m viewing distance, its density is 720 px/m:
  eye-to-screen = 1.50 m * 720 px/m = 1080 px
  eye separation = 0.064 m * 720 px/m = 46.08 px -> 46 px

Keep the pair fixed for this Quest build.  Clamping the settings setters is
intentional: an older .ggb XML payload must not silently restore the desktop
2500/200 calibration after a material is opened.
"""

from pathlib import Path
import sys


QUEST_EYE_TO_SCREEN_PX = 1080
QUEST_EYE_SEPARATION_PX = 46


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0936.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
settings_path = root / (
    "source/shared/common/src/main/java/org/geogebra/common/main/settings/"
    "EuclidianSettings3D.java"
)
view_path = root / (
    "source/shared/common/src/main/java/org/geogebra/common/geogebra3D/"
    "euclidian3D/EuclidianView3D.java"
)

settings = settings_path.read_text(encoding="utf-8")
view = view_path.read_text(encoding="utf-8")

if "GGQ_EXP45_QUEST_PERSPECTIVE_CALIBRATION" in settings:
    print("[GGQ] exp45 Quest perspective calibration already present")
    raise SystemExit(0)

settings = replace_once(
    settings,
    "\tpublic static final int EYE_SEP_DEFAULT = 200;",
    "\t// GGQ_EXP45_QUEST_PERSPECTIVE_CALIBRATION: nominal 64 mm IPD on\n"
    "\t// the 1080 px / 1.50 m Quest panel.\n"
    f"\tpublic static final int EYE_SEP_DEFAULT = {QUEST_EYE_SEPARATION_PX};",
    "Quest eye-separation default",
)
settings = replace_once(
    settings,
    "\tpublic static final int PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = 2500;",
    "\t// Exp45: 1.50 m nominal viewer distance at 720 panel pixels/metre.\n"
    "\tpublic static final int PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = "
    f"{QUEST_EYE_TO_SCREEN_PX};",
    "Quest eye-to-screen default",
)
settings = replace_once(
    settings,
    "\tpublic void setProjectionPerspectiveEyeDistance(int distance) {\n"
    "\t\tif (projectionPerspectiveEyeDistance != distance) {\n"
    "\t\t\tprojectionPerspectiveEyeDistance = distance;\n"
    "\t\t\tsettingChanged();\n"
    "\t\t}\n"
    "\t}",
    "\tpublic void setProjectionPerspectiveEyeDistance(int distance) {\n"
    "\t\t// Exp45: ignore desktop/XML calibration in the fixed Quest layout.\n"
    "\t\tint questDistance = PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT;\n"
    "\t\tif (projectionPerspectiveEyeDistance != questDistance) {\n"
    "\t\t\tprojectionPerspectiveEyeDistance = questDistance;\n"
    "\t\t\tsettingChanged();\n"
    "\t\t}\n"
    "\t}",
    "clamp Quest eye-to-screen distance",
)
settings = replace_once(
    settings,
    "\tpublic void setEyeSep(int value) {\n"
    "\t\tif (eyeSep != value) {\n"
    "\t\t\teyeSep = value;\n"
    "\t\t\tsettingChanged();\n"
    "\t\t}\n"
    "\t}",
    "\tpublic void setEyeSep(int value) {\n"
    "\t\t// Exp45: keep IPD and focal distance as one matched calibration.\n"
    "\t\tint questSeparation = EYE_SEP_DEFAULT;\n"
    "\t\tif (eyeSep != questSeparation) {\n"
    "\t\t\teyeSep = questSeparation;\n"
    "\t\t\tsettingChanged();\n"
    "\t\t}\n"
    "\t}",
    "clamp Quest eye separation",
)

view = replace_once(
    view,
    "\tprivate static final int PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = 2500;",
    "\t// Exp45 keeps constructor-time projection values consistent with settings.\n"
    "\tprivate static final int PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = "
    f"{QUEST_EYE_TO_SCREEN_PX};",
    "Quest view constructor eye distance",
)

for required in (
    "GGQ_EXP45_QUEST_PERSPECTIVE_CALIBRATION",
    "EYE_SEP_DEFAULT = 46",
    "PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = 1080",
    "int questDistance = PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT",
    "int questSeparation = EYE_SEP_DEFAULT",
):
    if required not in settings + view:
        raise RuntimeError(f"exp45 calibration requirement missing: {required}")

for forbidden in (
    "EYE_SEP_DEFAULT = 200",
    "PROJECTION_PERSPECTIVE_EYE_DISTANCE_DEFAULT = 2500",
):
    if forbidden in settings + view:
        raise RuntimeError(f"exp45 desktop calibration remains: {forbidden}")

settings_path.write_text(settings, encoding="utf-8")
view_path.write_text(view, encoding="utf-8")
print("[GGQ] exp45 Quest perspective calibrated to eyeDistance=1080, eyeSep=46")
