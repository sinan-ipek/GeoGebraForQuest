#!/usr/bin/env python3
"""Exp33: keep Exp27 XR behavior, fix GeoGebra cookie/token login semantics only.

The current Android bridge reads GeoGebra's remote SSID cookie but forwards it
through `deliverLoginToken()`. GeoGebra's API explicitly distinguishes OAuth
`token` from session `cookie`. Sending SSID as a token can fail authorization;
GeoGebra then clears the real stored token, which explains spontaneous logout and
resource lists falling back away from the user's current materials.

Exp33 makes one isolated login change:
- real ggtcallback OAuth tokens still use `deliverLoginToken()` unchanged;
- SSID cookie evidence uses a new `deliverLoginCookie()` MessageEvent action;
- only a NEW/CHANGED SSID edge is forwarded. A pre-existing baseline cookie is
  never injected opportunistically, so a stale cookie cannot invalidate a good
  local OAuth token;
- popup baseline is snapshotted at creation, before authentication navigation.

Exp27 local-file process kill/relaunch timing is intentionally untouched.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp33.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")

for required in (
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
    "private val popupInitialSessionToken",
    "private fun popupGeoGebraSessionToken(view: WebView): String?",
):
    if required not in panel:
        raise RuntimeError(f"exp33 required baseline marker missing: {required}")

# ---------------------------------------------------------------------------
# Add a cookie-specific delivery path next to Exp22's proven token handshake.
# ---------------------------------------------------------------------------
if "EXP33_COOKIE_LOGIN_DELIVERY" not in panel:
    anchor = "    // EXP17_OPENFROMGGT_HANDOFF:"
    pos = panel.find(anchor)
    if pos < 0:
        raise RuntimeError("exp33 Exp17 anchor after login bridge not found")

    helper = r'''    // EXP33_COOKIE_LOGIN_DELIVERY: SSID is a GeoGebra session cookie,
    // not an OAuth login token. The bundled LoginOperationW has a dedicated
    // `logincookie` action that performs native cookie authentication and lets
    // GeoGebra persist the real OAuth token returned by the API.
    fun deliverLoginCookie(cookie: String): Boolean {
        val main = mainWebView.get() ?: return false
        if (cookie.isBlank()) return false
        val payload = JSONObject()
            .put("action", "logincookie")
            .put("msg", cookie)
            .toString()
        val jsPayload = JSONObject.quote(payload)
        val jsCredential = JSONObject.quote(cookie)

        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var data = $jsPayload;
                  var credential = $jsCredential;
                  var readyAttempts = 0;
                  var ackAttempts = 0;

                  function dispatchCookie() {
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
                      dispatchCookie();
                      return;
                    }
                    if (readyAttempts < 300) {
                      window.setTimeout(waitUntilReady, 100);
                    }
                  }

                  function waitForSuccess() {
                    ackAttempts++;
                    if (window.__ggqLoginSuccessToken === credential) {
                      try {
                        if (window.QuestBridge &&
                            typeof window.QuestBridge.loginTokenAck === 'function') {
                          window.QuestBridge.loginTokenAck(credential);
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
    panel = panel[:pos] + helper + panel[pos:]

# ---------------------------------------------------------------------------
# Snapshot the popup's pre-login SSID immediately. This turns later cookie use
# into a real authentication edge rather than an opportunistic stale-cookie guess.
# ---------------------------------------------------------------------------
if "EXP33_POPUP_COOKIE_BASELINE" not in panel:
    helper_anchor = "private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {"
    helper_pos = panel.find(helper_anchor)
    if helper_pos < 0:
        raise RuntimeError("exp33 completePopupLoginFromCookie anchor not found")

    baseline_helper = r'''// EXP33_POPUP_COOKIE_BASELINE: snapshot before login navigation so only
// a newly-created/rotated SSID is treated as authentication evidence.
private fun snapshotPopupSessionBaseline(view: WebView) {
    if (!popupInitialSessionToken.containsKey(view)) {
        popupInitialSessionToken[view] = popupGeoGebraSessionToken(view)
    }
}

private fun changedPopupSessionCookie(view: WebView): String? {
    snapshotPopupSessionBaseline(view)
    val current = popupGeoGebraSessionToken(view) ?: return null
    val baseline = popupInitialSessionToken[view]
    if (current == baseline) return null
    if (popupDeliveredSessionToken[view] == current) return null
    return current
}

'''
    panel = panel[:helper_pos] + baseline_helper + panel[helper_pos:]

# Capture baseline immediately after popup registration.
popup_anchor = '''        GeoGebraWebNavigation.registerPopup(popup)
        popup.post { refreshImeConnection(popup) }
'''
popup_replacement = '''        GeoGebraWebNavigation.registerPopup(popup)
        snapshotPopupSessionBaseline(popup)
        popup.post { refreshImeConnection(popup) }
'''
if popup_anchor in panel:
    panel = panel.replace(popup_anchor, popup_replacement, 1)
elif "snapshotPopupSessionBaseline(popup)" not in panel:
    raise RuntimeError("exp33 popup registration anchor not found")

# ---------------------------------------------------------------------------
# Replace Exp19 cookie handoff: baseline is observation only, changed cookie is
# authenticated through the new cookie-specific path.
# ---------------------------------------------------------------------------
start = panel.find("private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {")
end = panel.find("\nprivate fun refreshImeConnection", start)
if start < 0 or end < 0:
    raise RuntimeError("exp33 cookie handoff function bounds not found")

cookie_handoff = r'''private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    snapshotPopupSessionBaseline(view)
    val cookie = changedPopupSessionCookie(view) ?: return false

    // EXP33_COOKIE_EDGE_ONLY: never reinterpret a pre-existing SSID as an OAuth
    // token. A changed SSID is sent through GeoGebra's cookie-auth path; successful
    // userinfo returns and persists the real OAuth token.
    GeoGebraWebNavigation.armLoginAck(view, cookie)
    if (!GeoGebraWebNavigation.deliverLoginCookie(cookie)) return false

    popupDeliveredSessionToken[view] = cookie
    popupInitialSessionToken[view] = cookie
    return true
}
'''
panel = panel[:start] + cookie_handoff + panel[end:]

# ---------------------------------------------------------------------------
# Exp23/24 may quarantine/close a popup before onPageFinished. They may forward
# only a changed cookie edge, never the baseline SSID.
# ---------------------------------------------------------------------------
def replace_function_cookie_delivery(text: str, signature: str, next_signature: str) -> str:
    s = text.find(signature)
    if s < 0:
        raise RuntimeError(f"exp33 function not found: {signature}")
    e = text.find(next_signature, s)
    if e < 0:
        raise RuntimeError(f"exp33 next function anchor not found after: {signature}")
    block = text[s:e]

    old = '''    val token = popupGeoGebraSessionToken(view)
    if (!token.isNullOrBlank()) {
        GeoGebraWebNavigation.armLoginAck(view, token)
        GeoGebraWebNavigation.deliverLoginToken(token)
    }
'''
    new = '''    val cookie = changedPopupSessionCookie(view)
    if (!cookie.isNullOrBlank()) {
        GeoGebraWebNavigation.armLoginAck(view, cookie)
        GeoGebraWebNavigation.deliverLoginCookie(cookie)
        popupDeliveredSessionToken[view] = cookie
        popupInitialSessionToken[view] = cookie
    }
'''
    if old not in block:
        if "deliverLoginCookie(cookie)" in block:
            return text
        raise RuntimeError(f"exp33 SSID delivery block not found in: {signature}")
    block = block.replace(old, new, 1)
    return text[:s] + block + text[e:]

panel = replace_function_cookie_delivery(
    panel,
    "private fun quarantineRemoteGeoGebraAppPopup(view: WebView, url: String) {",
    "\nprivate fun inspectPopupForRemoteAppShell",
)
panel = replace_function_cookie_delivery(
    panel,
    "private fun closeForbiddenGeoGebraPopup(view: WebView, uri: Uri): Boolean {",
    "\nprivate fun handleGeoGebraNavigation",
)

# Proper OAuth callback token path must remain token-based.
callback_start = panel.find("private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {")
callback_end = panel.find("\n", panel.find("return true", callback_start)) + 1
callback_probe = panel[callback_start:callback_start + 1800] if callback_start >= 0 else ""
if "GeoGebraWebNavigation.deliverLoginToken(token)" not in callback_probe:
    raise RuntimeError("exp33 accidentally changed trusted OAuth callback token path")
if "deliverLoginCookie" in callback_probe:
    raise RuntimeError("exp33 OAuth callback must not use cookie delivery")

# No SSID-cookie helper output may still be sent through deliverLoginToken.
for signature in (
    "private fun completePopupLoginFromCookie",
    "private fun quarantineRemoteGeoGebraAppPopup",
    "private fun closeForbiddenGeoGebraPopup",
):
    s = panel.find(signature)
    if s < 0:
        raise RuntimeError(f"exp33 verification function missing: {signature}")
    block = panel[s:s + 2400]
    if "popupGeoGebraSessionToken" in block and "deliverLoginToken(" in block:
        raise RuntimeError(f"exp33 SSID still routed as token in {signature}")

for required in (
    "EXP33_COOKIE_LOGIN_DELIVERY",
    'put("action", "logincookie")',
    "EXP33_POPUP_COOKIE_BASELINE",
    "snapshotPopupSessionBaseline(popup)",
    "EXP33_COOKIE_EDGE_ONLY",
    "changedPopupSessionCookie(view)",
    "GeoGebraWebNavigation.deliverLoginCookie(cookie)",
    "EXP27_COLD_PROCESS_PICKER",
    "KILL_MAIN_DELAY_MS",  # exists in generated ColdLocalFilePicker, guarded in CI
):
    if required == "KILL_MAIN_DELAY_MS":
        continue
    if required not in panel:
        raise RuntimeError(f"exp33 Android requirement missing: {required}")

panel_path.write_text(panel, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "login_cookie_semantics=exp33" not in text:
        text += (
            "login_cookie_semantics=exp33 SSID uses dedicated cookie-auth action; "
            "only changed cookie edges are forwarded; OAuth callback token path unchanged\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp33 Android SSID cookie semantics + edge-only handoff installed")
