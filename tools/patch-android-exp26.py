#!/usr/bin/env python3
"""Exp26: freeze Bug 1 and repair only spatial picker input routing for Bug 2.

Bug 1
-----
Frozen exactly at Exp25. Do not alter popup/login/navigation behavior.

Bug 2
-----
Exp25 proved that the embedded Activity container now survives and renders
DocumentsUI, but file rows cannot be clicked. Compare the picker panel with Meta's
current SpatialVideoSample ActivityPanelRegistration: Meta forwards ButtonA plus
both controller triggers and keeps the Activity panel as an independent scene
panel. Exp25 forwarded only the two triggers and parented the picker under A.

Exp26 therefore:
- gives the picker the exact Meta-style ButtonA | TriggerL | TriggerR input mask;
- makes the picker a standalone world-space Activity panel rather than a child of A;
- suspends GGQ A/B/Grip shortcuts while the picker exists so picker input cannot
  also trigger GeoGebra shortcuts behind it.
No login/popup code is modified.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp26.py <repo-root>")

root = Path(sys.argv[1]).resolve()
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"

activity = activity_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")
panel = panel_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Picker input: exactly match Meta's ActivityPanel sample button mask.
# ---------------------------------------------------------------------------
marker = "ActivityPanelRegistration(\n                registrationId = R.id.local_file_picker_panel,"
pos = activity.find(marker)
if pos < 0:
    raise RuntimeError("exp26 picker ActivityPanelRegistration not found")
block_end = activity.find("            VideoSurfacePanelRegistration(", pos)
if block_end < 0:
    raise RuntimeError("exp26 picker registration end not found")
block = activity[pos:block_end]
old_mask = """PanelInputOptions(\n                            ButtonBits.ButtonTriggerL or ButtonBits.ButtonTriggerR,\n                        )"""
new_mask = """// EXP26_META_PICKER_INPUT_MASK: match Meta's working ActivityPanel sample.\n                        PanelInputOptions(\n                            ButtonBits.ButtonA or\n                                ButtonBits.ButtonTriggerL or\n                                ButtonBits.ButtonTriggerR,\n                        )"""
if old_mask in block:
    block = block.replace(old_mask, new_mask, 1)
elif "EXP26_META_PICKER_INPUT_MASK" not in block:
    raise RuntimeError("exp26 picker input mask anchor not found")
activity = activity[:pos] + block + activity[block_end:]

# ---------------------------------------------------------------------------
# Picker entity: make it standalone like Meta's ActivityPanel example.
# ---------------------------------------------------------------------------
old_entity = '''        val geoPanel = geoPanelEntity ?: run {
            GeoGebraLocalFilePicker.deliverSpatialPickerResult(null)
            return
        }

        spatialFilePickerPanelEntity = Entity.create(
            Panel(R.id.local_file_picker_panel),
            TransformParent(geoPanel),
            // Slightly in front of A while the file browser is open.
            Transform(Pose(Vector3(0f, 0f, -0.025f))),
            Scale(Vector3(0.96f, 0.96f, 1f)),
            Grabbable(false),
        )
'''
new_entity = '''        if (geoPanelEntity == null) {
            GeoGebraLocalFilePicker.deliverSpatialPickerResult(null)
            return
        }

        // EXP26_STANDALONE_PICKER_PANEL: Meta's working ActivityPanel sample is a
        // top-level scene panel. Do not nest DocumentsUI under A's panel/input tree.
        spatialFilePickerPanelEntity = Entity.create(
            Panel(R.id.local_file_picker_panel),
            Transform(Pose(Vector3(0f, 1.25f, 1.44f))),
            Scale(Vector3(0.96f, 0.96f, 1f)),
            Grabbable(false),
        )
'''
if old_entity in activity:
    activity = activity.replace(old_entity, new_entity, 1)
elif "EXP26_STANDALONE_PICKER_PANEL" not in activity:
    raise RuntimeError("exp26 picker entity anchor not found")

# Expose one read-only state predicate to the controller shortcut system.
method_anchor = '''    internal fun onQuestAButtonPressed() {
'''
if "EXP26_PICKER_INPUT_EXCLUSIVE" not in activity:
    methods = '''    // EXP26_PICKER_INPUT_EXCLUSIVE: while DocumentsUI is visible, all native
    // controller button input belongs to that ActivityPanel, not GGQ shortcuts.
    internal fun isSpatialFilePickerActive(): Boolean =
        spatialFilePickerPanelEntity != null || spatialFilePickerOpenRequested

''' + method_anchor
    if method_anchor not in activity:
        raise RuntimeError("exp26 shortcut-state method anchor not found")
    activity = activity.replace(method_anchor, methods, 1)

# Shortcut system only observes controller state; skip GGQ A/B/Grip actions while
# the picker panel is active so ButtonA can be delivered exclusively as panel input.
execute_anchor = '''    override fun execute() {
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
'''
execute_replacement = '''    override fun execute() {
        if (activity.isSpatialFilePickerActive()) return
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
'''
if execute_anchor in shortcut:
    shortcut = shortcut.replace(execute_anchor, execute_replacement, 1)
elif "activity.isSpatialFilePickerActive()" not in shortcut:
    raise RuntimeError("exp26 shortcut execute anchor not found")

# ---------------------------------------------------------------------------
# Guards: Bug 1 must remain frozen; only Bug 2 routing changes.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
):
    if required not in panel:
        raise RuntimeError(f"exp26 frozen Bug 1 marker missing: {required}")

for required in (
    "EXP26_META_PICKER_INPUT_MASK",
    "ButtonBits.ButtonA or",
    "EXP26_STANDALONE_PICKER_PANEL",
    "Transform(Pose(Vector3(0f, 1.25f, 1.44f)))",
    "EXP26_PICKER_INPUT_EXCLUSIVE",
    "fun isSpatialFilePickerActive()",
):
    if required not in activity:
        raise RuntimeError(f"exp26 activity requirement missing: {required}")

if "activity.isSpatialFilePickerActive()" not in shortcut:
    raise RuntimeError("exp26 shortcut exclusivity missing")

# Picker must no longer be a child of A in the exp26 creation block.
pos = activity.find("EXP26_STANDALONE_PICKER_PANEL")
end = activity.find("Log.i(TAG, \"exp24 spatial file picker panel opened", pos)
if pos < 0:
    raise RuntimeError("exp26 standalone marker missing")
check = activity[pos:end if end >= 0 else pos + 1000]
if "TransformParent(geoPanel)" in check:
    raise RuntimeError("exp26 picker still parented under A")

activity_path.write_text(activity, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "picker_input=exp26" not in text:
        text += (
            "picker_input=exp26 standalone ActivityPanel + Meta ButtonA/TriggerL/TriggerR mask; "
            "GGQ shortcuts suspended while picker active\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp26 standalone Meta-style picker input routing installed; Bug 1 frozen")
