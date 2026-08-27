#!/usr/bin/env python3
"""Exp21: keep Exp20 cloud/navigation fixes, restore the proven local-file/controller path.

Hypothesis: ACTION_OPEN_DOCUMENT itself is not the regression. v0.9.29 used the
same picker successfully. The regression was introduced by later attempts to
repair XR input by rewriting Controller components and, in exp20, recreating the
Activity after file selection.

Exp21 therefore preserves exp19 login/layout fixes and exp20 MAIN navigation
protection, but removes all local-file XR recovery machinery:
- restore direct WebChromeClient file chooser callback delivery, as in v0.9.29;
- remove staged local.ggb bytes and Activity.recreate();
- remove exp19 controller recovery windows and lifecycle rebind calls;
- stop writing laserEnabled/Controller components; controller state is read only.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp21.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
controller_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
controller = controller_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# GeoGebraWebPanel: undo only Exp20's staged local-file restart. Keep Exp20's
# MAIN navigation guard / remote escape fallback untouched.
# ---------------------------------------------------------------------------
panel = panel.replace("import java.io.ByteArrayInputStream\n", "", 1)
panel = panel.replace(
    'private const val PENDING_LOCAL_GGB_URL =\n    "https://appassets.androidplatform.net/pending/local.ggb"\n',
    "",
    1,
)

start = panel.find("// EXP20_PENDING_LOCAL_FILE:")
end = panel.find("object GeoGebraLocalFilePicker {", start)
if start >= 0 and end >= 0:
    panel = panel[:start] + panel[end:]

# Restore the exact v0.9.29-style callback path: selected content Uri goes back
# to WebView/GeoGebra directly; no Activity recreation and no byte staging.
start = panel.find("    // EXP20_CANONICAL_FILE_RESTART:")
if start < 0:
    start = panel.find("    fun handleActivityResult(\n")
end = panel.find("    fun cancelPending()", start)
if start < 0 or end < 0:
    raise RuntimeError("exp21 local file result block not found")

proven_result = r'''    // EXP21_PROVEN_LOCAL_FILE_PATH: identical continuation model to v0.9.29.
    fun handleActivityResult(
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ): Boolean {
        if (requestCode != REQUEST_CODE) return false

        val callback = pendingCallback
        pendingCallback = null
        if (callback == null) return true

        if (resultCode != Activity.RESULT_OK || data == null) {
            callback.onReceiveValue(null)
            return true
        }

        val clipData = data.clipData
        val result = when {
            clipData != null && clipData.itemCount > 0 ->
                Array(clipData.itemCount) { index -> clipData.getItemAt(index).uri }
            data.data != null -> arrayOf(data.data!!)
            else -> null
        }

        callback.onReceiveValue(result)
        return true
    }

'''
panel = panel[:start] + proven_result + panel[end:]

# Remove Exp20's delayed private-file loader helper.
start = panel.find("    // EXP20_OPEN_STAGED_LOCAL_FILE:")
if start >= 0:
    end = panel.find("    fun handleBack(): Boolean {", start)
    if end < 0:
        raise RuntimeError("exp21 staged loader end anchor not found")
    panel = panel[:start] + panel[end:]

panel = panel.replace(
    "                    GeoGebraWebNavigation.openPendingLocalFileIfAny()\n",
    "",
)
panel = panel.replace(
    '        .addPathHandler("/pending/", PendingLocalFilePathHandler())\n',
    "",
)

# ---------------------------------------------------------------------------
# Spatial Activity: remove exp19 recovery lifecycle and exp20 recreation callback.
# Keep exp19 native stereo-layout rearm and all embedded stereo behavior.
# ---------------------------------------------------------------------------
activity = activity.replace(
    "\n    // EXP19_CONTROLLER_RECOVERY_SYSTEM\n    private lateinit var controllerShortcutSystem: QuestControllerShortcutSystem\n",
    "",
    1,
)
activity = activity.replace(
    "        controllerShortcutSystem = QuestControllerShortcutSystem(this)\n"
    "        systemManager.registerSystem(controllerShortcutSystem)\n",
    "        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n",
    1,
)

start = activity.find("    // EXP19_SPATIAL_INPUT_RECOVERY:")
if start >= 0:
    end = activity.find('    @Suppress("DEPRECATION")\n    override fun onBackPressed()', start)
    if end < 0:
        raise RuntimeError("exp21 exp19 lifecycle recovery end anchor not found")
    activity = activity[:start] + activity[end:]

activity = activity.replace(
    "        recoverSpatialInputAfterExternalActivity()\n        if (vrReady) return\n",
    "        if (vrReady) return\n",
    1,
)
activity = activity.replace(
    "        if (GeoGebraLocalFilePicker.handleActivityResult(this, requestCode, resultCode, data)) {\n"
    "            return\n"
    "        }\n",
    "        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {\n"
    "            return\n"
    "        }\n",
    1,
)

# ---------------------------------------------------------------------------
# Controller system: remove every exp19 recovery write and the older explicit
# laser write. Return to read-only controller handling while preserving Grip/A/B.
# ---------------------------------------------------------------------------
start = controller.find("    // EXP19_INPUT_RECOVERY_WINDOW:")
if start >= 0:
    end = controller.find("    override fun execute() {", start)
    if end < 0:
        raise RuntimeError("exp21 controller recovery field end anchor not found")
    controller = controller[:start] + controller[end:]

# Remove querycompat/recovery prelude, regardless of exact whitespace generated.
old_prelude = '''        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        val forceInputRecovery = inputRecoveryFrames > 0
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
new_prelude = '''        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }

        for (entity in controllers) {
'''
if old_prelude in controller:
    controller = controller.replace(old_prelude, new_prelude, 1)
else:
    # Fallback for a pre-querycompat shape.
    old_prelude2 = '''        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        val forceInputRecovery = inputRecoveryFrames > 0

        for (entity in controllers) {
'''
    if old_prelude2 in controller:
        controller = controller.replace(old_prelude2, new_prelude, 1)

laser_block = '''            // EXP12_VISIBLE_RAY remains frozen: the native beam always reaches A.
            if (forceInputRecovery || !controller.laserEnabled) {
                controller.laserEnabled = true
                entity.setComponent(controller)
            }

'''
controller = controller.replace(laser_block, "", 1)
laser_block2 = '''            // EXP12_VISIBLE_RAY remains frozen: the native beam always reaches A.
            if (!controller.laserEnabled) {
                controller.laserEnabled = true
                entity.setComponent(controller)
            }

'''
controller = controller.replace(laser_block2, "", 1)

# ---------------------------------------------------------------------------
# Guards: cloud/navigation fixes must remain, local-file/controller recovery must not.
# ---------------------------------------------------------------------------
for required in (
    "EXP21_PROVEN_LOCAL_FILE_PATH",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP20_REMOTE_ESCAPE_FALLBACK",
    "EXP19_POPUP_SESSION_EDGE",
    "EXP15_LOCAL_LOGIN_TOKEN_BRIDGE",
    "EXP17_OPENFROMGGT_HANDOFF",
):
    if required not in panel:
        raise RuntimeError(f"exp21 required panel behavior missing: {required}")

for forbidden in (
    "EXP20_PENDING_LOCAL_FILE",
    "EXP20_CANONICAL_FILE_RESTART",
    "activity.recreate()",
    "EXP20_OPEN_STAGED_LOCAL_FILE",
    "PENDING_LOCAL_GGB_URL",
    "PendingLocalFilePathHandler",
    "openPendingLocalFileIfAny",
    'addPathHandler("/pending/"',
):
    if forbidden in panel:
        raise RuntimeError(f"exp21 staged local-file residue remains: {forbidden}")

for forbidden in (
    "EXP19_SPATIAL_INPUT_RECOVERY",
    "recoverSpatialInputAfterExternalActivity",
    "controllerShortcutSystem.requestInputRecovery",
    "GeoGebraLocalFilePicker.handleActivityResult(this, requestCode",
):
    if forbidden in activity:
        raise RuntimeError(f"exp21 Activity recovery residue remains: {forbidden}")

for forbidden in (
    "EXP19_INPUT_RECOVERY_WINDOW",
    "inputRecoveryFrames",
    "forceInputRecovery",
    "recoveryFrameConsumed",
    "controller.laserEnabled = true",
    "entity.setComponent(controller)",
):
    if forbidden in controller:
        raise RuntimeError(f"exp21 controller-write residue remains: {forbidden}")

# Preserve the real controller features we still need.
for required in (
    "rightGripRotateActive",
    "ButtonBits.ButtonSqueezeR",
    "ButtonBits.ButtonA",
    "ButtonBits.ButtonB",
):
    if required not in controller:
        raise RuntimeError(f"exp21 controller feature missing: {required}")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
controller_path.write_text(controller, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "local_file_path=exp21" not in text:
        text += (
            "local_file_path=exp21 proven v0.9.29 direct WebView file callback; "
            "no Activity recreation; no controller component recovery writes\n"
        )
        meta.write_text(text, encoding="utf-8")

print("[GGQ] exp21 proven local-file path restored; cloud/navigation guards preserved")
