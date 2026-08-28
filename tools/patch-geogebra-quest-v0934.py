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
import re
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

# Exp22 preserves the upstream indentation around this block, and that indentation
# has changed across pinned GeoGebra revisions / prior Quest patches. Match the
# semantic block instead of assuming a fixed number of tabs.
pattern = re.compile(
    r'(?P<indent>^[ \t]*)if \("logintoken"\.equals\(action\)\) \{\n'
    r'(?P<body>.*?performTokenLogin\(ggqPendingLoginToken, false\);\n)'
    r'(?P=indent)\}',
    re.MULTILINE | re.DOTALL,
)
match = pattern.search(text)
if match is None:
    # Keep CI failure diagnostic useful without leaking unrelated source.
    token_pos = text.find("performTokenLogin(ggqPendingLoginToken, false);")
    if token_pos < 0:
        raise RuntimeError("exp33 could not find exp22 token-login call")
    snippet = text[max(0, token_pos - 500): token_pos + 300]
    raise RuntimeError("exp33 could not locate enclosing logintoken block:\n" + snippet)

indent = match.group("indent")
body_indent = indent + "\t"
original = match.group(0)
cookie_branch = (
    ' else if ("logincookie".equals(action)) {\n'
    + body_indent + '// GGQ_EXP33_COOKIE_AUTH_SEMANTICS: SSID is a cookie, not an\n'
    + body_indent + '// OAuth token. Follow LoginOperationW.passiveLogin() semantics\n'
    + body_indent + '// so GeoGebraTubeAPI emits {cookie: ...}; successful userinfo\n'
    + body_indent + '// returns the real token which AuthenticationModelW persists.\n'
    + body_indent + 'Log.debug("Login cookie sent via Quest bridge");\n'
    + body_indent + 'ggqPendingLoginToken = (String) dataObject.get("msg");\n'
    + body_indent + 'doPerformTokenLogin(\n'
    + body_indent + '\tnew GeoGebraTubeUser(null, ggqPendingLoginToken), false);\n'
    + indent + '}'
)
text = text[:match.start()] + original + cookie_branch + text[match.end():]

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
