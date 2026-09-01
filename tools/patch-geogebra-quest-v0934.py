#!/usr/bin/env python3
"""Exp34 source gate: token-first login and callback-token persistence.

This historical filename is still called by build-geogebra-quest.sh, but Exp34
no longer installs the Exp33 `logincookie` branch. The only authentication
credential is GeoGebra's real OAuth token.

GeoGebra's own ggtcallback.html receives `?token=...` and normally forwards it to
window.opener with postMessage. Android WebView has occasionally lost that opener
message. Exp34 additionally writes that SAME real callback token to same-origin
localStorage before postMessage. This is persistence/fallback only; SSID is never
converted into a token.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0934.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
login_path = root / (
    "source/web/web/src/main/java/org/geogebra/web/shared/ggtapi/"
    "LoginOperationW.java"
)
callback_path = root / (
    "source/web/web/src/main/resources/org/geogebra/web/pub/html/ggtcallback.html"
)

login = login_path.read_text(encoding="utf-8")

if "GGQ_EXP22_LOGIN_READY_ACK" not in login:
    raise RuntimeError("exp34 requires Exp22 login READY/SUCCESS handshake")

for forbidden in (
    '"logincookie".equals(action)',
    "GGQ_EXP33_COOKIE_AUTH_SEMANTICS",
    "new GeoGebraTubeUser(null, ggqPendingLoginToken)",
):
    if forbidden in login:
        raise RuntimeError(f"exp34 cookie-auth source residue present: {forbidden}")

if '"logintoken".equals(action)' not in login:
    raise RuntimeError("exp34 OAuth token message path missing")
if "performTokenLogin(ggqPendingLoginToken, false)" not in login:
    raise RuntimeError("exp34 Exp22 token login path missing")

callback = callback_path.read_text(encoding="utf-8")
marker = "GGQ_EXP34_CALLBACK_TOKEN_STORAGE"
if marker not in callback:
    old = '''    function sendToken() {
        window.opener.postMessage(JSON.stringify({action: "logintoken", msg: getURLParameter("token")}), "*");
    }
'''
    new = '''    function sendToken() {
        var token = getURLParameter("token");
        // GGQ_EXP34_CALLBACK_TOKEN_STORAGE: persist the REAL OAuth token from
        // the callback URL before opener messaging. This is not an SSID cookie.
        try {
            if (token !== null && token !== "") {
                window.localStorage.setItem("token", token);
            }
        } catch (e) {}
        window.opener.postMessage(JSON.stringify({action: "logintoken", msg: token}), "*");
    }
'''
    if old not in callback:
        raise RuntimeError("exp34 ggtcallback sendToken anchor not found")
    callback = callback.replace(old, new, 1)

for required in (
    marker,
    'getURLParameter("token")',
    'window.localStorage.setItem("token", token)',
    'action: "logintoken"',
):
    if required not in callback:
        raise RuntimeError(f"exp34 callback requirement missing: {required}")

callback_path.write_text(callback, encoding="utf-8")
print("[GGQ] exp34 token-first source gate + real callback-token persistence installed")
