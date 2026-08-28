#!/usr/bin/env python3
"""Exp31: return to Exp27 exactly, adding only one-shot login continuity.

Base
----
This patch is designed to run directly after Exp27. Exp28, Exp29 and Exp30 MUST
NOT be applied before it. Therefore the proven Exp27 local-file/XR behavior stays
byte-for-byte intact:

- :localpicker process
- ACTION_OPEN_DOCUMENT
- MAIN is killed 300 ms after DocumentsUI opens
- selected .ggb is staged privately
- a brand-new SpatialGeoGebraActivity is launched

Bug 1
-----
Frozen at Exp25. No popup whitelist/navigation rule is changed.

Only change: session continuity
-------------------------------
Immediately before Exp27 launches :localpicker, MAIN snapshots the current remote
GeoGebra SSID cookie into an app-private one-shot file. On the fresh local MAIN,
a normal local-page completion probes that one-shot token and hands it through
Exp22's already-proven READY/SUCCESS login bridge. The one-shot token is consumed
as soon as delivery is armed, so an invalid/stale token can never keep retrying or
interfere with a later explicit Sign in.

If the user is actually signed out (no SSID cookie), the one-shot file is cleared
and no automatic login is attempted.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp31.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
cold_path = root / "app/src/main/java/com/sinan/geogebraforquest/ColdLocalFilePickerActivity.kt"

panel = panel_path.read_text(encoding="utf-8")
cold = cold_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1) Read the current remote GeoGebra SSID from CookieManager in MAIN.
# This is intentionally a new passive helper; popup/login routing is untouched.
# ---------------------------------------------------------------------------
if "EXP31_CURRENT_REMOTE_SESSION" not in panel:
    anchor = "private fun popupGeoGebraSessionToken(view: WebView): String? {\n"
    helper = r'''// EXP31_CURRENT_REMOTE_SESSION: passive snapshot used only when the user
// explicitly enters Exp27's local-file cold-restart path.
private fun currentGeoGebraSessionToken(): String? {
    val cookies = CookieManager.getInstance()
    val candidates = listOf(
        "https://www.geogebra.org/",
        "https://geogebra.org/",
        "https://accounts.geogebra.org/",
    )
    for (url in candidates) {
        cookieValue(cookies.getCookie(url), "SSID")?.let { return it }
    }
    return null
}

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp31 could not locate popup session helper anchor")
    panel = panel.replace(anchor, helper, 1)

# ---------------------------------------------------------------------------
# 2) Snapshot session exactly at Exp27 local-file launch. No other navigation or
# login entry point is touched. A blank/missing cookie clears any stale snapshot.
# ---------------------------------------------------------------------------
if "EXP31_SNAPSHOT_SESSION_BEFORE_COLD_PICKER" not in panel:
    old = '''                pendingCallback = null
                callback.onReceiveValue(null)
                activity.startActivity(
                    Intent(activity, ColdLocalFilePickerActivity::class.java),
                )
'''
    new = '''                pendingCallback = null
                callback.onReceiveValue(null)
                // EXP31_SNAPSHOT_SESSION_BEFORE_COLD_PICKER: preserve only the
                // current authenticated SSID for the imminent Exp27 cold restart.
                ColdLocalFileBridge.prepareSessionRestore(
                    activity.applicationContext,
                    currentGeoGebraSessionToken(),
                )
                activity.startActivity(
                    Intent(activity, ColdLocalFilePickerActivity::class.java),
                )
'''
    if old not in panel:
        raise RuntimeError("exp31 could not locate Exp27 cold-picker launch")
    panel = panel.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 3) Fresh MAIN: one-shot delivery through Exp22's proven deliverLoginToken().
# Consume immediately after delivery is armed. Exp22 itself waits until
# __ggqLoginReady and then waits for __ggqLoginSuccessToken.
# ---------------------------------------------------------------------------
if "EXP31_RESTORE_COLD_SESSION_ONCE" not in panel:
    anchor = '''    // EXP27_OPEN_COLD_PENDING_FILE: only the fresh local MAIN consumes the
'''
    helper = r'''    // EXP31_RESTORE_COLD_SESSION_ONCE: cold restart restoration is isolated
    // from normal Sign in. An invalid token gets one attempt only and can never
    // shadow a later explicit login.
    private var coldSessionRestoreArmed = false

    fun restoreColdSessionIfAny() {
        if (coldSessionRestoreArmed) return
        val main = mainWebView.get() ?: return
        val context = main.context.applicationContext
        val token = ColdLocalFileBridge.pendingSessionToken(context) ?: return

        coldSessionRestoreArmed = true
        if (deliverLoginToken(token)) {
            // deliverLoginToken contains Exp22's READY/SUCCESS polling, so the
            // persistent handoff is no longer needed once that JS job is armed.
            ColdLocalFileBridge.consumeSessionToken(context)
        } else {
            coldSessionRestoreArmed = false
        }
    }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp31 could not locate Exp27 cold-file helper")
    panel = panel.replace(anchor, helper, 1)

old_page = '''                    injectControllerContextMenuSupport(view)
                    GeoGebraWebNavigation.openPendingColdLocalFileIfAny()
'''
new_page = '''                    injectControllerContextMenuSupport(view)
                    GeoGebraWebNavigation.restoreColdSessionIfAny()
                    GeoGebraWebNavigation.openPendingColdLocalFileIfAny()
'''
if old_page in panel:
    panel = panel.replace(old_page, new_page, 1)
elif "GeoGebraWebNavigation.restoreColdSessionIfAny()" not in panel:
    raise RuntimeError("exp31 local MAIN onPageFinished anchor missing")

# ---------------------------------------------------------------------------
# 4) App-private, cross-process one-shot token storage. File storage is used
# instead of multi-process SharedPreferences caching.
# ---------------------------------------------------------------------------
if "EXP31_SESSION_HANDOFF_FILE" not in cold:
    old_constants = '''    private const val READY_NAME = "ready"

    private fun dir(context: Context): File =
'''
    new_constants = '''    private const val READY_NAME = "ready"
    // EXP31_SESSION_HANDOFF_FILE: app-private one-shot SSID snapshot.
    private const val SESSION_NAME = "session-token"

    private fun dir(context: Context): File =
'''
    if old_constants not in cold:
        raise RuntimeError("exp31 ColdLocalFileBridge constants anchor missing")
    cold = cold.replace(old_constants, new_constants, 1)

    old_files = '''    private fun stagedFile(context: Context): File = File(dir(context), FILE_NAME)
    private fun readyFile(context: Context): File = File(dir(context), READY_NAME)

    fun clearReady(context: Context) {
'''
    new_files = '''    private fun stagedFile(context: Context): File = File(dir(context), FILE_NAME)
    private fun readyFile(context: Context): File = File(dir(context), READY_NAME)
    private fun sessionFile(context: Context): File = File(dir(context), SESSION_NAME)

    fun prepareSessionRestore(context: Context, token: String?) {
        val file = sessionFile(context)
        if (token.isNullOrBlank()) {
            try { file.delete() } catch (_: Throwable) {}
            return
        }
        try {
            file.writeText(token)
        } catch (_: Throwable) {
            try { file.delete() } catch (_: Throwable) {}
        }
    }

    fun pendingSessionToken(context: Context): String? = try {
        val file = sessionFile(context)
        if (!file.isFile) null else file.readText().trim().takeIf { it.isNotBlank() }
    } catch (_: Throwable) {
        null
    }

    fun consumeSessionToken(context: Context) {
        try { sessionFile(context).delete() } catch (_: Throwable) {}
    }

    fun clearReady(context: Context) {
'''
    if old_files not in cold:
        raise RuntimeError("exp31 ColdLocalFileBridge file-helper anchor missing")
    cold = cold.replace(old_files, new_files, 1)

# ---------------------------------------------------------------------------
# Guards: Exp31 must literally be Exp27 XR/picker behavior + session continuity.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP27_COLD_PROCESS_PICKER",
    "EXP27_OPEN_COLD_PENDING_FILE",
    "EXP31_CURRENT_REMOTE_SESSION",
    "EXP31_SNAPSHOT_SESSION_BEFORE_COLD_PICKER",
    "EXP31_RESTORE_COLD_SESSION_ONCE",
    "GeoGebraWebNavigation.restoreColdSessionIfAny()",
    "deliverLoginToken(token)",
):
    if required not in panel:
        raise RuntimeError(f"exp31 panel requirement missing: {required}")

for required in (
    "EXP27_COLD_PICKER_PROXY",
    "EXP31_SESSION_HANDOFF_FILE",
    "KILL_MAIN_DELAY_MS = 300L",
    "Process.killProcess(process.pid)",
    "prepareSessionRestore(context: Context, token: String?)",
    "pendingSessionToken(context: Context)",
    "consumeSessionToken(context: Context)",
):
    if required not in cold:
        raise RuntimeError(f"exp31 cold requirement missing: {required}")

# Absolute regression guard: none of Exp28/29/30 runtime experiments may leak in.
for forbidden in (
    "EXP28_KEEP_MAIN_VISIBLE_WHILE_PICKING",
    "EXP28_POST_RESULT_COLD_HANDOFF",
    "EXP29_CONFIRMED_PROCESS_EXIT",
    "EXP30_GRACEFUL_XR_SHUTDOWN",
    "XR_RELEASE_SETTLE_MS",
    "requestGracefulSpatialShutdown",
):
    if forbidden in panel or forbidden in cold:
        raise RuntimeError(f"exp31 is not clean Exp27 base; found {forbidden}")

# Normal login bridge must remain exactly the Exp22/25 path. Exp31 must not add
# popup ownership or a new JavascriptInterface ACK.
if "coldLoginTokenAck" in panel or "EXP30_SESSION" in panel:
    raise RuntimeError("exp31 must not modify normal login ACK semantics")

panel_path.write_text(panel, encoding="utf-8")
cold_path.write_text(cold, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "session_continuity=exp31" not in text:
        text += (
            "session_continuity=exp31 Exp27 cold XR path unchanged; snapshot current SSID only "
            "when local picker launches, one-shot restore through Exp22 READY/SUCCESS bridge\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp31 installed: exact Exp27 cold XR path + isolated one-shot session restore")
