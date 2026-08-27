#!/usr/bin/env python3
"""Restore Exp20 MAIN navigation helpers if Exp22 cookie-handoff replacement removed them.

Exp22 replaces the Exp19 cookie handoff block. In the patched build order, Exp20
had inserted the canonical MAIN navigation helpers between that function and
refreshImeConnection(), so a broad replacement could accidentally remove those
helpers while leaving call-sites pointing at handleGeoGebraNavigation().

This narrow repair restores only the Exp20 navigation helper layer. It does not
reintroduce Exp20's staged local-file restart; Exp21's proven direct local-file
callback remains untouched.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp22-preserve-navigation.py <repo-root>")

root = Path(sys.argv[1]).resolve()
path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
text = path.read_text(encoding="utf-8")

marker = "EXP20_CANONICAL_MAIN_GUARD"
if marker not in text:
    anchor = "private fun refreshImeConnection(view: View) {\n"
    if anchor not in text:
        raise RuntimeError("exp22 navigation repair refreshImeConnection anchor not found")

    helpers = r'''private fun isRemoteGeoGebraUri(uri: Uri): Boolean {
    val scheme = uri.scheme.orEmpty().lowercase()
    val host = uri.host.orEmpty().lowercase()
    return (scheme == "http" || scheme == "https") &&
        (host == "geogebra.org" || host.endsWith(".geogebra.org"))
}

private fun isGeoGebraMaterialUri(uri: Uri): Boolean {
    val path = uri.path.orEmpty().lowercase()
    return path.startsWith("/m/") ||
        path.startsWith("/material/") ||
        path.contains("/material/show/")
}

// EXP20_CANONICAL_MAIN_GUARD: MAIN is the patched local Classic engine, not a
// general browser. A remote GeoGebra material may be imported into MAIN, but the
// remote site shell/profile/teacher pages are never allowed to replace MAIN.
private fun handleGeoGebraNavigation(
    view: WebView,
    uri: Uri,
    registerAsMain: Boolean,
): Boolean {
    if (handleGeoGebraLoginCallback(view, uri)) return true
    if (!registerAsMain) return false
    if (!isRemoteGeoGebraUri(uri)) return false

    if (isGeoGebraMaterialUri(uri)) {
        GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())
    }
    return true
}

'''
    text = text.replace(anchor, helpers + anchor, 1)

for required in (
    "EXP20_CANONICAL_MAIN_GUARD",
    "handleGeoGebraNavigation(view, request.url, registerAsMain)",
    "handleGeoGebraNavigation(view, Uri.parse(url), registerAsMain)",
    "EXP20_REMOTE_ESCAPE_FALLBACK",
    "EXP21_PROVEN_LOCAL_FILE_PATH",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
):
    if required not in text:
        raise RuntimeError(f"exp22 navigation-preservation requirement missing: {required}")

for forbidden in (
    "EXP20_PENDING_LOCAL_FILE",
    "EXP20_CANONICAL_FILE_RESTART",
    "activity.recreate()",
    "PENDING_LOCAL_GGB_URL",
    "PendingLocalFilePathHandler",
    "openPendingLocalFileIfAny",
):
    if forbidden in text:
        raise RuntimeError(f"exp22 navigation repair reintroduced local-file restart residue: {forbidden}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp22 preserved Exp20 MAIN navigation guard without restoring staged local-file restart")
