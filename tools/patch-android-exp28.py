#!/usr/bin/env python3
"""Exp28: freeze Bug 1 and keep the GeoGebra window visible while DocumentsUI is open.

Bug 1
-----
Frozen exactly at Exp25/26/27. No popup/login/navigation behavior is modified.

Bug 2 / UX
-----------
Exp27 solved most of Bug 2 by moving SAF into a separate :localpicker process and
cold-starting a fresh Spatial/OpenXR runtime after selection. However, Exp27 also
scheduled killOldMainProcessIfAlive() only 300 ms after DocumentsUI opened. That
made the GeoGebra spatial window disappear for the entire time the user browsed
files.

Exp28 preserves the cold-process isolation but changes *when* the old immersive
process is killed:

1. Launch DocumentsUI from :localpicker.
2. Keep the old MAIN/GeoGebra process alive and visible behind DocumentsUI for the
   whole browse/selection period.
3. When DocumentsUI returns to the picker proxy, stage the selected .ggb (or clear
   the marker on cancel) while the old MAIN is still alive.
4. Only then kill the old MAIN process, while the picker proxy is still the top
   Activity, so the stale Spatial/OpenXR Activity can never resume.
5. After a short bounded 90 ms handoff delay, launch a brand-new
   SpatialGeoGebraActivity task/process.

This retains Exp27's clean XR-session guarantee while removing the long blank gap
from the user experience.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp28.py <repo-root>")

root = Path(sys.argv[1]).resolve()
cold_path = root / "app/src/main/java/com/sinan/geogebraforquest/ColdLocalFilePickerActivity.kt"
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"

cold = cold_path.read_text(encoding="utf-8")
panel = panel_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Remove Exp27's early timed process kill. The old GeoGebra process must remain
# alive for the entire DocumentsUI browsing period.
# ---------------------------------------------------------------------------
cold = cold.replace(
    "        private const val KILL_MAIN_DELAY_MS = 300L\n",
    "        // EXP28_POST_RESULT_COLD_HANDOFF: kill only after DocumentsUI returns.\n"
    "        private const val COLD_RELAUNCH_DELAY_MS = 90L\n",
    1,
)

early_kill = '''            @Suppress("DEPRECATION")
            startActivityForResult(intent, REQUEST_OPEN_GGB)
            Handler(Looper.getMainLooper()).postDelayed(
                { killOldMainProcessIfAlive() },
                KILL_MAIN_DELAY_MS,
            )
'''
no_early_kill = '''            @Suppress("DEPRECATION")
            startActivityForResult(intent, REQUEST_OPEN_GGB)
            // EXP28_KEEP_MAIN_VISIBLE_WHILE_PICKING: do not kill MAIN here.
            // DocumentsUI now floats over the still-live GeoGebra spatial window.
'''
if early_kill in cold:
    cold = cold.replace(early_kill, no_early_kill, 1)
elif "EXP28_KEEP_MAIN_VISIBLE_WHILE_PICKING" not in cold:
    raise RuntimeError("exp28 could not remove Exp27 early main-process kill")

# If picker launch itself fails, there is no external-activity boundary. Simply
# return to the existing MAIN rather than killing/restarting it.
old_catch = '''        } catch (_: Throwable) {
            relaunchFreshMain()
        }
    }
'''
new_catch = '''        } catch (_: Throwable) {
            finish()
        }
    }
'''
if old_catch in cold:
    cold = cold.replace(old_catch, new_catch, 1)

# ---------------------------------------------------------------------------
# On real picker return, stage/clear first, then kill stale MAIN while this proxy
# still owns the foreground, then launch a fresh Spatial runtime.
# ---------------------------------------------------------------------------
old_result_tail = '''        } else {
            ColdLocalFileBridge.clearReady(applicationContext)
        }

        relaunchFreshMain()
    }

    private fun relaunchFreshMain() {
'''
new_result_tail = '''        } else {
            ColdLocalFileBridge.clearReady(applicationContext)
        }

        // EXP28_POST_RESULT_COLD_HANDOFF: DocumentsUI has returned to this proxy,
        // so MAIN is still covered. Destroy the stale XR process now — never while
        // the user is browsing, and never after this proxy has finished.
        restartFreshMainAfterPickerResult()
    }

    private fun restartFreshMainAfterPickerResult() {
        if (relaunching) return
        relaunching = true
        killOldMainProcessIfAlive()
        Handler(Looper.getMainLooper()).postDelayed(
            { relaunchFreshMainAlreadyArmed() },
            COLD_RELAUNCH_DELAY_MS,
        )
    }

    private fun relaunchFreshMainAlreadyArmed() {
'''
if old_result_tail in cold:
    cold = cold.replace(old_result_tail, new_result_tail, 1)
elif "EXP28_POST_RESULT_COLD_HANDOFF" not in cold:
    raise RuntimeError("exp28 picker result handoff anchor not found")

# Exp27's relaunchFreshMain() starts with the reentrancy guard. Exp28 already arms
# relaunching before the delay, so remove that second guard from the renamed helper.
old_helper_head = '''    private fun relaunchFreshMainAlreadyArmed() {
        if (relaunching) return
        relaunching = true
        val intent = Intent(this, SpatialGeoGebraActivity::class.java).apply {
'''
new_helper_head = '''    private fun relaunchFreshMainAlreadyArmed() {
        val intent = Intent(this, SpatialGeoGebraActivity::class.java).apply {
'''
if old_helper_head in cold:
    cold = cold.replace(old_helper_head, new_helper_head, 1)
elif "private fun relaunchFreshMainAlreadyArmed()" not in cold:
    raise RuntimeError("exp28 fresh-main helper rename failed")

# Update the class comment so generated source documents the actual runtime rule.
cold = cold.replace(
    " * kills the stale main process after the picker is visible, stages the selected\n"
    " * .ggb, then launches a completely fresh SpatialGeoGebraActivity.\n",
    " * keeps the old GeoGebra process visible while DocumentsUI is open, then after\n"
    " * picker result stages the .ggb, kills stale MAIN, and launches a fresh Spatial runtime.\n",
    1,
)

# ---------------------------------------------------------------------------
# Guards. Bug 1 is frozen and Exp27's clean-process architecture must remain.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP27_COLD_PROCESS_PICKER",
    "EXP27_OPEN_COLD_PENDING_FILE",
):
    if required not in panel:
        raise RuntimeError(f"exp28 frozen path missing: {required}")

for required in (
    "EXP27_COLD_PICKER_PROXY",
    "EXP28_KEEP_MAIN_VISIBLE_WHILE_PICKING",
    "EXP28_POST_RESULT_COLD_HANDOFF",
    "COLD_RELAUNCH_DELAY_MS = 90L",
    "restartFreshMainAfterPickerResult()",
    "killOldMainProcessIfAlive()",
    "Process.killProcess(process.pid)",
    "ColdLocalFileBridge.stage(applicationContext, uri)",
    "SpatialGeoGebraActivity::class.java",
    "Intent.FLAG_ACTIVITY_CLEAR_TASK",
):
    if required not in cold:
        raise RuntimeError(f"exp28 cold-picker requirement missing: {required}")

for forbidden in (
    "KILL_MAIN_DELAY_MS",
    "{ killOldMainProcessIfAlive() },\n                KILL_MAIN_DELAY_MS",
    "private fun relaunchFreshMain()",
):
    if forbidden in cold:
        raise RuntimeError(f"exp28 early-kill/relaunch residue remains: {forbidden}")

# There must be no kill scheduled inside launchPicker().
launch_start = cold.find("    private fun launchPicker() {")
launch_end = cold.find("    private fun killOldMainProcessIfAlive()", launch_start)
if launch_start < 0 or launch_end < 0:
    raise RuntimeError("exp28 launchPicker bounds missing")
launch_block = cold[launch_start:launch_end]
if "killOldMainProcessIfAlive()" in launch_block:
    raise RuntimeError("exp28 still kills MAIN while DocumentsUI is open")

# Result flow must stage before the kill call.
result_start = cold.find("    override fun onActivityResult(")
restart_start = cold.find("    private fun restartFreshMainAfterPickerResult()", result_start)
if result_start < 0 or restart_start < 0:
    raise RuntimeError("exp28 result/restart blocks missing")
result_block = cold[result_start:restart_start]
if "ColdLocalFileBridge.stage(applicationContext, uri)" not in result_block:
    raise RuntimeError("exp28 result no longer stages selected GGB")
if "restartFreshMainAfterPickerResult()" not in result_block:
    raise RuntimeError("exp28 result does not enter cold handoff")

cold_path.write_text(cold, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "local_picker_ux=exp28" not in text:
        text += (
            "local_picker_ux=exp28 keep old GeoGebra visible throughout DocumentsUI; "
            "kill stale MAIN only after picker result, then 90ms cold relaunch\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp28 post-result cold handoff installed; GeoGebra remains visible while picking")
