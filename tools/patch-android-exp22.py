#!/usr/bin/env python3
"""Exp22: deterministic login handshake + AvatarSystem document-picker recovery.

Two independent failures are targeted without disturbing Exp20/21's working cloud
material and stereo paths.

LOGIN
-----
Exp15-19 delivered an SSID token to MAIN with a fire-and-forget MessageEvent.
If local LoginOperationW had not installed its listener yet, the event vanished.
Exp22 waits for GeoGebra source marker __ggqLoginReady, dispatches the token only
then, and closes the popup only after GeoGebra reports __ggqLoginSuccessToken for
that exact token. No fixed 250/900 ms success guess remains.

LOCAL FILE / CONTROLLER
-----------------------
Exp21 proved that restoring the v0.9.29 WebView file callback and removing direct
Controller writes did not cure the controller disappearance. Exp22 therefore
moves one layer up to the Meta-owned representation system: a dedicated Spatial
SystemBase resets/reasserts AvatarSystem controller visibility after returning
from ACTION_OPEN_DOCUMENT. Controller components remain read-only and are logged
for diagnosis; no laserEnabled or Controller component write is reintroduced.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp22.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
recovery_path = root / (
    "app/src/main/java/com/sinan/geogebraforquest/"
    "QuestControllerPresentationRecoverySystem.kt"
)

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
recovery = recovery_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# MAIN login delivery: replace fire-and-forget token dispatch with READY/SUCCESS
# handshake and track the popup that owns each pending token.
# ---------------------------------------------------------------------------
start = panel.find("    // EXP15_LOCAL_LOGIN_TOKEN_BRIDGE:")
end = panel.find("    // EXP17_OPENFROMGGT_HANDOFF:", start)
if start < 0 or end < 0:
    raise RuntimeError("exp22 could not locate exp15 login bridge block")

login_bridge = r'''    // EXP22_LOGIN_READY_SUCCESS_HANDSHAKE: MAIN receives a token only after
    // bundled LoginOperationW has installed its message listener. The popup is
    // closed only after GeoGebra itself reaches logged-in state for that token.
    private val pendingLoginAckPopups = java.util.WeakHashMap<WebView, String>()

    fun armLoginAck(webView: WebView, token: String) {
        if (token.isBlank() || !isRegisteredPopup(webView)) return
        synchronized(pendingLoginAckPopups) {
            pendingLoginAckPopups[webView] = token
        }
    }

    fun onLoginTokenAck(token: String) {
        if (token.isBlank()) return
        val popup = synchronized(pendingLoginAckPopups) {
            val entry = pendingLoginAckPopups.entries.firstOrNull { it.value == token }
            entry?.key.also { candidate ->
                if (candidate != null) pendingLoginAckPopups.remove(candidate)
            }
        } ?: return

        popup.post {
            if (isRegisteredPopup(popup)) {
                closePopup(popup)
            }
        }
    }

    fun deliverLoginToken(token: String): Boolean {
        val main = mainWebView.get() ?: return false
        if (token.isBlank()) return false
        val payload = JSONObject()
            .put("action", "logintoken")
            .put("msg", token)
            .toString()
        val jsPayload = JSONObject.quote(payload)
        val jsToken = JSONObject.quote(token)

        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var data = $jsPayload;
                  var token = $jsToken;
                  var readyAttempts = 0;
                  var ackAttempts = 0;

                  function dispatchToken() {
                    // Clear a success marker from an earlier login using the same SSID.
                    try { window.__ggqLoginSuccessToken = null; } catch (_) {}
                    try {
                      window.dispatchEvent(new MessageEvent('message', {
                        data: data,
                        origin: 'https://www.geogebra.org'
                      }));
                    } catch (e) {
                      try {
                        var event = document.createEvent('MessageEvent');
                        event.initMessageEvent(
                          'message', false, false, data,
                          'https://www.geogebra.org', '', window, null
                        );
                        window.dispatchEvent(event);
                      } catch (_) {}
                    }
                    waitForSuccess();
                  }

                  function waitUntilReady() {
                    readyAttempts++;
                    if (window.__ggqLoginReady === true) {
                      dispatchToken();
                      return;
                    }
                    if (readyAttempts < 300) {
                      window.setTimeout(waitUntilReady, 100);
                    }
                  }

                  function waitForSuccess() {
                    ackAttempts++;
                    if (window.__ggqLoginSuccessToken === token) {
                      try {
                        if (window.QuestBridge &&
                            typeof window.QuestBridge.loginTokenAck === 'function') {
                          window.QuestBridge.loginTokenAck(token);
                        }
                      } catch (_) {}
                      return;
                    }
                    if (ackAttempts < 300) {
                      window.setTimeout(waitForSuccess, 100);
                    }
                  }

                  waitUntilReady();
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }

'''
panel = panel[:start] + login_bridge + panel[end:]

# Clear any pending ACK ownership when a popup is explicitly destroyed.
close_anchor = '''    fun closePopup(webView: WebView) {
        unregisterPopup(webView)
'''
close_replacement = '''    fun closePopup(webView: WebView) {
        synchronized(pendingLoginAckPopups) {
            pendingLoginAckPopups.remove(webView)
        }
        unregisterPopup(webView)
'''
if close_anchor not in panel:
    raise RuntimeError("exp22 closePopup anchor not found")
panel = panel.replace(close_anchor, close_replacement, 1)

# The trusted ggtcallback token path must arm ACK ownership and must no longer
# close the popup merely because a token string was observed.
old_callback_tail = '''    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false

    if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
        view.post { GeoGebraWebNavigation.closePopup(view) }
    }
    return true
}
'''
new_callback_tail = '''    if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
        GeoGebraWebNavigation.armLoginAck(view, token)
    }
    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false
    return true
}
'''
if old_callback_tail not in panel:
    raise RuntimeError("exp22 trusted login callback tail anchor not found")
panel = panel.replace(old_callback_tail, new_callback_tail, 1)

# Exp19 cookie handoff remains the source of the SSID, but popup closure now
# belongs exclusively to the SUCCESS ACK path above.
func_start = panel.find("private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {")
func_end = panel.find("\nprivate fun refreshImeConnection", func_start)
if func_start < 0 or func_end < 0:
    raise RuntimeError("exp22 exp19 cookie handoff function not found")

cookie_handoff = r'''private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    val token = popupGeoGebraSessionToken(view)

    // The first completed page establishes the baseline. A pre-existing valid
    // session is still worth handing to MAIN, but the popup remains open until
    // the local GeoGebra SUCCESS ACK proves that the token actually worked.
    if (!popupInitialSessionToken.containsKey(view)) {
        popupInitialSessionToken[view] = token
        if (!token.isNullOrBlank()) {
            GeoGebraWebNavigation.armLoginAck(view, token)
            if (GeoGebraWebNavigation.deliverLoginToken(token)) {
                popupDeliveredSessionToken[view] = token
            }
        }
        return false
    }

    val baseline = popupInitialSessionToken[view]
    if (token.isNullOrBlank()) return false

    // A changed token is a strong authentication edge. A repeated token may
    // still be legitimate (server-side session reuse), so allow it to be armed
    // again if this popup has not already handed that token to MAIN.
    if (popupDeliveredSessionToken[view] == token && token == baseline) return false

    GeoGebraWebNavigation.armLoginAck(view, token)
    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false

    popupDeliveredSessionToken[view] = token
    popupInitialSessionToken[view] = token
    return token != baseline
}
'''
panel = panel[:func_start] + cookie_handoff + panel[func_end:]

# MAIN-only JavascriptInterface receives the verified success marker from the JS
# polling wrapper after LoginOperationW has actually logged in.
bridge_anchor = '''    @JavascriptInterface
    fun panelReady() {
        if (spatialMode) SpatialBridgeBus.panelReady()
    }
'''
bridge_insert = bridge_anchor + '''

    // EXP22_LOGIN_SUCCESS_ACK_BRIDGE
    @JavascriptInterface
    fun loginTokenAck(token: String) {
        if (token.isNotBlank()) {
            GeoGebraWebNavigation.onLoginTokenAck(token)
        }
    }
'''
if bridge_anchor not in panel:
    raise RuntimeError("exp22 QuestBridge panelReady anchor not found")
panel = panel.replace(bridge_anchor, bridge_insert, 1)

# ---------------------------------------------------------------------------
# Spatial Activity: register the dedicated AvatarSystem recovery system and arm
# it only on a real external local-file boundary / subsequent VR return.
# ---------------------------------------------------------------------------
field_anchor = "    private var startupSplashActive = true\n"
field_replacement = field_anchor + (
    "\n    // EXP22_AVATAR_CONTROLLER_RETURN\n"
    "    private lateinit var controllerPresentationRecoverySystem: "
    "QuestControllerPresentationRecoverySystem\n"
)
if field_anchor not in activity:
    raise RuntimeError("exp22 Activity startupSplashActive anchor not found")
activity = activity.replace(field_anchor, field_replacement, 1)

register_anchor = "        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n"
register_replacement = (
    "        controllerPresentationRecoverySystem = QuestControllerPresentationRecoverySystem()\n"
    "        systemManager.registerSystem(controllerPresentationRecoverySystem)\n"
    "        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n"
)
if register_anchor not in activity:
    raise RuntimeError("exp22 controller system registration anchor not found")
activity = activity.replace(register_anchor, register_replacement, 1)

back_anchor = '''    @Suppress("DEPRECATION")
    override fun onBackPressed() {
'''
recovery_helper = r'''    private fun requestControllerPresentationRecovery(reason: String) {
        if (!::controllerPresentationRecoverySystem.isInitialized) return
        controllerPresentationRecoverySystem.requestRecovery(reason)

        // Requests only publish a volatile flag. AvatarSystem lookup and mutation
        // occur later on the Spatial system thread inside the recovery system.
        window.decorView.postDelayed({
            if (::controllerPresentationRecoverySystem.isInitialized) {
                controllerPresentationRecoverySystem.requestRecovery("$reason+400ms")
            }
        }, 400L)
        window.decorView.postDelayed({
            if (::controllerPresentationRecoverySystem.isInitialized) {
                controllerPresentationRecoverySystem.requestRecovery("$reason+1200ms")
            }
        }, 1200L)
    }

''' + back_anchor
if back_anchor not in activity:
    raise RuntimeError("exp22 onBackPressed anchor not found")
activity = activity.replace(back_anchor, recovery_helper, 1)

result_anchor = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
'''
result_replacement = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            requestControllerPresentationRecovery("local-file-result")
            return
        }
'''
if result_anchor not in activity:
    raise RuntimeError("exp22 Activity local-file result anchor not found")
activity = activity.replace(result_anchor, result_replacement, 1)

vr_anchor = '''    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
'''
vr_replacement = '''    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) {
            requestControllerPresentationRecovery("vr-ready-return")
            return
        }
'''
if vr_anchor not in activity:
    raise RuntimeError("exp22 Activity onVRReady anchor not found")
activity = activity.replace(vr_anchor, vr_replacement, 1)

# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
for required in (
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "pendingLoginAckPopups",
    "window.__ggqLoginReady === true",
    "window.__ggqLoginSuccessToken === token",
    "window.QuestBridge.loginTokenAck(token)",
    "EXP22_LOGIN_SUCCESS_ACK_BRIDGE",
    "GeoGebraWebNavigation.armLoginAck(view, token)",
):
    if required not in panel:
        raise RuntimeError(f"exp22 login requirement missing: {required}")

if "view.postDelayed({\n        if (GeoGebraWebNavigation.isRegisteredPopup(view))" in panel:
    raise RuntimeError("exp22 fixed-delay popup-success closure residue remains")

for required in (
    "EXP22_AVATAR_CONTROLLER_RETURN",
    "QuestControllerPresentationRecoverySystem",
    "requestControllerPresentationRecovery(\"local-file-result\")",
    "requestControllerPresentationRecovery(\"vr-ready-return\")",
):
    if required not in activity:
        raise RuntimeError(f"exp22 Activity requirement missing: {required}")

for required in (
    "AvatarSystem",
    "setShowControllers",
    "getShowControllers",
    "localControllers",
    "activeControllers",
    "laserEnabledControllers",
):
    if required not in recovery:
        raise RuntimeError(f"exp22 recovery-system requirement missing: {required}")

# Exp22 must not regress into direct Controller writes.
for forbidden in (
    "controller.laserEnabled =",
    "entity.setComponent(controller)",
):
    if forbidden in recovery:
        raise RuntimeError(f"exp22 recovery system directly writes Controller: {forbidden}")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "login_handshake=exp22" not in text:
        text += (
            "login_handshake=exp22 LoginOperationW READY + verified logged-in SUCCESS ACK; "
            "no fixed-delay popup closure\n"
        )
    if "controller_return=exp22" not in text:
        text += (
            "controller_return=exp22 AvatarSystem visibility reset/reassert after DocumentsUI; "
            "Controller components read-only with state diagnostics\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp22 deterministic login handshake + AvatarSystem controller return installed")
