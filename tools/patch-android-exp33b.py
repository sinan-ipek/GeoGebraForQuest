#!/usr/bin/env python3
"""Exp33b: fix SSID-cookie authentication without relying on historical helper names.

This patch is intentionally applied on top of the exact Exp27 runtime. It changes
only login credential semantics:

* OAuth callback credentials remain `logintoken` and use deliverLoginToken().
* Remote GeoGebra SSID values are session cookies, so they use `logincookie` and
  GeoGebra's cookie-auth path.
* A popup's SSID is snapshotted when the popup is created. Only a new/changed
  cookie is forwarded; a stale baseline cookie is observation only.
* Every remaining historical block that reads popupGeoGebraSessionToken(view)
  and forwards it through deliverLoginToken() is replaced semantically, regardless
  of which Exp23/24/25 helper currently contains it.

No Exp27 file-picker/XR code is touched.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp33b.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")

for required in (
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
    "private val popupInitialSessionToken",
    "private val popupDeliveredSessionToken",
    "private fun popupGeoGebraSessionToken(view: WebView): String?",
):
    if required not in panel:
        raise RuntimeError(f"exp33b baseline marker missing: {required}")

# ---------------------------------------------------------------------------
# 1. Add a cookie-specific delivery path beside the proven Exp22 token bridge.
# ---------------------------------------------------------------------------
if "EXP33_COOKIE_LOGIN_DELIVERY" not in panel:
    anchor = "    // EXP17_OPENFROMGGT_HANDOFF:"
    pos = panel.find(anchor)
    if pos < 0:
        raise RuntimeError("exp33b Exp17 anchor after login bridge not found")

    helper = r'''    // EXP33_COOKIE_LOGIN_DELIVERY: SSID is a GeoGebra session cookie,
    // not an OAuth login token. The bundled LoginOperationW has a dedicated
    // `logincookie` action that performs GeoGebra's native cookie authentication.
    // On success the backend returns the real OAuth token, which GeoGebra stores.
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
# 2. Snapshot SSID before authentication navigation; only an edge is evidence.
# ---------------------------------------------------------------------------
if "EXP33_POPUP_COOKIE_BASELINE" not in panel:
    anchor = "private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {"
    pos = panel.find(anchor)
    if pos < 0:
        raise RuntimeError("exp33b completePopupLoginFromCookie anchor not found")

    helper = r'''// EXP33_POPUP_COOKIE_BASELINE: record the cookie state before the login flow.
// A pre-existing SSID is never injected into MAIN merely because it exists.
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
    panel = panel[:pos] + helper + panel[pos:]

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
    raise RuntimeError("exp33b popup registration anchor not found")

# ---------------------------------------------------------------------------
# 3. Replace the central onPageFinished SSID handoff with cookie authentication.
# ---------------------------------------------------------------------------
start = panel.find("private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {")
end = panel.find("\nprivate fun refreshImeConnection", start)
if start < 0 or end < 0:
    raise RuntimeError("exp33b cookie handoff function bounds not found")

cookie_handoff = r'''private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    snapshotPopupSessionBaseline(view)
    val cookie = changedPopupSessionCookie(view) ?: return false

    // EXP33_COOKIE_EDGE_ONLY: a changed SSID is authenticated as a cookie.
    GeoGebraWebNavigation.armLoginAck(view, cookie)
    if (!GeoGebraWebNavigation.deliverLoginCookie(cookie)) return false

    popupDeliveredSessionToken[view] = cookie
    popupInitialSessionToken[view] = cookie
    return true
}
'''
panel = panel[:start] + cookie_handoff + panel[end:]

# ---------------------------------------------------------------------------
# 4. Historical early-close/quarantine helpers may still contain an SSID block.
# Replace every exact semantic instance globally instead of naming the helper.
# Zero matches is valid when the current Exp27 patch chain has already removed
# those historical helpers; the safety guards below remain authoritative.
# ---------------------------------------------------------------------------
old_ssid_pattern = re.compile(
    r'(?P<indent>^[ \t]*)val token = popupGeoGebraSessionToken\(view\)\n'
    r'(?P=indent)if \(!token\.isNullOrBlank\(\)\) \{\n'
    r'(?P=indent)[ \t]+GeoGebraWebNavigation\.armLoginAck\(view, token\)\n'
    r'(?P=indent)[ \t]+GeoGebraWebNavigation\.deliverLoginToken\(token\)\n'
    r'(?P=indent)\}',
    re.MULTILINE,
)

replacement_count = 0
while True:
    match = old_ssid_pattern.search(panel)
    if match is None:
        break
    indent = match.group("indent")
    inner = indent + "    "
    replacement = (
        indent + "val cookie = changedPopupSessionCookie(view)\n"
        + indent + "if (!cookie.isNullOrBlank()) {\n"
        + inner + "GeoGebraWebNavigation.armLoginAck(view, cookie)\n"
        + inner + "GeoGebraWebNavigation.deliverLoginCookie(cookie)\n"
        + inner + "popupDeliveredSessionToken[view] = cookie\n"
        + inner + "popupInitialSessionToken[view] = cookie\n"
        + indent + "}"
    )
    panel = panel[:match.start()] + replacement + panel[match.end():]
    replacement_count += 1

# ---------------------------------------------------------------------------
# 5. Safety guards: OAuth callback remains token-auth; SSID can never be token-auth.
# ---------------------------------------------------------------------------
callback_start = panel.find("private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {")
if callback_start < 0:
    raise RuntimeError("exp33b trusted OAuth callback function missing")
callback_probe = panel[callback_start:callback_start + 2200]
if "GeoGebraWebNavigation.deliverLoginToken(token)" not in callback_probe:
    raise RuntimeError("exp33b trusted OAuth callback token path was changed")
if "deliverLoginCookie" in callback_probe:
    raise RuntimeError("exp33b OAuth callback must never use cookie delivery")

# The old semantic anti-pattern must be completely gone.
if old_ssid_pattern.search(panel) is not None:
    raise RuntimeError("exp33b SSID-as-token block remains")

# Any direct SSID read should be baseline/edge observation, not followed by token delivery.
for match in re.finditer(r'popupGeoGebraSessionToken\(view\)', panel):
    probe = panel[match.start():match.start() + 700]
    if "deliverLoginToken(" in probe:
        raise RuntimeError("exp33b SSID value still reaches deliverLoginToken")

for required in (
    "EXP33_COOKIE_LOGIN_DELIVERY",
    'put("action", "logincookie")',
    "EXP33_POPUP_COOKIE_BASELINE",
    "snapshotPopupSessionBaseline(popup)",
    "EXP33_COOKIE_EDGE_ONLY",
    "changedPopupSessionCookie(view)",
    "GeoGebraWebNavigation.deliverLoginCookie(cookie)",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in panel:
        raise RuntimeError(f"exp33b requirement missing: {required}")

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

print(
    "[GGQ] exp33 semantic SSID-cookie handoff installed; "
    f"rewrote {replacement_count} historical SSID-as-token block(s)"
)
