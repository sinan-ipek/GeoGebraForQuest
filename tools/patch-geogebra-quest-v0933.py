#!/usr/bin/env python3
"""Exp22 GeoGebra-side login READY/SUCCESS handshake for Quest.

The Android login bridge can observe an authenticated GeoGebra SSID cookie before
the bundled local AppW has finished constructing LoginOperationW. A one-shot
MessageEvent can therefore be delivered too early and disappear, leaving the
remote popup authenticated while MAIN still shows "Sign in".

Patch LoginOperationW so the bundled local AppW exposes two explicit JS state
markers:
- window.__ggqLoginReady becomes true only after the message listener exists;
- window.__ggqLoginSuccessToken is set only after the LogInOperation reports a
  real logged-in state for the token most recently received from Android.

Android exp22 waits for READY before dispatching the token and closes the popup
only after SUCCESS is observed, eliminating timing guesses and stale-cookie
premature closure.
"""

from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0933.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
path = root / (
    "source/web/web/src/main/java/org/geogebra/web/shared/ggtapi/"
    "LoginOperationW.java"
)
text = path.read_text(encoding="utf-8")

marker = "GGQ_EXP22_LOGIN_READY_ACK"
if marker in text:
    print("[GGQ] exp22 GeoGebra login READY/SUCCESS handshake already present")
    raise SystemExit(0)

field_anchor = "\tprivate BackendAPIFactory apiFactory;\n"
field_insert = field_anchor + (
    "\n\t// GGQ_EXP22_LOGIN_READY_ACK: token received from the native Quest bridge.\n"
    "\tprivate String ggqPendingLoginToken;\n"
)
if field_anchor not in text:
    raise RuntimeError("exp22 LoginOperationW field anchor not found")
text = text.replace(field_anchor, field_insert, 1)

class_anchor = "\tprivate final class LanguageLoginCallback implements EventRenderable {\n"
ack_class = '''\tprivate final class QuestLoginAckCallback implements EventRenderable {\n\t\t@Override\n\t\tpublic void renderEvent(BaseEvent event) {\n\t\t\tif (isLoggedIn() && ggqPendingLoginToken != null) {\n\t\t\t\tJs.asPropertyMap(DomGlobal.window).set(\n\t\t\t\t\t\t"__ggqLoginSuccessToken", ggqPendingLoginToken);\n\t\t\t\tggqPendingLoginToken = null;\n\t\t\t}\n\t\t}\n\t}\n\n'''
if class_anchor not in text:
    raise RuntimeError("exp22 LoginOperationW callback-class anchor not found")
text = text.replace(class_anchor, ack_class + class_anchor, 1)

constructor_anchor = '''\t\tgetView().add(new LanguageLoginCallback());\n\t\tgetView().add(new LoginAnalytics());\n'''
constructor_replacement = '''\t\tgetView().add(new LanguageLoginCallback());\n\t\tgetView().add(new LoginAnalytics());\n\t\tgetView().add(new QuestLoginAckCallback());\n'''
if constructor_anchor not in text:
    raise RuntimeError("exp22 LoginOperationW view-registration anchor not found")
text = text.replace(constructor_anchor, constructor_replacement, 1)

ready_anchor = '''\t\tiniNativeEvents(app);\n\t\tapiFactory = new BackendAPIFactory(app);\n'''
ready_replacement = '''\t\tiniNativeEvents(app);\n\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginSuccessToken", "");\n\t\tJs.asPropertyMap(DomGlobal.window).set("__ggqLoginReady", true);\n\t\tapiFactory = new BackendAPIFactory(app);\n'''
if ready_anchor not in text:
    raise RuntimeError("exp22 LoginOperationW ready anchor not found")
text = text.replace(ready_anchor, ready_replacement, 1)

# Earlier Quest source patches can change indentation around this block. Patch
# only the actual performTokenLogin call and preserve whatever indentation the
# current pinned source has instead of depending on an exact multi-line shape.
pattern = re.compile(
    r'(?P<indent>[ \t]*)performTokenLogin\(\(String\) dataObject\.get\("msg"\), false\);'
)
match = pattern.search(text)
if match is None:
    raise RuntimeError("exp22 LoginOperationW logintoken call not found")
indent = match.group("indent")
replacement = (
    indent + 'ggqPendingLoginToken = (String) dataObject.get("msg");\n' +
    indent + 'performTokenLogin(ggqPendingLoginToken, false);'
)
text = text[:match.start()] + replacement + text[match.end():]

for required in (
    marker,
    "QuestLoginAckCallback",
    "ggqPendingLoginToken",
    '"__ggqLoginReady"',
    '"__ggqLoginSuccessToken"',
    "performTokenLogin(ggqPendingLoginToken, false)",
):
    if required not in text:
        raise RuntimeError(f"exp22 GeoGebra login requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp22 GeoGebra login READY/SUCCESS handshake installed")
