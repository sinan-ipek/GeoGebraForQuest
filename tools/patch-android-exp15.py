#!/usr/bin/env python3
"""Exp15: keep GeoGebra cloud login/material flow inside the patched local app.

Android WebView popups do not reliably complete GeoGebra's popup -> opener
postMessage lifecycle. Previously a local ggtcallback URL was redirected to the
official remote callback page; if opener messaging failed, that popup stayed
alive and the user continued inside an unpatched official GeoGebra web app.

Intercept the trusted GeoGebra callback in Android, forward its token directly
to the MAIN local WebView in exactly the JSON MessageEvent format expected by
LoginOperationW, then close the popup. The native local BrowseView consequently
loads selected cloud materials through the same patched AppW/ArchiveLoader.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp15.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

# Remove the old remote-callback redirect constant. The bundled local callback
# remains a fallback, but normal Quest flow is handled natively before it loads.
old_constant = '''private const val REMOTE_LOGIN_CALLBACK_URL =
    "https://www.geogebra.org/apps/latest/web3d/html/ggtcallback.html"
'''
text = text.replace(old_constant, "", 1)

# Add direct token delivery to the registered MAIN local WebView.
if "EXP15_LOCAL_LOGIN_TOKEN_BRIDGE" not in text:
    nav_anchor = '''    fun closePopup(webView: WebView) {
        unregisterPopup(webView)
        (webView.parent as? ViewGroup)?.removeView(webView)
        try {
            webView.stopLoading()
            webView.removeJavascriptInterface("QuestBridge")
            webView.destroy()
        } catch (_: Throwable) {
        }
    }
'''
    nav_insert = nav_anchor + r'''

    fun isRegisteredPopup(webView: WebView): Boolean {
        cleanupPopups()
        return popupWebViews.any { it.get() === webView }
    }

    // EXP15_LOCAL_LOGIN_TOKEN_BRIDGE: bypass fragile popup window.opener messaging.
    fun deliverLoginToken(token: String): Boolean {
        val main = mainWebView.get() ?: return false
        if (token.isBlank()) return false
        val payload = JSONObject()
            .put("action", "logintoken")
            .put("msg", token)
            .toString()
        val jsPayload = JSONObject.quote(payload)
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var data = $jsPayload;
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
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }
'''
    if nav_anchor not in text:
        raise RuntimeError("exp15 navigation closePopup anchor not found")
    text = text.replace(nav_anchor, nav_insert, 1)

# Replace the old local->remote callback redirect with direct native forwarding.
old_redirect = '''private fun redirectLocalLoginCallback(view: WebView, uri: Uri): Boolean {
    val path = uri.path.orEmpty()
    if (
        !uri.host.equals(LOCAL_ASSET_HOST, ignoreCase = true) ||
        !path.endsWith("/ggtcallback.html")
    ) {
        return false
    }

    val remote = Uri.parse(REMOTE_LOGIN_CALLBACK_URL)
        .buildUpon()
        .encodedQuery(uri.encodedQuery)
        .build()
    view.loadUrl(remote.toString())
    return true
}
'''
new_callback = r'''private fun callbackParameter(uri: Uri, name: String): String? {
    uri.getQueryParameter(name)?.takeIf { it.isNotBlank() }?.let { return it }
    val fragment = uri.fragment.orEmpty()
    if (fragment.isBlank()) return null
    return fragment.split('&')
        .mapNotNull { part ->
            val pieces = part.split('=', limit = 2)
            if (pieces.size == 2 && pieces[0] == name) {
                Uri.decode(pieces[1])
            } else {
                null
            }
        }
        .firstOrNull { it.isNotBlank() }
}

private fun isTrustedGeoGebraCallback(uri: Uri): Boolean {
    val host = uri.host.orEmpty().lowercase()
    val trustedHost = host == LOCAL_ASSET_HOST ||
        host == "geogebra.org" || host.endsWith(".geogebra.org")
    return trustedHost && uri.path.orEmpty().endsWith("/ggtcallback.html")
}

// EXP15_LOCAL_LOGIN_CALLBACK: consume the OAuth callback in Android and feed the
// token to the still-running LOCAL patched GeoGebra window. Never turn the login
// popup into a second, unpatched GeoGebra application.
private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {
    if (!isTrustedGeoGebraCallback(uri)) return false

    val token = callbackParameter(uri, "token")
        ?: callbackParameter(uri, "msg")
        ?: callbackParameter(uri, "access_token")
        ?: return false // bundled callback page remains a safe fallback

    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false

    if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
        view.post { GeoGebraWebNavigation.closePopup(view) }
    }
    return true
}
'''
if old_redirect not in text:
    if "EXP15_LOCAL_LOGIN_CALLBACK" not in text:
        raise RuntimeError("exp15 old login callback redirect anchor not found")
else:
    text = text.replace(old_redirect, new_callback, 1)

text = text.replace(
    "): Boolean = redirectLocalLoginCallback(view, request.url)",
    "): Boolean = handleGeoGebraLoginCallback(view, request.url)",
)
text = text.replace(
    "redirectLocalLoginCallback(view, Uri.parse(url))",
    "handleGeoGebraLoginCallback(view, Uri.parse(url))",
)

# Build guards: the remote callback redirect and its independent-app escape hatch
# must not survive in the generated Android source.
for forbidden in (
    "REMOTE_LOGIN_CALLBACK_URL",
    "redirectLocalLoginCallback(",
    "view.loadUrl(remote.toString())",
):
    if forbidden in text:
        raise RuntimeError(f"exp15 remote-login escape residue must not exist: {forbidden}")

for required in (
    "EXP15_LOCAL_LOGIN_TOKEN_BRIDGE",
    "EXP15_LOCAL_LOGIN_CALLBACK",
    'put("action", "logintoken")',
    'put("msg", token)',
    "new MessageEvent('message'",
    "GeoGebraWebNavigation.closePopup(view)",
    "handleGeoGebraLoginCallback(view, request.url)",
):
    if required not in text:
        raise RuntimeError(f"exp15 login bridge missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp15 direct login-token bridge installed; popup cannot become an independent app")
