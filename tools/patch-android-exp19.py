#!/usr/bin/env python3
"""Exp19: recover login, stereo visibility, and Spatial input across file loads.

Three lifecycle failures are fixed together because they are all transition bugs:

1) Exp18 closed any registered popup as soon as *any* GeoGebra SSID cookie was
   visible. A stale/pre-existing cookie could therefore kill the login popup
   before the user could authenticate. Exp19 snapshots the popup's initial SSID,
   forwards it to MAIN without closing, and only treats a NEW/CHANGED SSID as a
   completed login edge.

2) SpatialGeoGebraActivity de-duplicated the last active stereo layout even after
   an inactive transition. A newly loaded file with the same 3D rectangle could
   therefore stay hidden. Exp19 clears the native de-duplication state on inactive.

3) ACTION_OPEN_DOCUMENT temporarily moves the Quest app from immersive Spatial
   focus to a normal Android activity. On return, the Controller component can
   still say laserEnabled=true while the native ray/input presentation has not
   rebound. Exp19 reasserts controller laser state for a short recovery window and
   explicitly restores MAIN WebView focus on Activity/VR resume.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp19.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
controller_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"

# ---------------------------------------------------------------------------
# GeoGebraWebPanel: do not let a stale SSID close the login popup.
# ---------------------------------------------------------------------------
panel = panel_path.read_text(encoding="utf-8")

if "EXP19_POPUP_SESSION_EDGE" not in panel:
    start_marker = "// EXP18_POPUP_SSID_HANDOFF:"
    start = panel.find(start_marker)
    end = panel.find("private fun refreshImeConnection", start)
    if start < 0 or end < 0:
        raise RuntimeError("exp19 could not locate exp18 popup SSID helper block")

    replacement = r'''// EXP19_POPUP_SESSION_EDGE: a cookie that already existed when the popup
// first loaded is NOT proof that the current login just completed. Keep the popup
// usable, seed MAIN with that token opportunistically, and close only after an
// actual SSID edge (blank->value or value->different value).
private val popupInitialSessionToken = java.util.WeakHashMap<WebView, String?>()
private val popupDeliveredSessionToken = java.util.WeakHashMap<WebView, String>()

private fun popupGeoGebraSessionToken(view: WebView): String? {
    val cookies = CookieManager.getInstance()
    val candidates = linkedSetOf<String>()
    view.url?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
        ?.let { candidates.add(it) }
    candidates.add("https://www.geogebra.org/")
    candidates.add("https://geogebra.org/")
    candidates.add("https://accounts.geogebra.org/")

    for (url in candidates) {
        cookieValue(cookies.getCookie(url), "SSID")?.let { return it }
    }
    return null
}

private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    val token = popupGeoGebraSessionToken(view)

    // First completed page establishes the baseline. A pre-existing valid cookie
    // is still useful to MAIN, but MUST NOT close the popup; a stale cookie must
    // likewise never prevent the user from reaching the login form.
    if (!popupInitialSessionToken.containsKey(view)) {
        popupInitialSessionToken[view] = token
        if (!token.isNullOrBlank()) {
            if (GeoGebraWebNavigation.deliverLoginToken(token)) {
                popupDeliveredSessionToken[view] = token
            }
        }
        return false
    }

    val baseline = popupInitialSessionToken[view]
    if (token.isNullOrBlank() || token == baseline) return false
    if (popupDeliveredSessionToken[view] == token) return false
    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false

    popupDeliveredSessionToken[view] = token
    popupInitialSessionToken[view] = token

    // The token edge happened after the popup was already usable, so this is a
    // completed authentication transition rather than a stale-cookie guess.
    // Give LoginOperationW time to consume the MessageEvent, then close only the
    // registered popup. Explicit ggtcallback handling from exp15/17 remains valid.
    view.postDelayed({
        if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
            GeoGebraWebNavigation.closePopup(view)
        }
    }, 900L)
    return true
}

'''
    panel = panel[:start] + replacement + panel[end:]

if "EXP19_MAIN_INPUT_FOCUS_RECOVERY" not in panel:
    anchor = "    fun handleBack(): Boolean {\n"
    insert = r'''    // EXP19_MAIN_INPUT_FOCUS_RECOVERY: ACTION_OPEN_DOCUMENT temporarily gives
    // Android/Spatial focus to another Activity. Rebind the local WebView when we
    // return so controller pointer events are delivered to A again.
    fun restoreMainInputFocus() {
        val main = mainWebView.get() ?: return
        main.post {
            try {
                main.onResume()
                main.resumeTimers()
                main.requestFocus()
                refreshImeConnection(main)
                main.evaluateJavascript(
                    "try { window.focus(); document.body && document.body.focus && document.body.focus(); } catch (_) {}",
                    null,
                )
            } catch (_: Throwable) {
            }
        }
    }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp19 handleBack anchor not found")
    panel = panel.replace(anchor, insert, 1)

# Production exp19 must not leave exp18's visible red diagnostic banner behind.
for forbidden in (
    "ggq-popup-login-diagnostic",
    "GGQ POPUP | SSID ",
    "injectPopupLoginDiagnostic(",
):
    if forbidden in panel:
        raise RuntimeError(f"exp19 popup diagnostic residue remains: {forbidden}")

for required in (
    "EXP19_POPUP_SESSION_EDGE",
    "popupInitialSessionToken",
    "token == baseline",
    "popupDeliveredSessionToken",
    "EXP19_MAIN_INPUT_FOCUS_RECOVERY",
    "fun restoreMainInputFocus()",
    "main.onResume()",
    "main.resumeTimers()",
):
    if required not in panel:
        raise RuntimeError(f"exp19 panel requirement missing: {required}")

panel_path.write_text(panel, encoding="utf-8")

# ---------------------------------------------------------------------------
# Spatial activity: rearm layout after inactive and restore Spatial input after
# returning from Android file picker / non-immersive activity.
# ---------------------------------------------------------------------------
activity = activity_path.read_text(encoding="utf-8")

if "EXP19_CONTROLLER_RECOVERY_SYSTEM" not in activity:
    prop_anchor = "    private var startupSplashActive = true\n"
    prop_replacement = prop_anchor + \
        "\n    // EXP19_CONTROLLER_RECOVERY_SYSTEM\n" + \
        "    private lateinit var controllerShortcutSystem: QuestControllerShortcutSystem\n"
    if prop_anchor not in activity:
        raise RuntimeError("exp19 startupSplashActive anchor not found")
    activity = activity.replace(prop_anchor, prop_replacement, 1)

    old_register = "        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n"
    new_register = (
        "        controllerShortcutSystem = QuestControllerShortcutSystem(this)\n"
        "        systemManager.registerSystem(controllerShortcutSystem)\n"
    )
    if old_register not in activity:
        raise RuntimeError("exp19 controller registration anchor not found")
    activity = activity.replace(old_register, new_register, 1)

if "EXP19_SPATIAL_INPUT_RECOVERY" not in activity:
    back_anchor = '''    @Suppress("DEPRECATION")
    override fun onBackPressed() {
'''
    recovery = r'''    // EXP19_SPATIAL_INPUT_RECOVERY: the system document picker is a normal
    // Android Activity, so the Spatial/OpenXR presentation may need a few frames
    // to reacquire controller/ray state after returning.
    private fun recoverSpatialInputAfterExternalActivity() {
        if (::controllerShortcutSystem.isInitialized) {
            controllerShortcutSystem.requestInputRecovery()
        }
        GeoGebraWebNavigation.restoreMainInputFocus()

        window.decorView.postDelayed({
            if (::controllerShortcutSystem.isInitialized) {
                controllerShortcutSystem.requestInputRecovery()
            }
            GeoGebraWebNavigation.restoreMainInputFocus()
        }, 350L)

        window.decorView.postDelayed({
            if (::controllerShortcutSystem.isInitialized) {
                controllerShortcutSystem.requestInputRecovery()
            }
            GeoGebraWebNavigation.restoreMainInputFocus()
        }, 1200L)
    }

    override fun onPostResume() {
        super.onPostResume()
        recoverSpatialInputAfterExternalActivity()
    }

''' + back_anchor
    if back_anchor not in activity:
        raise RuntimeError("exp19 onBackPressed anchor not found")
    activity = activity.replace(back_anchor, recovery, 1)

# Returning from ACTION_OPEN_DOCUMENT must run the recovery immediately as well
# as via onPostResume, because callback/file loading may begin before XR input is
# completely rebound.
old_result = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
'''
new_result = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            recoverSpatialInputAfterExternalActivity()
            return
        }
'''
if old_result in activity:
    activity = activity.replace(old_result, new_result, 1)
elif "recoverSpatialInputAfterExternalActivity()\n            return" not in activity:
    raise RuntimeError("exp19 onActivityResult anchor not found")

# onVRReady is called again when an AppSystemActivity returns from non-immersive
# mode. Recovery must happen even though entity creation remains one-shot.
vr_anchor = '''    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
'''
vr_replacement = '''    override fun onVRReady() {
        super.onVRReady()
        recoverSpatialInputAfterExternalActivity()
        if (vrReady) return
'''
if vr_anchor in activity:
    activity = activity.replace(vr_anchor, vr_replacement, 1)
elif "recoverSpatialInputAfterExternalActivity()\n        if (vrReady) return" not in activity:
    raise RuntimeError("exp19 onVRReady anchor not found")

# Native de-duplication must also be rearmed on inactive; JS exp19 performs the
# matching reset on its side.
inactive_anchor = '''            if (!root.optBoolean("active", true)) {
                embeddedStereoVisible = false
'''
inactive_replacement = '''            if (!root.optBoolean("active", true)) {
                // EXP19_NATIVE_LAYOUT_REARM: a new file may recreate the exact same
                // 3D rectangle. Forget the previous active payload when hiding B.
                lastAppliedEmbeddedLayout = null
                embeddedStereoVisible = false
'''
if inactive_anchor in activity:
    activity = activity.replace(inactive_anchor, inactive_replacement, 1)
elif "EXP19_NATIVE_LAYOUT_REARM" not in activity:
    raise RuntimeError("exp19 inactive layout anchor not found")

for required in (
    "EXP19_CONTROLLER_RECOVERY_SYSTEM",
    "EXP19_SPATIAL_INPUT_RECOVERY",
    "override fun onPostResume()",
    "recoverSpatialInputAfterExternalActivity()",
    "controllerShortcutSystem.requestInputRecovery()",
    "EXP19_NATIVE_LAYOUT_REARM",
    "lastAppliedEmbeddedLayout = null",
):
    if required not in activity:
        raise RuntimeError(f"exp19 activity requirement missing: {required}")

activity_path.write_text(activity, encoding="utf-8")

# ---------------------------------------------------------------------------
# Controller system: reassert the component for a short window even if its
# cached laserEnabled field already says true.
# ---------------------------------------------------------------------------
controller = controller_path.read_text(encoding="utf-8")

if "EXP19_INPUT_RECOVERY_WINDOW" not in controller:
    field_anchor = "    private var rightGripRotateActive = false\n"
    field_replacement = field_anchor + r'''

    // EXP19_INPUT_RECOVERY_WINDOW: after an external Android Activity the cached
    // Controller can still report laserEnabled=true while native presentation is
    // being rebound. Push the component again for several Spatial frames.
    private var inputRecoveryFrames = 0

    internal fun requestInputRecovery(frames: Int = 180) {
        if (frames > inputRecoveryFrames) inputRecoveryFrames = frames
    }
'''
    if field_anchor not in controller:
        raise RuntimeError("exp19 controller field anchor not found")
    controller = controller.replace(field_anchor, field_replacement, 1)

    query_anchor = '''        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }

        for (entity in controllers) {
'''
    query_replacement = '''        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        val forceInputRecovery = inputRecoveryFrames > 0
        if (forceInputRecovery && controllers.isNotEmpty()) {
            inputRecoveryFrames--
        }

        for (entity in controllers) {
'''
    if query_anchor not in controller:
        raise RuntimeError("exp19 controller query anchor not found")
    controller = controller.replace(query_anchor, query_replacement, 1)

    laser_anchor = '''            if (!controller.laserEnabled) {
                controller.laserEnabled = true
                entity.setComponent(controller)
            }
'''
    laser_replacement = '''            if (forceInputRecovery || !controller.laserEnabled) {
                controller.laserEnabled = true
                entity.setComponent(controller)
            }
'''
    if laser_anchor not in controller:
        raise RuntimeError("exp19 laser anchor not found")
    controller = controller.replace(laser_anchor, laser_replacement, 1)

for required in (
    "EXP19_INPUT_RECOVERY_WINDOW",
    "fun requestInputRecovery(frames: Int = 180)",
    "forceInputRecovery || !controller.laserEnabled",
    "entity.setComponent(controller)",
):
    if required not in controller:
        raise RuntimeError(f"exp19 controller requirement missing: {required}")

controller_path.write_text(controller, encoding="utf-8")

# Append build metadata after build-geogebra-quest.sh has produced the source WAR.
meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    meta_text = meta.read_text(encoding="utf-8")
    marker = "file_load_lifecycle=exp19"
    if marker not in meta_text:
        meta_text += (
            "file_load_lifecycle=exp19 inactive->same-layout rearm; "
            "popup SSID edge gating; Spatial input recovery after document picker\n"
        )
        meta.write_text(meta_text, encoding="utf-8")

print("[GGQ] exp19 file/login/input lifecycle recovery installed")
