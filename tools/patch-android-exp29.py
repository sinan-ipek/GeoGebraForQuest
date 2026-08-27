#!/usr/bin/env python3
"""Exp29: freeze Bug 1 and make Exp28's post-result cold handoff deterministic.

Bug 1
-----
Frozen exactly at Exp25+. No popup/login/navigation behavior is modified.

Bug 2
-----
Exp28 improved picker UX by keeping the old GeoGebra window visible while
DocumentsUI was open, but it regressed controller reliability because it started
the new Spatial/OpenXR Activity only 90 ms after killing the stale MAIN process.
The device video shows the old window disappearing around picker return and the
new runtime coming back with hand tracking / missing right controller. Exp27 had
much more teardown time because MAIN died while the user was still browsing.

Exp29 keeps the good Exp28 UX, but makes the post-result handoff deterministic:
1. keep old GeoGebra visible for the whole DocumentsUI browsing period;
2. after picker result, stage the file and kill stale MAIN;
3. poll ActivityManager until the old MAIN process is actually gone (re-killing
   while needed, with a bounded timeout);
4. after confirmed/bounded process exit, wait 1200 ms for OpenXR/Spatial runtime
   resources to settle;
5. only then launch the fresh SpatialGeoGebraActivity.

There is no fixed 90 ms correctness assumption anymore.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp29.py <repo-root>")

root = Path(sys.argv[1]).resolve()
cold_path = root / "app/src/main/java/com/sinan/geogebraforquest/ColdLocalFilePickerActivity.kt"
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"

cold = cold_path.read_text(encoding="utf-8")
panel = panel_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Replace Exp28's fixed 90 ms delay with process-exit polling + XR settle time.
# ---------------------------------------------------------------------------
old_constants = '''        // EXP28_POST_RESULT_COLD_HANDOFF: kill only after DocumentsUI returns.
        private const val COLD_RELAUNCH_DELAY_MS = 90L
'''
new_constants = '''        // EXP29_CONFIRMED_PROCESS_EXIT: never assume that Process.killProcess()
        // has released the Spatial/OpenXR runtime after an arbitrary short delay.
        private const val PROCESS_EXIT_POLL_MS = 50L
        private const val PROCESS_EXIT_MAX_ATTEMPTS = 50
        private const val XR_RELEASE_SETTLE_MS = 1200L
'''
if old_constants in cold:
    cold = cold.replace(old_constants, new_constants, 1)
elif "EXP29_CONFIRMED_PROCESS_EXIT" not in cold:
    raise RuntimeError("exp29 Exp28 delay constants anchor not found")

old_restart = '''    private fun restartFreshMainAfterPickerResult() {
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
new_restart = '''    private fun restartFreshMainAfterPickerResult() {
        if (relaunching) return
        relaunching = true
        killOldMainProcessIfAlive()
        waitForOldMainProcessExit(0)
    }

    // EXP29_CONFIRMED_PROCESS_EXIT: Process.killProcess() is asynchronous from the
    // point of view of the Spatial/OpenXR stack. Do not start the replacement VR
    // Activity until ActivityManager no longer reports the stale MAIN process.
    private fun isOldMainProcessAlive(): Boolean {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager ?: return false
        val selfPid = Process.myPid()
        val mainProcessName = packageName
        return am.runningAppProcesses.orEmpty().any { process ->
            process.pid != selfPid && process.processName == mainProcessName
        }
    }

    private fun waitForOldMainProcessExit(attempt: Int) {
        val stillAlive = isOldMainProcessAlive()
        if (stillAlive && attempt < PROCESS_EXIT_MAX_ATTEMPTS) {
            // Reassert the kill in case the first signal raced Android lifecycle work.
            killOldMainProcessIfAlive()
            Handler(Looper.getMainLooper()).postDelayed(
                { waitForOldMainProcessExit(attempt + 1) },
                PROCESS_EXIT_POLL_MS,
            )
            return
        }

        // Even after the Linux process disappears, give the platform-owned XR
        // session/compositor resources time to detach before constructing VRFeature.
        Handler(Looper.getMainLooper()).postDelayed(
            { relaunchFreshMainAlreadyArmed() },
            XR_RELEASE_SETTLE_MS,
        )
    }

    private fun relaunchFreshMainAlreadyArmed() {
'''
if old_restart in cold:
    cold = cold.replace(old_restart, new_restart, 1)
elif "private fun waitForOldMainProcessExit(attempt: Int)" not in cold:
    raise RuntimeError("exp29 Exp28 restart helper anchor not found")

# Keep Exp28's desirable UX invariant: no kill inside launchPicker().
launch_start = cold.find("    private fun launchPicker() {")
launch_end = cold.find("    private fun killOldMainProcessIfAlive()", launch_start)
if launch_start < 0 or launch_end < 0:
    raise RuntimeError("exp29 launchPicker bounds missing")
launch_block = cold[launch_start:launch_end]
if "killOldMainProcessIfAlive()" in launch_block:
    raise RuntimeError("exp29 would kill MAIN while DocumentsUI is still open")

# ---------------------------------------------------------------------------
# Guards: Bug 1 and Exp27/28 architecture remain frozen.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP27_COLD_PROCESS_PICKER",
    "EXP27_OPEN_COLD_PENDING_FILE",
):
    if required not in panel:
        raise RuntimeError(f"exp29 frozen path missing: {required}")

for required in (
    "EXP27_COLD_PICKER_PROXY",
    "EXP28_KEEP_MAIN_VISIBLE_WHILE_PICKING",
    "EXP28_POST_RESULT_COLD_HANDOFF",
    "EXP29_CONFIRMED_PROCESS_EXIT",
    "PROCESS_EXIT_POLL_MS = 50L",
    "PROCESS_EXIT_MAX_ATTEMPTS = 50",
    "XR_RELEASE_SETTLE_MS = 1200L",
    "isOldMainProcessAlive()",
    "waitForOldMainProcessExit(0)",
    "Process.killProcess(process.pid)",
    "ColdLocalFileBridge.stage(applicationContext, uri)",
    "SpatialGeoGebraActivity::class.java",
    "Intent.FLAG_ACTIVITY_CLEAR_TASK",
):
    if required not in cold:
        raise RuntimeError(f"exp29 cold-picker requirement missing: {required}")

for forbidden in (
    "COLD_RELAUNCH_DELAY_MS",
    "KILL_MAIN_DELAY_MS",
):
    if forbidden in cold:
        raise RuntimeError(f"exp29 fixed-delay residue remains: {forbidden}")

# The new fresh-main launch must only be reachable after the settle timer.
wait_start = cold.find("    private fun waitForOldMainProcessExit(attempt: Int) {")
launch_helper = cold.find("    private fun relaunchFreshMainAlreadyArmed()", wait_start)
if wait_start < 0 or launch_helper < 0:
    raise RuntimeError("exp29 wait/launch helper bounds missing")
wait_block = cold[wait_start:launch_helper]
if "XR_RELEASE_SETTLE_MS" not in wait_block or "relaunchFreshMainAlreadyArmed()" not in wait_block:
    raise RuntimeError("exp29 fresh launch is not gated by XR settle")

cold_path.write_text(cold, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "local_picker_handoff=exp29" not in text:
        text += (
            "local_picker_handoff=exp29 keep GeoGebra visible while browsing; after result "
            "kill stale MAIN, confirm process exit, wait 1200ms XR settle, then cold relaunch\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp29 confirmed process-exit + XR-settle cold handoff installed")
