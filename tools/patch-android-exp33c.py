#!/usr/bin/env python3
"""Exp33c: separate SSID-cookie auth from OAuth tokens without touching navigation.

Applied on top of the exact Exp27 patch chain. This patch changes login credential
semantics only:

- trusted ggtcallback credentials remain OAuth tokens and use deliverLoginToken();
- GeoGebra SSID values use a dedicated logincookie MessageEvent;
- popup SSID is snapshotted before authentication navigation and only a changed
  cookie edge is forwarded;
- any surviving historical SSID-as-token block is rewritten semantically;
- the replacement of completePopupLoginFromCookie() is bounded to that one Kotlin
  function. Exp20/23/25 navigation and popup guards after it are never removed.

No Exp27 file-picker/XR code is modified.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp33c.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
panel = panel_path.read_text(encoding="utf-8")

for required in (
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
    "private val popupInitialSessionToken",
    "private val popupDeliveredSessionToken",
    "private fun popupGeoGebraSessionToken(view: WebView): String?",
):
    if required not in panel:
        raise RuntimeError(f"exp33c baseline marker missing: {required}")


def next_top_level_function(text: str, start: int) -> int:
    """Return the start of the next top-level `private fun`, preserving helpers."""
    pos = text.find("\nprivate fun ", start + 1)
    if pos < 0:
        raise RuntimeError("exp33c could not locate next top-level Kotlin function")
    return pos


# ---------------------------------------------------------------------------
# 1. Cookie-specific delivery beside Exp22's proven token delivery.
# ---------------------------------------------------------------------------
if "EXP33_COOKIE_LOGIN_DELIVERY" not in panel:
    anchor = "    // EXP17_OPENFROMGGT_HANDOFF:"
    pos = panel.find(anchor)
    if pos < 0:
        raise RuntimeError("exp33c Exp17 anchor after login bridge not found")

    helper = r'''    // EXP33_COOKIE_LOGIN_DELIVERY: SSID is a GeoGebra session cookie,
    // not an OAuth login token. Bundled LoginOperationW handles `logincookie`
    // through GeoGebraTubeUser(null, cookie), so the API receives {cookie: ...}.
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
# 2. Establish a pre-authentication SSID baseline.
# ---------------------------------------------------------------------------
if "EXP33_POPUP_COOKIE_BASELINE" not in panel:
    anchor = "private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {"
    pos = panel.find(anchor)
    if pos < 0:
        raise RuntimeError("exp33c completePopupLoginFromCookie anchor not found")

    helper = r'''// EXP33_POPUP_COOKIE_BASELINE: record SSID before login navigation.
// A pre-existing cookie is observation only; only a new/rotated SSID is evidence.
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
    raise RuntimeError("exp33c popup registration anchor not found")

# ---------------------------------------------------------------------------
# 3. Replace ONLY completePopupLoginFromCookie(), not the helpers following it.
# ---------------------------------------------------------------------------
signature = "private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {"
start = panel.find(signature)
if start < 0:
    raise RuntimeError("exp33c cookie handoff function missing")
end = next_top_level_function(panel, start + len(signature))

cookie_handoff = r'''private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    snapshotPopupSessionBaseline(view)
    val cookie = changedPopupSessionCookie(view) ?: return false

    // EXP33_COOKIE_EDGE_ONLY: SSID is authenticated as a cookie, never as token.
    GeoGebraWebNavigation.armLoginAck(view, cookie)
    if (!GeoGebraWebNavigation.deliverLoginCookie(cookie)) return false

    popupDeliveredSessionToken[view] = cookie
    popupInitialSessionToken[view] = cookie
    return true
}
'''
panel = panel[:start] + cookie_handoff + panel[end:]

# ---------------------------------------------------------------------------
# 4. Convert any historical early-close SSID-as-token block that still survives.
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
# 5. Safety invariants.
# ---------------------------------------------------------------------------
callback_start = panel.find("private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {")
if callback_start < 0:
    raise RuntimeError("exp33c trusted OAuth callback missing")
callback_end = next_top_level_function(panel, callback_start + 1)
callback = panel[callback_start:callback_end]
if "GeoGebraWebNavigation.deliverLoginToken(token)" not in callback:
    raise RuntimeError("exp33c trusted OAuth callback token path changed")
if "deliverLoginCookie" in callback:
    raise RuntimeError("exp33c OAuth callback must not use cookie delivery")

if old_ssid_pattern.search(panel) is not None:
    raise RuntimeError("exp33c SSID-as-token block remains")

for match in re.finditer(r'popupGeoGebraSessionToken\(view\)', panel):
    probe = panel[match.start():match.start() + 700]
    if "deliverLoginToken(" in probe:
        raise RuntimeError("exp33c SSID value still reaches deliverLoginToken")

# The navigation layer that protected Bug 1 must survive this login-only patch.
for required in (
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP20_REMOTE_ESCAPE_FALLBACK",
    "EXP25_STRICT_POPUP_WHITELIST",
    "private fun handleGeoGebraNavigation(",
    "if (!registerAsMain)",
    "if (!isRemoteGeoGebraUri(uri)) return false",
    "GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())",
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
        raise RuntimeError(f"exp33c requirement missing: {required}")

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
    "[GGQ] exp33 constrained SSID-cookie semantics installed; "
    f"rewrote {replacement_count} historical SSID-as-token block(s); "
    "Exp20/25 navigation guards preserved"
)
