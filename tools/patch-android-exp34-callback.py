#!/usr/bin/env python3
"""Exp34 callback hardening.

Android WebView does not guarantee that every redirect is surfaced through
shouldOverrideUrlLoading. GeoGebra's ggtcallback.html contains the REAL OAuth
`token` query parameter and normally forwards it with window.opener.postMessage.
Catch that same trusted callback URL from onPageStarted and onPageFinished too.

No SSID handling and no XR/local-file behavior is changed.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp34-callback.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

for required in (
    "EXP34_TOKEN_FIRST_SESSION_OWNER",
    "EXP34_NO_SSID_AUTH",
    "EXP20_REMOTE_ESCAPE_FALLBACK",
    "private fun handleGeoGebraLoginCallback(view: WebView, uri: Uri): Boolean {",
):
    if required not in text:
        raise RuntimeError(f"exp34 callback baseline missing: {required}")

if "EXP34_CALLBACK_LIFECYCLE_FALLBACK" not in text:
    started = '''                super.onPageStarted(view, url, favicon)
                if (registerAsMain) {
'''
    started_new = '''                super.onPageStarted(view, url, favicon)
                // EXP34_CALLBACK_LIFECYCLE_FALLBACK: redirects can bypass
                // shouldOverrideUrlLoading on some WebView paths. ggtcallback
                // itself carries the real OAuth token, so catch it here too.
                if (!registerAsMain) {
                    val callbackUri = try { Uri.parse(url) } catch (_: Throwable) { null }
                    if (callbackUri != null && handleGeoGebraLoginCallback(view, callbackUri)) {
                        view.stopLoading()
                        return
                    }
                }
                if (registerAsMain) {
'''
    if started not in text:
        raise RuntimeError("exp34 callback onPageStarted anchor not found")
    text = text.replace(started, started_new, 1)

    finished = '''                super.onPageFinished(view, url)
'''
    finished_new = '''                super.onPageFinished(view, url)
                if (!registerAsMain) {
                    val callbackUri = try { Uri.parse(url) } catch (_: Throwable) { null }
                    if (callbackUri != null && handleGeoGebraLoginCallback(view, callbackUri)) {
                        return
                    }
                }
'''
    if finished not in text:
        raise RuntimeError("exp34 callback onPageFinished anchor not found")
    text = text.replace(finished, finished_new, 1)

for required in (
    "EXP34_CALLBACK_LIFECYCLE_FALLBACK",
    "handleGeoGebraLoginCallback(view, callbackUri)",
    "view.stopLoading()",
):
    if required not in text:
        raise RuntimeError(f"exp34 callback requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp34 trusted OAuth callback hardened across WebView lifecycle")
