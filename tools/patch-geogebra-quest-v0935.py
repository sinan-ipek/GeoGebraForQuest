#!/usr/bin/env python3
"""Exp39: export direct OAuth login entrypoint from LoginOperationW.

Android WebView popup/opener MessageEvent delivery has been the unstable link in
the Quest login flow.  Exp39 keeps GeoGebra's real token validation and SUCCESS
event, but exposes a direct JsInterop method that invokes performTokenLogin on
the already-created LoginOperationW instance.  Android can therefore submit one
real callback token without fabricating or repeatedly dispatching MessageEvents.
"""

from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0935.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
path = root / (
    "source/web/web/src/main/java/org/geogebra/web/shared/ggtapi/"
    "LoginOperationW.java"
)
text = path.read_text(encoding="utf-8")

marker = "GGQ_EXP39_DIRECT_OAUTH_ENTRYPOINT"
if marker in text:
    print("[GGQ] exp39 direct OAuth entrypoint already present")
    raise SystemExit(0)

for required in (
    "GGQ_EXP22_LOGIN_READY_ACK",
    "ggqPendingLoginToken",
    "performTokenLogin(ggqPendingLoginToken, false)",
    '"__ggqLoginReady"',
    '"__ggqLoginSuccessToken"',
):
    if required not in text:
        raise RuntimeError(f"exp39 source baseline missing: {required}")

import_anchor = "import jsinterop.base.Js;\n"
import_replacement = (
    "import jsinterop.annotations.JsMethod;\n"
    "import jsinterop.annotations.JsPackage;\n"
    "import jsinterop.base.Js;\n"
)
if import_anchor not in text:
    raise RuntimeError("exp39 Js import anchor missing")
text = text.replace(import_anchor, import_replacement, 1)

field_anchor = "\tprivate String ggqPendingLoginToken;\n"
field_replacement = field_anchor + (
    "\tprivate static LoginOperationW ggqQuestLoginOperation;\n"
)
if field_anchor not in text:
    raise RuntimeError("exp39 pending-token field anchor missing")
text = text.replace(field_anchor, field_replacement, 1)

ready_anchor = '''\t\tiniNativeEvents(app);
\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginSuccessToken", "");
\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginReady", true);
\t\tapiFactory = new BackendAPIFactory(app);
'''
ready_replacement = '''\t\tiniNativeEvents(app);
\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginSuccessToken", "");
\t\tggqQuestLoginOperation = this;
\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginReady", true);
\t\tapiFactory = new BackendAPIFactory(app);
'''
if ready_anchor not in text:
    raise RuntimeError("exp39 LoginOperationW READY anchor missing")
text = text.replace(ready_anchor, ready_replacement, 1)

method_anchor = "\t@Override\n\tpublic BackendAPI getGeoGebraTubeAPI() {\n"
method = '''\t/**
\t * GGQ_EXP39_DIRECT_OAUTH_ENTRYPOINT: submit one real OAuth callback token
\t * directly to the local LoginOperationW instance. Validation and session
\t * creation remain entirely inside GeoGebra's performTokenLogin().
\t *
\t * @param token real OAuth token from ggtcallback
\t * @return whether the local login operation accepted the request
\t */
\t@JsMethod(namespace = JsPackage.GLOBAL, name = "ggqLoginWithOAuthToken")
\tpublic static boolean ggqLoginWithOAuthToken(String token) {
\t\tLoginOperationW operation = ggqQuestLoginOperation;
\t\tif (operation == null || token == null || token.isEmpty()) {
\t\t\treturn false;
\t\t}
\t\toperation.ggqPendingLoginToken = token;
\t\toperation.performTokenLogin(token, false);
\t\treturn true;
\t}

''' + method_anchor
if method_anchor not in text:
    raise RuntimeError("exp39 BackendAPI method anchor missing")
text = text.replace(method_anchor, method, 1)

for required in (
    marker,
    "ggqQuestLoginOperation = this",
    'name = "ggqLoginWithOAuthToken"',
    "operation.ggqPendingLoginToken = token",
    "operation.performTokenLogin(token, false)",
):
    if required not in text:
        raise RuntimeError(f"exp39 source requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp39 direct LoginOperationW OAuth entrypoint installed")
