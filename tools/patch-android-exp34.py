#!/usr/bin/env python3
"""Exp34: token-first GeoGebra login with verified native session persistence.

Runtime baseline:
- Keep Exp25 MAIN/popup navigation protection.
- Keep Exp27 local-file/XR cold-process behavior exactly unchanged.

Login policy:
- SSID is NEVER used as an authentication credential.
- Trusted ggtcallback OAuth tokens remain the primary login path.
- If GeoGebra's login service does not expose the callback to Android, the login
  popup is allowed to finish its post-login GeoGebra redirect while INVISIBLE.
  Native code then reads the REAL OAuth token from that remote GeoGebra origin's
  localStorage/sessionStorage key `token` and sends only that token to MAIN.
- MAIN closes the popup only after Exp22's local LoginOperationW SUCCESS ACK.
- A token is persisted in Android SharedPreferences only AFTER that SUCCESS ACK.
  Fresh MAIN processes can restore the verified token if WebView localStorage was
  lost, while normal GeoGebra localStorage remains the first persistence layer.

This patch intentionally does not change the Exp27 local-file process kill/relaunch.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp34.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

for required in (
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP23_POPUP_APP_SHELL_QUARANTINE",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
    "fun deliverLoginToken(token: String): Boolean",
    "private fun popupGeoGebraSessionToken(view: WebView): String?",
):
    if required not in text:
        raise RuntimeError(f"exp34 baseline requirement missing: {required}")


def replace_function(source: str, signature: str, replacement: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"exp34 function not found: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise RuntimeError(f"exp34 opening brace not found: {signature}")
    depth = 0
    i = brace
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return source[:start] + replacement + source[end:]
        i += 1
    raise RuntimeError(f"exp34 closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# 1. Token-first helpers inside GeoGebraWebNavigation.
# ---------------------------------------------------------------------------
if "EXP34_TOKEN_FIRST_SESSION_OWNER" not in text:
    anchor = "    // EXP17_OPENFROMGGT_HANDOFF:"
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError("exp34 Exp17 navigation anchor not found")

    helper = r'''    // EXP34_TOKEN_FIRST_SESSION_OWNER: only a real OAuth token may own the
    // local AppW session. SSID cookies are intentionally ignored by authentication.
    private const val EXP34_AUTH_PREFS = "ggq_verified_auth"
    private const val EXP34_AUTH_TOKEN = "oauth_token"
    private val exp34PopupTokens = java.util.WeakHashMap<WebView, String>()
    private val exp34PopupProbeStarted = java.util.WeakHashMap<WebView, Boolean>()
    private val exp34MainRestoreStarted = java.util.WeakHashMap<WebView, Boolean>()

    private fun decodeJavascriptString(raw: String?): String? {
        if (raw.isNullOrBlank() || raw == "null" || raw == "undefined") return null
        return try {
            JSONObject("{\"value\":$raw}").optString("value")
                .takeIf { it.isNotBlank() && it != "null" }
        } catch (_: Throwable) {
            null
        }
    }

    private fun looksLikeOAuthToken(token: String): Boolean =
        token.length >= 16 && token.length <= 4096 && token.none { it.isWhitespace() }

    private fun saveVerifiedOAuthToken(token: String) {
        if (!looksLikeOAuthToken(token)) return
        val context = mainWebView.get()?.context?.applicationContext ?: return
        context.getSharedPreferences(EXP34_AUTH_PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(EXP34_AUTH_TOKEN, token)
            .apply()
    }

    private fun verifiedOAuthToken(): String? {
        val context = mainWebView.get()?.context?.applicationContext ?: return null
        return context.getSharedPreferences(EXP34_AUTH_PREFS, Context.MODE_PRIVATE)
            .getString(EXP34_AUTH_TOKEN, null)
            ?.takeIf { looksLikeOAuthToken(it) }
    }

    private fun submitPopupOAuthToken(webView: WebView, token: String) {
        if (!isRegisteredPopup(webView) || !looksLikeOAuthToken(token)) return
        synchronized(exp34PopupTokens) {
            if (exp34PopupTokens[webView] == token) return
            exp34PopupTokens[webView] = token
        }
        armLoginAck(webView, token)
        if (!deliverLoginToken(token)) {
            synchronized(exp34PopupTokens) {
                exp34PopupTokens.remove(webView)
            }
        }
    }

    // EXP34_REMOTE_OAUTH_STORAGE_PROBE: official GeoGebra Web stores its real
    // OAuth token in BrowserStorage LOCAL/SESSION under key `token`. Read that
    // exact value from the authenticated remote popup; never reinterpret SSID.
    fun probePopupOAuthToken(webView: WebView) {
        if (!isRegisteredPopup(webView)) return
        val uri = try { Uri.parse(webView.url.orEmpty()) } catch (_: Throwable) { null }
        val host = uri?.host.orEmpty().lowercase()
        if (host != "geogebra.org" && !host.endsWith(".geogebra.org")) return

        webView.evaluateJavascript(
            """
            (function () {
              try {
                return window.localStorage.getItem('token') ||
                       window.sessionStorage.getItem('token') || '';
              } catch (_) {
                return '';
              }
            })();
            """.trimIndent(),
        ) { raw ->
            val token = decodeJavascriptString(raw) ?: return@evaluateJavascript
            submitPopupOAuthToken(webView, token)
        }
    }

    fun startPopupOAuthTokenProbe(webView: WebView) {
        synchronized(exp34PopupProbeStarted) {
            if (exp34PopupProbeStarted[webView] == true) return
            exp34PopupProbeStarted[webView] = true
        }

        var attempts = 0
        fun probeAgain() {
            if (!isRegisteredPopup(webView)) return
            attempts++
            probePopupOAuthToken(webView)
            if (attempts < 240) {
                webView.postDelayed({ probeAgain() }, 250L)
            }
        }
        webView.post { probeAgain() }
    }

    // EXP34_VERIFIED_TOKEN_RESTORE: SharedPreferences is only a second copy of
    // a token already proven by local GeoGebra SUCCESS. If WebView localStorage
    // still has a token, GeoGebra's own automatic performTokenLogin() remains in
    // charge; native restore is used only when WebView storage has no token.
    fun restoreVerifiedLoginTokenIfNeeded() {
        val main = mainWebView.get() ?: return
        synchronized(exp34MainRestoreStarted) {
            if (exp34MainRestoreStarted[main] == true) return
            exp34MainRestoreStarted[main] = true
        }
        val verified = verifiedOAuthToken() ?: return

        main.postDelayed({
            if (mainWebView.get() !== main) return@postDelayed
            main.evaluateJavascript(
                """
                (function () {
                  try {
                    return window.localStorage.getItem('token') ||
                           window.sessionStorage.getItem('token') || '';
                  } catch (_) {
                    return '';
                  }
                })();
                """.trimIndent(),
            ) { raw ->
                val webToken = decodeJavascriptString(raw)
                if (webToken.isNullOrBlank()) {
                    deliverLoginToken(verified)
                }
            }
        }, 900L)
    }

'''
    text = text[:pos] + helper + text[pos:]


# ---------------------------------------------------------------------------
# 2. Persist only SUCCESS-verified OAuth tokens. Exp22 popup ACK behavior stays.
# ---------------------------------------------------------------------------
ack_signature = "    fun onLoginTokenAck(token: String) {"
ack_replacement = r'''    fun onLoginTokenAck(token: String) {
        if (token.isBlank()) return

        // EXP34_VERIFIED_TOKEN_STORE: this callback is reached only after the
        // bundled local LoginOperationW reports a real successful login.
        saveVerifiedOAuthToken(token)

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
    }'''
text = replace_function(text, ack_signature, ack_replacement)


# ---------------------------------------------------------------------------
# 3. Exp18 SSID path becomes observation-free/no-auth. It merely asks the token
# probe to inspect remote Web storage for a real OAuth token.
# ---------------------------------------------------------------------------
cookie_signature = "private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {"
cookie_replacement = r'''private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    // EXP34_NO_SSID_AUTH: SSID is deliberately ignored. The URL argument is kept
    // only because older onPageFinished call sites use this helper signature.
    GeoGebraWebNavigation.probePopupOAuthToken(view)
    return false
}'''
text = replace_function(text, cookie_signature, cookie_replacement)


# ---------------------------------------------------------------------------
# 4. Exp23 app-shell quarantine stays visually strict, but no longer destroys the
# hidden transport after 350ms. The hidden page may finish its official redirect
# so its real OAuth token can be read from remote localStorage/sessionStorage.
# ---------------------------------------------------------------------------
quarantine_signature = "private fun quarantineRemoteGeoGebraAppPopup(view: WebView, url: String) {"
quarantine_replacement = r'''private fun quarantineRemoteGeoGebraAppPopup(view: WebView, url: String) {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return
    synchronized(exp23QuarantinedPopups) {
        exp23QuarantinedPopups[view] = true
    }

    // EXP34_HIDDEN_LOGIN_TRANSPORT: remote GeoGebra application pages may exist
    // only as an invisible authentication transport. They can never cover MAIN.
    view.visibility = View.INVISIBLE

    val uri = try { Uri.parse(url) } catch (_: Throwable) { null }
    if (uri != null && isGeoGebraMaterialUri(uri)) {
        GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())
        view.post { GeoGebraWebNavigation.closePopup(view) }
        return
    }

    GeoGebraWebNavigation.startPopupOAuthTokenProbe(view)
}'''
text = replace_function(text, quarantine_signature, quarantine_replacement)


# ---------------------------------------------------------------------------
# 5. Exp25 strict popup guard: materials are still consumed. Other forbidden
# GeoGebra popup routes are hidden but allowed to load as token-extraction
# transport. MAIN's canonical remote guard remains untouched.
# ---------------------------------------------------------------------------
close_signature = "private fun closeForbiddenGeoGebraPopup(view: WebView, uri: Uri): Boolean {"
close_replacement = r'''private fun closeForbiddenGeoGebraPopup(view: WebView, uri: Uri): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false
    if (!isForbiddenGeoGebraPopupRoute(uri)) return false

    if (isGeoGebraMaterialUri(uri)) {
        GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())
        view.visibility = View.INVISIBLE
        view.post { GeoGebraWebNavigation.closePopup(view) }
        return true
    }

    // EXP34_HIDDEN_FORBIDDEN_REDIRECT: do not let a post-login redirect become
    // visible, but do let it load in this registered popup so the REAL OAuth
    // token can be recovered from GeoGebra's own Web storage. Returning false
    // allows only this popup navigation; MAIN remains protected by Exp20.
    view.visibility = View.INVISIBLE
    GeoGebraWebNavigation.startPopupOAuthTokenProbe(view)
    return false
}'''
text = replace_function(text, close_signature, close_replacement)


# ---------------------------------------------------------------------------
# 6. Start the OAuth token probe as soon as a login popup exists.
# ---------------------------------------------------------------------------
popup_anchor = '''        GeoGebraWebNavigation.registerPopup(popup)
        popup.post { refreshImeConnection(popup) }
'''
popup_replacement = '''        GeoGebraWebNavigation.registerPopup(popup)
        GeoGebraWebNavigation.startPopupOAuthTokenProbe(popup)
        popup.post { refreshImeConnection(popup) }
'''
if popup_anchor in text:
    text = text.replace(popup_anchor, popup_replacement, 1)
elif "GeoGebraWebNavigation.startPopupOAuthTokenProbe(popup)" not in text:
    raise RuntimeError("exp34 popup registration anchor not found")


# ---------------------------------------------------------------------------
# 7. Fresh MAIN after Exp27 cold restart restores the verified token only if
# WebView localStorage has lost it.
# ---------------------------------------------------------------------------
restore_anchor = "                    GeoGebraWebNavigation.openPendingColdLocalFileIfAny()\n"
restore_replacement = restore_anchor + "                    GeoGebraWebNavigation.restoreVerifiedLoginTokenIfNeeded()\n"
if restore_anchor in text and "GeoGebraWebNavigation.restoreVerifiedLoginTokenIfNeeded()" not in text:
    text = text.replace(restore_anchor, restore_replacement, 1)
elif "GeoGebraWebNavigation.restoreVerifiedLoginTokenIfNeeded()" not in text:
    raise RuntimeError("exp34 MAIN onPageFinished restore anchor not found")


# ---------------------------------------------------------------------------
# 8. Safety verification.
# ---------------------------------------------------------------------------
for required in (
    "EXP34_TOKEN_FIRST_SESSION_OWNER",
    "EXP34_REMOTE_OAUTH_STORAGE_PROBE",
    "window.localStorage.getItem('token')",
    "window.sessionStorage.getItem('token')",
    "EXP34_VERIFIED_TOKEN_STORE",
    "EXP34_VERIFIED_TOKEN_RESTORE",
    "EXP34_NO_SSID_AUTH",
    "EXP34_HIDDEN_LOGIN_TRANSPORT",
    "EXP34_HIDDEN_FORBIDDEN_REDIRECT",
    "startPopupOAuthTokenProbe(popup)",
    "restoreVerifiedLoginTokenIfNeeded()",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in text:
        raise RuntimeError(f"exp34 final requirement missing: {required}")

# Real callback must remain the primary token path.
callback_pos = text.find("private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {")
if callback_pos < 0:
    raise RuntimeError("exp34 trusted callback missing")
callback_probe = text[callback_pos:callback_pos + 2400]
if "GeoGebraWebNavigation.deliverLoginToken(token)" not in callback_probe:
    raise RuntimeError("exp34 trusted callback no longer delivers OAuth token")

# No SSID-derived value may reach token authentication anywhere.
for match in __import__('re').finditer(r'popupGeoGebraSessionToken\(view\)', text):
    probe = text[match.start():match.start() + 900]
    if "deliverLoginToken(" in probe:
        raise RuntimeError("exp34 SSID is still routed to token authentication")

for forbidden in (
    "deliverLoginCookie(",
    'put("action", "logincookie")',
    "EXP33_COOKIE_LOGIN_DELIVERY",
    "EXP33_COOKIE_EDGE_ONLY",
    "EXP33_POPUP_COOKIE_BASELINE",
):
    if forbidden in text:
        raise RuntimeError(f"exp34 cookie-auth residue remains: {forbidden}")

path.write_text(text, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "login_session=exp34 token-first single session owner; SSID never authenticates; "
        "trusted callback or remote GeoGebra WebStorage OAuth token -> local Exp22 SUCCESS ACK\n"
        "login_persistence=exp34 OAuth token saved natively only after local SUCCESS ACK; "
        "fresh MAIN restores only when WebView token storage is absent\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp34 token-first login + verified session persistence installed")
