#!/usr/bin/env python3
"""Exp38: keep OAuth token delivery alive until GeoGebra confirms SUCCESS.

Exp34 introduced a token-first login path, but it still contained two timing
guesses: the popup WebStorage probe stopped after 60 seconds, and a token was
deduplicated as soon as delivery was merely queued.  A lost evaluateJavascript
call could therefore leave the remote account logged in while MAIN stayed
logged out.  Later launches appeared to fix the problem only because WebView
cookies had already warmed the remote account session.

Exp38 makes delivery acknowledgement-driven:
- probe the registered popup for its real OAuth token for its whole lifetime;
- retry native-to-MAIN delivery while that popup and token remain current;
- make the MAIN JavaScript bridge idempotent and retry the MessageEvent every
  eight seconds until LoginOperationW publishes the exact SUCCESS token;
- cancel a pending delivery when its popup is explicitly closed;
- preserve Exp34's rule that native persistence happens only after SUCCESS.

No SSID/cookie value is used for authentication.  Exp35 IME/thumb behavior and
Exp27 local-file/XR behavior are deliberately untouched.
"""

from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp38.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

for required in (
    "EXP34_TOKEN_FIRST_SESSION_OWNER",
    "EXP34_NO_SSID_AUTH",
    "EXP35_LOGIN_IME_NEXT_GUARD",
    "EXP35_RIGHT_THUMB_ZOOM_BRIDGE",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in text:
        raise RuntimeError(f"exp38 baseline requirement missing: {required}")


def replace_function(source: str, signature: str, replacement: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"exp38 function not found: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise RuntimeError(f"exp38 opening brace not found: {signature}")
    depth = 0
    for index in range(brace, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[:start] + replacement + source[index + 1 :]
    raise RuntimeError(f"exp38 closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# 1. MAIN delivery is idempotent and acknowledgement-driven.  Native retries
# re-install this state if a WebView navigation discarded an earlier JS call;
# once installed, the JS state itself avoids duplicate concurrent loops.
# ---------------------------------------------------------------------------
delivery_signature = "    fun deliverLoginToken(token: String): Boolean {"
delivery_replacement = r'''    // EXP38_ACK_DRIVEN_TOKEN_DELIVERY: scheduling evaluateJavascript is not
    // authentication success. Keep one idempotent delivery transaction in MAIN
    // until LoginOperationW publishes SUCCESS for this exact OAuth token.
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
                  var token = $jsToken;
                  var data = $jsPayload;
                  var existing = window.__ggqExp38LoginDelivery;
                  if (existing && existing.token === token &&
                      !existing.cancelled && !existing.acked) {
                    return 'active';
                  }

                  var state = {
                    token: token,
                    data: data,
                    cancelled: false,
                    acked: false,
                    expiresAt: Date.now() + 120000,
                    nextDispatchAt: 0
                  };
                  window.__ggqExp38LoginDelivery = state;

                  function dispatchToken() {
                    try {
                      window.dispatchEvent(new MessageEvent('message', {
                        data: state.data,
                        origin: 'https://www.geogebra.org'
                      }));
                    } catch (e) {
                      try {
                        var event = document.createEvent('MessageEvent');
                        event.initMessageEvent(
                          'message', false, false, state.data,
                          'https://www.geogebra.org', '', window, null
                        );
                        window.dispatchEvent(event);
                      } catch (_) {}
                    }
                  }

                  function acknowledgeSuccess() {
                    if (state.acked) return;
                    state.acked = true;
                    try {
                      if (window.QuestBridge &&
                          typeof window.QuestBridge.loginTokenAck === 'function') {
                        window.QuestBridge.loginTokenAck(state.token);
                      }
                    } catch (_) {}
                  }

                  function tick() {
                    if (window.__ggqExp38LoginDelivery !== state ||
                        state.cancelled || state.acked) return;

                    if (Date.now() >= state.expiresAt) {
                      // Popup-owned native delivery will install a fresh state;
                      // a one-shot restore will stop instead of retrying forever.
                      state.cancelled = true;
                      return;
                    }

                    if (window.__ggqLoginSuccessToken === state.token) {
                      acknowledgeSuccess();
                      return;
                    }

                    var ready = window.__ggqLoginReady === true;
                    var now = Date.now();
                    if (ready && now >= state.nextDispatchAt) {
                      // A prior success marker for the same token must not ACK a
                      // newly created transaction before its own dispatch.
                      try { window.__ggqLoginSuccessToken = null; } catch (_) {}
                      state.nextDispatchAt = now + 8000;
                      dispatchToken();
                    }
                    window.setTimeout(tick, ready ? 250 : 100);
                  }

                  tick();
                  return 'started';
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }

    fun cancelLoginTokenDelivery(token: String) {
        val main = mainWebView.get() ?: return
        if (token.isBlank()) return
        val jsToken = JSONObject.quote(token)
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var state = window.__ggqExp38LoginDelivery;
                  if (state && state.token === $jsToken) {
                    state.cancelled = true;
                    window.__ggqExp38LoginDelivery = null;
                  }
                })();
                """.trimIndent(),
                null,
            )
        }
    }'''
text = replace_function(text, delivery_signature, delivery_replacement)


# ---------------------------------------------------------------------------
# 2. A real popup OAuth token is retried natively until SUCCESS closes the
# popup.  The token is not considered delivered merely because JS was queued.
# ---------------------------------------------------------------------------
submit_signature = "    private fun submitPopupOAuthToken(webView: WebView, token: String) {"
submit_replacement = r'''    // EXP38_POPUP_TOKEN_RETRY_UNTIL_ACK
    fun submitPopupOAuthToken(webView: WebView, token: String) {
        if (!isRegisteredPopup(webView) || !looksLikeOAuthToken(token)) return

        var startLoop = false
        synchronized(exp34PopupTokens) {
            if (exp34PopupTokens[webView] != token) {
                exp34PopupTokens[webView] = token
                startLoop = true
            }
        }
        armLoginAck(webView, token)
        if (!startLoop) return

        android.util.Log.i(
            "GGQ-LOGIN",
            "Exp38 OAuth token observed; starting delivery until SUCCESS ACK",
        )

        fun deliverUntilAck() {
            if (!isRegisteredPopup(webView)) return
            val current = synchronized(exp34PopupTokens) {
                exp34PopupTokens[webView]
            }
            if (current != token) return

            armLoginAck(webView, token)
            deliverLoginToken(token)
            webView.postDelayed({ deliverUntilAck() }, 1500L)
        }
        webView.post { deliverUntilAck() }
    }'''
text = replace_function(text, submit_signature, submit_replacement)


# ---------------------------------------------------------------------------
# 3. Observe WebStorage for the popup's entire registered lifetime.  There is no
# 60-second attempt counter; closing/unregistering the popup is the stop signal.
# ---------------------------------------------------------------------------
probe_signature = "    fun startPopupOAuthTokenProbe(webView: WebView) {"
probe_replacement = r'''    // EXP38_LIFETIME_OAUTH_PROBE
    fun startPopupOAuthTokenProbe(webView: WebView) {
        synchronized(exp34PopupProbeStarted) {
            if (exp34PopupProbeStarted[webView] == true) return
            exp34PopupProbeStarted[webView] = true
        }

        fun probeWhileRegistered() {
            if (!isRegisteredPopup(webView)) return
            probePopupOAuthToken(webView)
            webView.postDelayed({ probeWhileRegistered() }, 500L)
        }
        webView.post { probeWhileRegistered() }
    }'''
text = replace_function(text, probe_signature, probe_replacement)


# ---------------------------------------------------------------------------
# 4. The trusted callback path joins the same retry/ACK transaction instead of
# making one fire-and-forget delivery attempt.
# ---------------------------------------------------------------------------
callback_signature = "private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {"
callback_replacement = r'''private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {
    if (!isTrustedGeoGebraCallback(uri)) return false

    // EXP17_OPENFROMGGT_CALLBACK remains unchanged.
    val openUrl = callbackParameter(uri, "url")
    if (openUrl != null) {
        if (!GeoGebraWebNavigation.deliverOpenFromGgt(openUrl)) return false
        if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
            view.post { GeoGebraWebNavigation.closePopup(view) }
        }
        return true
    }

    val token = callbackParameter(uri, "token")
        ?: callbackParameter(uri, "msg")
        ?: callbackParameter(uri, "access_token")
        ?: return false

    // EXP38_TRUSTED_CALLBACK_RETRY: a popup callback owns a retry transaction
    // until local LoginOperationW returns SUCCESS for this exact token.
    if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
        GeoGebraWebNavigation.submitPopupOAuthToken(view, token)
        return true
    }
    return GeoGebraWebNavigation.deliverLoginToken(token)
}'''
text = replace_function(text, callback_signature, callback_replacement)


# ---------------------------------------------------------------------------
# 5. Explicit popup cancellation stops any pending MAIN retry.  SUCCESS already
# marks the JS transaction ACKed before calling the native bridge.
# ---------------------------------------------------------------------------
close_signature = "    fun closePopup(webView: WebView) {"
close_replacement = r'''    fun closePopup(webView: WebView) {
        val cancelledToken = synchronized(pendingLoginAckPopups) {
            pendingLoginAckPopups.remove(webView)
        }
        synchronized(exp34PopupTokens) {
            exp34PopupTokens.remove(webView)
        }
        if (!cancelledToken.isNullOrBlank()) {
            android.util.Log.i("GGQ-LOGIN", "Exp38 pending login cancelled with popup")
            cancelLoginTokenDelivery(cancelledToken)
        }
        unregisterPopup(webView)
        (webView.parent as? ViewGroup)?.removeView(webView)
        try {
            webView.stopLoading()
            webView.removeJavascriptInterface("QuestBridge")
            webView.destroy()
        } catch (_: Throwable) {
        }
    }'''
text = replace_function(text, close_signature, close_replacement)


for required in (
    "EXP38_ACK_DRIVEN_TOKEN_DELIVERY",
    "__ggqExp38LoginDelivery",
    "state.nextDispatchAt = now + 8000",
    "expiresAt: Date.now() + 120000",
    "EXP38_POPUP_TOKEN_RETRY_UNTIL_ACK",
    "deliverUntilAck()",
    "EXP38_LIFETIME_OAUTH_PROBE",
    "probeWhileRegistered()",
    "EXP38_TRUSTED_CALLBACK_RETRY",
    "submitPopupOAuthToken(view, token)",
    "saveVerifiedOAuthToken(token)",
    "EXP34_NO_SSID_AUTH",
    "EXP35_LOGIN_IME_NEXT_GUARD",
    "EXP35_RIGHT_THUMB_ZOOM_BRIDGE",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in text:
        raise RuntimeError(f"exp38 final requirement missing: {required}")

for forbidden in (
    "if (attempts < 240)",
    "exp34PopupTokens.remove(webView)\n            }\n        }",
    "deliverLoginCookie(",
    'put("action", "logincookie")',
):
    if forbidden in text:
        raise RuntimeError(f"exp38 forbidden login residue present: {forbidden}")

path.write_text(text, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "login_retry=exp38 popup-lifetime OAuth probe; trusted callback and "
        "WebStorage token retry until exact local SUCCESS ACK\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp38 acknowledgement-driven OAuth retry installed")
