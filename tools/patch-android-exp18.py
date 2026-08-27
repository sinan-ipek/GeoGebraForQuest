#!/usr/bin/env python3
"""Exp18: end the remote-popup lifecycle as soon as GeoGebra login succeeds.

Exp15/17 tried to depend on GeoGebra callback URLs. The Quest WebView flow can
instead remain on a normal GeoGebra web page after login, so those callbacks may
never be observed. Android's CookieManager still sees the authenticated GeoGebra
SSID session cookie. GeoGebra Web itself uses SSID as the token for passiveLogin.

When a registered popup finishes a page, inspect GeoGebra cookies. If SSID is
present, forward it through exp15's exact logintoken MessageEvent bridge to the
MAIN local patched AppW and close the popup immediately. OpenFileView then reacts
to the successful LoginEvent and loads the user's materials inside the local AppW.

If no SSID is visible, leave a tiny diagnostic banner in the popup with its URL
and SSID state; this gives direct runtime evidence without ADB if the flow still
fails on Quest.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp18.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

if "EXP18_POPUP_SSID_HANDOFF" in text:
    print("[GGQ] exp18 popup SSID handoff already present")
    raise SystemExit(0)

helper_anchor = '''private fun refreshImeConnection(view: View) {
'''
helpers = r'''private fun cookieValue(cookieHeader: String?, name: String): String? {
    if (cookieHeader.isNullOrBlank()) return null
    return cookieHeader.split(';')
        .map { it.trim() }
        .mapNotNull { part ->
            val pieces = part.split('=', limit = 2)
            if (pieces.size == 2 && pieces[0] == name && pieces[1].isNotBlank()) {
                pieces[1]
            } else {
                null
            }
        }
        .firstOrNull()
}

// EXP18_POPUP_SSID_HANDOFF: GeoGebra Web passiveLogin() itself treats SSID as
// its login token. Read it natively because the MAIN appassets origin cannot
// access geogebra.org cookies directly.
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

private fun injectPopupLoginDiagnostic(view: WebView, url: String, hasSession: Boolean) {
    val text = "GGQ POPUP | SSID " + (if (hasSession) "YES" else "NO") + " | " + url
    val quoted = JSONObject.quote(text.take(220))
    view.evaluateJavascript(
        """
        (function () {
          try {
            var id = 'ggq-popup-login-diagnostic';
            var bar = document.getElementById(id);
            if (!bar) {
              bar = document.createElement('div');
              bar.id = id;
              bar.style.cssText =
                'position:fixed;left:0;top:0;right:0;z-index:2147483647;' +
                'background:rgba(120,0,0,.86);color:white;font:11px monospace;' +
                'padding:3px 6px;white-space:nowrap;overflow:hidden;' +
                'text-overflow:ellipsis;pointer-events:none;';
              (document.body || document.documentElement).appendChild(bar);
            }
            bar.textContent = $quoted;
          } catch (_) {}
        })();
        """.trimIndent(),
        null,
    )
}

private fun completePopupLoginFromCookie(view: WebView, url: String): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false

    val token = popupGeoGebraSessionToken(view)
    injectPopupLoginDiagnostic(view, url, token != null)
    if (token.isNullOrBlank()) return false
    if (!GeoGebraWebNavigation.deliverLoginToken(token)) return false

    // Let the MessageEvent reach LoginOperationW before destroying the popup.
    view.postDelayed({
        if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
            GeoGebraWebNavigation.closePopup(view)
        }
    }, 250L)
    return true
}

''' + helper_anchor

if helper_anchor not in text:
    raise RuntimeError("exp18 refreshImeConnection anchor not found")
text = text.replace(helper_anchor, helpers, 1)

page_anchor = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
'''
page_replacement = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                if (completePopupLoginFromCookie(view, url)) {
                    return
                }
'''
if page_anchor not in text:
    raise RuntimeError("exp18 onPageFinished anchor not found")
text = text.replace(page_anchor, page_replacement, 1)

for required in (
    "EXP18_POPUP_SSID_HANDOFF",
    'cookieValue(cookies.getCookie(url), "SSID")',
    "completePopupLoginFromCookie(view, url)",
    "GeoGebraWebNavigation.deliverLoginToken(token)",
    "GeoGebraWebNavigation.closePopup(view)",
    "ggq-popup-login-diagnostic",
    "GGQ POPUP | SSID ",
    '(if (hasSession) "YES" else "NO")',
):
    if required not in text:
        raise RuntimeError(f"exp18 requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp18 SSID session handoff installed; authenticated popup returns to MAIN local AppW")
