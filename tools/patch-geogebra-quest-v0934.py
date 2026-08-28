#!/usr/bin/env python3
"""Exp33: distinguish GeoGebra SSID cookie authentication from OAuth token login.

GeoGebra's own authentication API has two different credential paths:
- OAuth/login token -> {"token": ...}
- GeoGebra SSID cookie -> {"cookie": ...}

The Android Exp18+ fallback reads the remote SSID cookie. Historically we fed that
value through the existing `logintoken` MessageEvent, which makes LoginOperationW
call performTokenLogin(cookie, false). That incorrectly sends an SSID cookie in the
API's `token` field. A failed authorization can then clear the real stored OAuth
login token, causing spontaneous logout and stale/featured material lists.

This source patch adds a separate `logincookie` MessageEvent action. It follows
GeoGebra's native passive-login semantics exactly by constructing
GeoGebraTubeUser(null, cookie), so GeoGebraTubeAPI sends the credential as a
cookie. On success the API response supplies the real OAuth token and the existing
AuthenticationModelW persists that token in localStorage.

The existing Exp22 READY/SUCCESS ACK remains unchanged: the opaque credential
string is only used as the request correlation marker for the native popup bridge.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0934.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
path = root / (
    "source/web/web/src/main/java/org/geogebra/web/shared/ggtapi/"
    "LoginOperationW.java"
)
text = path.read_text(encoding="utf-8")

marker = "GGQ_EXP33_COOKIE_AUTH_SEMANTICS"
if marker in text:
    print("[GGQ] exp33 cookie authentication semantics already present")
    raise SystemExit(0)

if "GGQ_EXP22_LOGIN_READY_ACK" not in text:
    raise RuntimeError("exp33 requires exp22 login READY/SUCCESS patch first")

old = '''\t\t\t\t\tif ("logintoken".equals(action)) {\n\t\t\t\t\t\tLog.debug("Login token sent via message");\n\t\t\t\t\t\tggqPendingLoginToken = (String) dataObject.get("msg");\n\t\t\t\t\t\tperformTokenLogin(ggqPendingLoginToken, false);\n\t\t\t\t\t}\n'''
new = '''\t\t\t\t\tif ("logintoken".equals(action)) {\n\t\t\t\t\t\tLog.debug("Login token sent via message");\n\t\t\t\t\t\tggqPendingLoginToken = (String) dataObject.get("msg");\n\t\t\t\t\t\tperformTokenLogin(ggqPendingLoginToken, false);\n\t\t\t\t\t} else if ("logincookie".equals(action)) {\n\t\t\t\t\t\t// GGQ_EXP33_COOKIE_AUTH_SEMANTICS: SSID is a cookie, not an\n\t\t\t\t\t\t// OAuth token. Follow LoginOperationW.passiveLogin() semantics\n\t\t\t\t\t\t// so GeoGebraTubeAPI emits {cookie: ...}; successful userinfo\n\t\t\t\t\t\t// returns the real token which AuthenticationModelW persists.\n\t\t\t\t\t\tLog.debug("Login cookie sent via Quest bridge");\n\t\t\t\t\t\tggqPendingLoginToken = (String) dataObject.get("msg");\n\t\t\t\t\t\tdoPerformTokenLogin(\n\t\t\t\t\t\t\t\tnew GeoGebraTubeUser(null, ggqPendingLoginToken), false);\n\t\t\t\t\t}\n'''

if old not in text:
    raise RuntimeError("exp33 could not locate exp22 logintoken message handler")
text = text.replace(old, new, 1)

for required in (
    marker,
    '"logincookie".equals(action)',
    "new GeoGebraTubeUser(null, ggqPendingLoginToken)",
    "performTokenLogin(ggqPendingLoginToken, false)",
    '"__ggqLoginReady"',
    '"__ggqLoginSuccessToken"',
):
    if required not in text:
        raise RuntimeError(f"exp33 source requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp33 separate SSID-cookie authentication installed")
