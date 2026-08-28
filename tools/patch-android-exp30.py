#!/usr/bin/env python3
"""Exp30: graceful XR handoff + GeoGebra session restore after local files.

Bug 1
-----
Frozen exactly at Exp25+. No popup whitelist/navigation rules are changed.

Bug 2 / UX
-----------
Exp29 proved that a genuinely torn-down XR runtime can recover controller input,
but Process.killProcess() creates a visible/audible app-close transition. Exp30
tries a graceful path first:

1. DocumentsUI remains in the separate :localpicker process and old GeoGebra stays
   visible while browsing, exactly as Exp28/29.
2. After a file result, :localpicker broadcasts a private graceful-shutdown request
   to the old SpatialGeoGebraActivity.
3. MAIN captures the current GeoGebra SSID for the coming cold handoff, calls
   finish(), and only after AppSystemActivity.onDestroy() returns writes an
   app-private XR-shutdown-complete marker.
4. :localpicker waits for that marker, then keeps the proven 1200 ms XR settle
   interval before launching the replacement SpatialGeoGebraActivity.
5. If graceful shutdown never completes, Exp29's process-kill path remains as a
   bounded safety fallback; controller reliability is therefore not sacrificed.

Session continuity
------------------
The old MAIN's GeoGebra login state lives partly in local AppW memory. Before the
controlled restart, Exp30 reads the still-valid GeoGebra SSID cookie and stores it
in app-private storage. The replacement local AppW replays that token through the
already-proven Exp22 READY/SUCCESS handshake before/while opening the staged .ggb.
A user who was signed in should therefore remain signed in after local-file load.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp30.py <repo-root>")

root = Path(sys.argv[1]).resolve()
cold_path = root / "app/src/main/java/com/sinan/geogebraforquest/ColdLocalFilePickerActivity.kt"
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"

cold = cold_path.read_text(encoding="utf-8")
panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Shared cross-process bridge: graceful XR shutdown marker + session token.
# ---------------------------------------------------------------------------
bridge_anchor = '''    private const val READY_NAME = "ready"\n'''
bridge_insert = bridge_anchor + '''    private const val SESSION_TOKEN_NAME = "session_token"\n    private const val XR_SHUTDOWN_READY_NAME = "xr_shutdown_ready"\n'''
if "SESSION_TOKEN_NAME" not in cold:
    if bridge_anchor not in cold:
        raise RuntimeError("exp30 ColdLocalFileBridge constant anchor missing")
    cold = cold.replace(bridge_anchor, bridge_insert, 1)

file_anchor = '''    private fun readyFile(context: Context): File = File(dir(context), READY_NAME)\n'''
file_insert = file_anchor + '''    private fun sessionTokenFile(context: Context): File = File(dir(context), SESSION_TOKEN_NAME)\n    private fun xrShutdownReadyFile(context: Context): File = File(dir(context), XR_SHUTDOWN_READY_NAME)\n'''
if "sessionTokenFile(context" not in cold:
    if file_anchor not in cold:
        raise RuntimeError("exp30 ColdLocalFileBridge file anchor missing")
    cold = cold.replace(file_anchor, file_insert, 1)

method_anchor = '''    fun clearReady(context: Context) {\n        try { readyFile(context).delete() } catch (_: Throwable) {}\n    }\n'''
method_insert = method_anchor + r'''

    // EXP30_CROSS_PROCESS_HANDOFF_STATE
    fun saveSessionToken(context: Context, token: String?) {
        val file = sessionTokenFile(context)
        if (token.isNullOrBlank()) {
            try { file.delete() } catch (_: Throwable) {}
            return
        }
        try {
            file.writeText(token)
        } catch (_: Throwable) {}
    }

    fun readSessionToken(context: Context): String? = try {
        sessionTokenFile(context).takeIf { it.isFile }
            ?.readText()
            ?.trim()
            ?.takeIf { it.isNotBlank() }
    } catch (_: Throwable) {
        null
    }

    fun clearXrShutdownReady(context: Context) {
        try { xrShutdownReadyFile(context).delete() } catch (_: Throwable) {}
    }

    fun markXrShutdownReady(context: Context) {
        try { xrShutdownReadyFile(context).writeText("ready") } catch (_: Throwable) {}
    }

    fun isXrShutdownReady(context: Context): Boolean =
        try { xrShutdownReadyFile(context).isFile } catch (_: Throwable) { false }
'''
if "EXP30_CROSS_PROCESS_HANDOFF_STATE" not in cold:
    if method_anchor not in cold:
        raise RuntimeError("exp30 ColdLocalFileBridge method anchor missing")
    cold = cold.replace(method_anchor, method_insert, 1)

# ---------------------------------------------------------------------------
# MAIN session capture/restore. Reuse the exact Exp22 deliverLoginToken handshake.
# ---------------------------------------------------------------------------
nav_anchor = '''    fun handleBack(): Boolean {\n'''
nav_helpers = r'''    // EXP30_COLD_SESSION_RESTORE: capture GeoGebra's remote SSID before
    // destroying the old local AppW, then replay it into the replacement AppW.
    private var coldSessionRestoreToken: String? = null

    fun captureSessionForColdRestart(context: Context) {
        val main = mainWebView.get()
        val token = if (main != null) popupGeoGebraSessionToken(main) else null
        ColdLocalFileBridge.saveSessionToken(context.applicationContext, token)
    }

    private fun restoreSessionForColdRestartIfAny(context: Context) {
        if (!ColdLocalFileBridge.hasPending(context)) return
        val token = ColdLocalFileBridge.readSessionToken(context) ?: return
        if (coldSessionRestoreToken == token) return
        coldSessionRestoreToken = token
        if (!deliverLoginToken(token)) {
            coldSessionRestoreToken = null
        }
    }

''' + nav_anchor
if "EXP30_COLD_SESSION_RESTORE" not in panel:
    if nav_anchor not in panel:
        raise RuntimeError("exp30 GeoGebraWebNavigation handleBack anchor missing")
    panel = panel.replace(nav_anchor, nav_helpers, 1)

open_anchor = '''        val context = main.context.applicationContext\n        if (!ColdLocalFileBridge.hasPending(context) || coldLocalOpenInFlight) return\n'''
open_replacement = '''        val context = main.context.applicationContext\n        if (!ColdLocalFileBridge.hasPending(context) || coldLocalOpenInFlight) return\n        restoreSessionForColdRestartIfAny(context)\n'''
if "restoreSessionForColdRestartIfAny(context)" not in panel:
    if open_anchor not in panel:
        raise RuntimeError("exp30 pending cold file context anchor missing")
    panel = panel.replace(open_anchor, open_replacement, 1)

# ---------------------------------------------------------------------------
# Spatial Activity: private graceful-shutdown receiver and onDestroy ACK marker.
# ---------------------------------------------------------------------------
for imp in (
    "import android.content.BroadcastReceiver\n",
    "import android.content.Context\n",
    "import android.content.IntentFilter\n",
):
    if imp not in activity:
        activity = activity.replace("import android.content.Intent\n", "import android.content.Intent\n" + imp, 1)

companion_anchor = '''        private const val REQUEST_USE_SCENE = 701\n'''
companion_insert = companion_anchor + '''        const val ACTION_GRACEFUL_COLD_RESTART =\n            "com.sinan.geogebraforquest.action.GRACEFUL_COLD_RESTART"\n'''
if "ACTION_GRACEFUL_COLD_RESTART" not in activity:
    if companion_anchor not in activity:
        raise RuntimeError("exp30 Activity companion anchor missing")
    activity = activity.replace(companion_anchor, companion_insert, 1)

field_anchor = '''    private var startupSplashActive = true\n'''
field_insert = field_anchor + r'''

    // EXP30_GRACEFUL_XR_SHUTDOWN
    private var gracefulColdRestartRequested = false
    private var coldRestartReceiverRegistered = false
    private val coldRestartReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != ACTION_GRACEFUL_COLD_RESTART) return
            if (gracefulColdRestartRequested) return
            gracefulColdRestartRequested = true

            // Capture the authenticated GeoGebra session while the old WebView and
            // CookieManager state are still alive, before AppSystemActivity teardown.
            GeoGebraWebNavigation.captureSessionForColdRestart(applicationContext)
            ColdLocalFileBridge.clearXrShutdownReady(applicationContext)

            // finish(), not Process.killProcess(): AppSystemActivity/VRFeature gets
            // its normal destruction path. Picker is a separate process and stays up.
            window.decorView.post {
                try { finish() } catch (_: Throwable) {}
            }
        }
    }
'''
if "EXP30_GRACEFUL_XR_SHUTDOWN" not in activity:
    if field_anchor not in activity:
        raise RuntimeError("exp30 Activity startupSplash anchor missing")
    activity = activity.replace(field_anchor, field_insert, 1)

create_anchor = '''    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n'''
create_insert = '''    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n        ColdLocalFileBridge.clearXrShutdownReady(applicationContext)\n        registerReceiver(\n            coldRestartReceiver,\n            IntentFilter(ACTION_GRACEFUL_COLD_RESTART),\n            Context.RECEIVER_NOT_EXPORTED,\n        )\n        coldRestartReceiverRegistered = true\n'''
if "coldRestartReceiverRegistered = true" not in activity:
    if create_anchor not in activity:
        raise RuntimeError("exp30 Activity onCreate anchor missing")
    activity = activity.replace(create_anchor, create_insert, 1)

# Mark shutdown complete only after the parent AppSystemActivity has finished its
# destruction. This is the signal consumed by :localpicker.
destroy_anchor = '''        embeddedStereoVisible = false\n\n        super.onDestroy()\n    }\n}'''
destroy_replacement = '''        embeddedStereoVisible = false\n\n        if (coldRestartReceiverRegistered) {\n            try { unregisterReceiver(coldRestartReceiver) } catch (_: Throwable) {}\n            coldRestartReceiverRegistered = false\n        }\n\n        super.onDestroy()\n\n        if (gracefulColdRestartRequested) {\n            ColdLocalFileBridge.markXrShutdownReady(applicationContext)\n        }\n    }\n}'''
if "ColdLocalFileBridge.markXrShutdownReady" not in activity:
    if destroy_anchor not in activity:
        raise RuntimeError("exp30 Activity onDestroy tail anchor missing")
    activity = activity.replace(destroy_anchor, destroy_replacement, 1)

# ---------------------------------------------------------------------------
# Picker: graceful first; Exp29 process kill only as a bounded fallback.
# ---------------------------------------------------------------------------
constant_anchor = '''        private const val XR_RELEASE_SETTLE_MS = 1200L\n'''
constant_insert = constant_anchor + '''        private const val GRACEFUL_SHUTDOWN_POLL_MS = 50L\n        private const val GRACEFUL_SHUTDOWN_MAX_ATTEMPTS = 50\n'''
if "GRACEFUL_SHUTDOWN_POLL_MS" not in cold:
    if constant_anchor not in cold:
        raise RuntimeError("exp30 Exp29 XR settle constant anchor missing")
    cold = cold.replace(constant_anchor, constant_insert, 1)

old_restart = '''    private fun restartFreshMainAfterPickerResult() {\n        if (relaunching) return\n        relaunching = true\n        killOldMainProcessIfAlive()\n        waitForOldMainProcessExit(0)\n    }\n\n    // EXP29_CONFIRMED_PROCESS_EXIT: Process.killProcess() is asynchronous from the\n'''
new_restart = '''    private fun restartFreshMainAfterPickerResult() {\n        if (relaunching) return\n        relaunching = true\n\n        // EXP30_GRACEFUL_FIRST_XR_HANDOFF: request normal AppSystemActivity teardown.\n        // Process.killProcess() remains below only as a timeout fallback.\n        ColdLocalFileBridge.clearXrShutdownReady(applicationContext)\n        try {\n            sendBroadcast(\n                Intent(SpatialGeoGebraActivity.ACTION_GRACEFUL_COLD_RESTART)\n                    .setPackage(packageName),\n            )\n        } catch (_: Throwable) {}\n        waitForGracefulXrShutdown(0)\n    }\n\n    private fun waitForGracefulXrShutdown(attempt: Int) {\n        if (ColdLocalFileBridge.isXrShutdownReady(applicationContext)) {\n            Handler(Looper.getMainLooper()).postDelayed(\n                { relaunchFreshMainAlreadyArmed() },\n                XR_RELEASE_SETTLE_MS,\n            )\n            return\n        }\n\n        if (attempt < GRACEFUL_SHUTDOWN_MAX_ATTEMPTS) {\n            Handler(Looper.getMainLooper()).postDelayed(\n                { waitForGracefulXrShutdown(attempt + 1) },\n                GRACEFUL_SHUTDOWN_POLL_MS,\n            )\n            return\n        }\n\n        // Safety fallback: if the Activity did not acknowledge normal teardown,\n        // preserve Exp29's proven controller-recovery architecture.\n        killOldMainProcessIfAlive()\n        waitForOldMainProcessExit(0)\n    }\n\n    // EXP29_CONFIRMED_PROCESS_EXIT: Process.killProcess() is asynchronous from the\n'''
if "EXP30_GRACEFUL_FIRST_XR_HANDOFF" not in cold:
    if old_restart not in cold:
        raise RuntimeError("exp30 Exp29 restart anchor missing")
    cold = cold.replace(old_restart, new_restart, 1)

# Clear stale marker at picker launch as well, before DocumentsUI browsing begins.
launch_anchor = '''    private fun launchPicker() {\n        ColdLocalFileBridge.clearReady(applicationContext)\n'''
launch_replacement = '''    private fun launchPicker() {\n        ColdLocalFileBridge.clearReady(applicationContext)\n        ColdLocalFileBridge.clearXrShutdownReady(applicationContext)\n'''
if launch_anchor in cold and "clearXrShutdownReady(applicationContext)\n        val intent" not in cold:
    cold = cold.replace(launch_anchor, launch_replacement, 1)

# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP27_COLD_PROCESS_PICKER",
    "EXP27_OPEN_COLD_PENDING_FILE",
    "EXP30_COLD_SESSION_RESTORE",
    "captureSessionForColdRestart",
    "restoreSessionForColdRestartIfAny",
    "deliverLoginToken(token)",
):
    if required not in panel:
        raise RuntimeError(f"exp30 panel requirement missing: {required}")

for required in (
    "EXP30_GRACEFUL_XR_SHUTDOWN",
    "ACTION_GRACEFUL_COLD_RESTART",
    "BroadcastReceiver",
    "Context.RECEIVER_NOT_EXPORTED",
    "GeoGebraWebNavigation.captureSessionForColdRestart",
    "finish()",
    "ColdLocalFileBridge.markXrShutdownReady",
):
    if required not in activity:
        raise RuntimeError(f"exp30 Activity requirement missing: {required}")

for required in (
    "EXP30_CROSS_PROCESS_HANDOFF_STATE",
    "EXP30_GRACEFUL_FIRST_XR_HANDOFF",
    "saveSessionToken",
    "readSessionToken",
    "markXrShutdownReady",
    "isXrShutdownReady",
    "GRACEFUL_SHUTDOWN_POLL_MS = 50L",
    "GRACEFUL_SHUTDOWN_MAX_ATTEMPTS = 50",
    "sendBroadcast(",
    "waitForGracefulXrShutdown(0)",
    "XR_RELEASE_SETTLE_MS = 1200L",
    "killOldMainProcessIfAlive()",
    "waitForOldMainProcessExit(0)",
):
    if required not in cold:
        raise RuntimeError(f"exp30 cold-picker requirement missing: {required}")

# Normal restart entry must not immediately kill MAIN anymore.
restart_start = cold.find("    private fun restartFreshMainAfterPickerResult() {")
restart_end = cold.find("    private fun waitForGracefulXrShutdown", restart_start)
if restart_start < 0 or restart_end < 0:
    raise RuntimeError("exp30 graceful restart bounds missing")
restart_block = cold[restart_start:restart_end]
if "killOldMainProcessIfAlive()" in restart_block:
    raise RuntimeError("exp30 normal restart path still kills MAIN immediately")

# The kill must remain only in graceful-timeout / Exp29 fallback paths.
if cold.count("killOldMainProcessIfAlive()") < 2:
    raise RuntimeError("exp30 lost Exp29 safety fallback")

cold_path.write_text(cold, encoding="utf-8")
panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "local_picker_handoff=exp30" not in text:
        text += (
            "local_picker_handoff=exp30 graceful AppSystemActivity finish/onDestroy ACK first; "
            "Exp29 process-kill only timeout fallback; 1200ms XR settle preserved\n"
        )
    if "cold_session_restore=exp30" not in text:
        text += (
            "cold_session_restore=exp30 capture SSID before graceful XR teardown and replay via "
            "Exp22 READY/SUCCESS handshake in replacement local AppW\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp30 graceful XR handoff + cold GeoGebra session restore installed")
