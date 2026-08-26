#!/usr/bin/env python3
"""Exp17: keep 'Open in app' inside the patched local GeoGebra WebView.

GeoGebra's ggtcallback.html carries TWO messages: logintoken and openfromggt.
Exp15 only intercepted the login token. When the account/material popup later
used ?url=... for 'Open in app', that callback was left to window.opener and the
popup could continue as an independent unpatched GeoGebra Classic instance.

Handle the url callback natively too: call ggbApplet.openFile(url) on the MAIN
local patched WebView, then close the popup. The exported openFile API routes to
GgbAPIW -> ArchiveLoader.processFileName(), so the construction is loaded by our
patched AppW and its Quest stereo renderer.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp17.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

if "EXP17_OPENFROMGGT_HANDOFF" in text:
    print("[GGQ] exp17 openfromggt handoff already present")
    raise SystemExit(0)

# Add a MAIN-WebView loader next to exp15's token bridge.
anchor = '''    fun handleBack(): Boolean {
'''
insert = r'''    // EXP17_OPENFROMGGT_HANDOFF: 'Open in app' must load the file in the
    // MAIN local patched AppW, never in the login/material popup WebView.
    fun deliverOpenFromGgt(url: String): Boolean {
        val main = mainWebView.get() ?: return false
        if (url.isBlank()) return false
        val jsUrl = JSONObject.quote(url)
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var url = $jsUrl;
                  var attempts = 0;

                  function closeBrowseLayer() {
                    try {
                      var target = document.activeElement || document.body;
                      target.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Escape', code: 'Escape', keyCode: 27, which: 27,
                        bubbles: true, cancelable: true
                      }));
                      target.dispatchEvent(new KeyboardEvent('keyup', {
                        key: 'Escape', code: 'Escape', keyCode: 27, which: 27,
                        bubbles: true, cancelable: true
                      }));
                    } catch (_) {}
                  }

                  function openInLocalApp() {
                    attempts++;
                    try {
                      if (window.ggbApplet && typeof window.ggbApplet.openFile === 'function') {
                        window.ggbApplet.openFile(url, function () {
                          closeBrowseLayer();
                        });
                        return true;
                      }
                    } catch (_) {}
                    return false;
                  }

                  if (!openInLocalApp()) {
                    var timer = window.setInterval(function () {
                      if (openInLocalApp() || attempts >= 80) {
                        window.clearInterval(timer);
                      }
                    }, 100);
                  }
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }

''' + anchor
if anchor not in text:
    raise RuntimeError("exp17 handleBack anchor not found")
text = text.replace(anchor, insert, 1)

# Exp15's callback only understands login tokens. Add GeoGebra's second official
# callback payload: ?url=... -> openfromggt.
callback_anchor = '''private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {
    if (!isTrustedGeoGebraCallback(uri)) return false

    val token = callbackParameter(uri, "token")
'''
callback_replacement = '''private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {
    if (!isTrustedGeoGebraCallback(uri)) return false

    // EXP17_OPENFROMGGT_CALLBACK: ggtcallback.html sends {action:"openfromggt"}
    // when it receives ?url=. Bypass fragile window.opener and load that URL in
    // the registered MAIN local patched GeoGebra app directly.
    val openUrl = callbackParameter(uri, "url")
    if (openUrl != null) {
        if (!GeoGebraWebNavigation.deliverOpenFromGgt(openUrl)) return false
        if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
            view.post { GeoGebraWebNavigation.closePopup(view) }
        }
        return true
    }

    val token = callbackParameter(uri, "token")
'''
if callback_anchor not in text:
    raise RuntimeError("exp17 exp15 callback anchor not found")
text = text.replace(callback_anchor, callback_replacement, 1)

for required in (
    "EXP17_OPENFROMGGT_HANDOFF",
    "EXP17_OPENFROMGGT_CALLBACK",
    "fun deliverOpenFromGgt(url: String): Boolean",
    'callbackParameter(uri, "url")',
    "GeoGebraWebNavigation.deliverOpenFromGgt(openUrl)",
    "window.ggbApplet.openFile(url",
    "GeoGebraWebNavigation.closePopup(view)",
):
    if required not in text:
        raise RuntimeError(f"exp17 requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp17 openfromggt URL handoff installed; account files return to MAIN patched AppW")
