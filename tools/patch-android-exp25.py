#!/usr/bin/env python3
"""Exp25: Meta-compliant embedded picker Activity + strict popup whitelist.

Bug 1
-----
Exp24 still allowed some remote GeoGebra popup routes that were not in the
profile/app-shell blacklist. Exp25 switches from a blacklist to a whitelist:
registered popup WebViews may navigate remotely only to accounts.geogebra.org or
the trusted ggtcallback page. Material URLs are handed to MAIN and every other
GeoGebra URL is consumed/closed before it can become the visible application.

Bug 2
-----
Exp24 used ActivityPanelRegistration but its panel Activity declaration was
missing the two pieces used by Meta's own ActivityPanel samples:
- android:allowEmbedded="true" on the Activity;
- com.oculus.vrdesktop.fbpermission.CREATE_ACTIVITY_CONTAINER application meta-data.
The missing container contract can make Activity-panel creation tear down the
spatial app at runtime even though Kotlin/CI compiles. Exp25 adds the official
manifest contract, uses a transparent panel theme, and switches result handoff to
SpatialActivityManager.executeOnVrActivity<T>(), matching current Meta samples.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp25.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
manifest_path = root / "app/src/main/AndroidManifest.xml"
proxy_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialFilePickerPanelActivity.kt"

panel = panel_path.read_text(encoding="utf-8")
manifest = manifest_path.read_text(encoding="utf-8")
proxy = proxy_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# BUG 1: replace Exp24 route blacklist with a strict remote-popup whitelist.
# ---------------------------------------------------------------------------
start = panel.find("private fun isForbiddenGeoGebraPopupRoute(uri: Uri): Boolean {")
end = panel.find("\nprivate fun closeForbiddenGeoGebraPopup", start)
if start < 0 or end < 0:
    raise RuntimeError("exp25 could not locate Exp24 popup route function")

strict_route = r'''// EXP25_STRICT_POPUP_WHITELIST: a registered popup is an authentication
// transport, never a second GeoGebra application. Only the account host and the
// trusted callback page may render remotely. Materials are consumed by the close
// helper and handed directly to MAIN local AppW.
private fun isForbiddenGeoGebraPopupRoute(uri: Uri): Boolean {
    if (!isRemoteGeoGebraUri(uri)) return false
    val host = uri.host.orEmpty().lowercase()
    if (host == "accounts.geogebra.org") return false
    if (isTrustedGeoGebraCallback(uri)) return false
    return true
}
'''
panel = panel[:start] + strict_route + panel[end:]

# If the blocked popup URL itself is a material, import it into MAIN before close.
close_anchor = '''    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false
    if (!isForbiddenGeoGebraPopupRoute(uri)) return false

    // If a session cookie happens to exist, opportunistically synchronize MAIN
'''
close_replacement = '''    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false
    if (!isForbiddenGeoGebraPopupRoute(uri)) return false

    if (isGeoGebraMaterialUri(uri)) {
        GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())
    }

    // If a session cookie happens to exist, opportunistically synchronize MAIN
'''
if close_anchor not in panel:
    if "GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())" not in panel:
        raise RuntimeError("exp25 popup close anchor not found")
else:
    panel = panel.replace(close_anchor, close_replacement, 1)

# ---------------------------------------------------------------------------
# BUG 2: match Meta's ActivityPanel manifest requirements.
# ---------------------------------------------------------------------------
container_meta = '''        <meta-data
            android:name="com.oculus.vrdesktop.fbpermission.CREATE_ACTIVITY_CONTAINER"
            android:value="" />
'''
if "com.oculus.vrdesktop.fbpermission.CREATE_ACTIVITY_CONTAINER" not in manifest:
    anchor = '''        <meta-data android:name="com.oculus.vr.focusaware" android:value="true" />
'''
    if anchor not in manifest:
        raise RuntimeError("exp25 focusaware manifest anchor not found")
    manifest = manifest.replace(anchor, anchor + container_meta, 1)

# ActivityPanelRegistration targets must explicitly allow embedding on Horizon OS.
activity_marker = 'android:name=".SpatialFilePickerPanelActivity"'
pos = manifest.find(activity_marker)
if pos < 0:
    raise RuntimeError("exp25 SpatialFilePickerPanelActivity declaration missing")
block_start = manifest.rfind("        <activity", 0, pos)
block_end = manifest.find("/>", pos)
if block_start < 0 or block_end < 0:
    raise RuntimeError("exp25 picker Activity manifest block malformed")
block_end += 2
block = manifest[block_start:block_end]
if 'android:allowEmbedded="true"' not in block:
    block = block.replace(
        'android:exported="false"',
        'android:exported="false"\n            android:allowEmbedded="true"',
        1,
    )
block = block.replace('android:theme="@style/PanelAppTheme"', 'android:theme="@style/PanelAppThemeTransparent"')
manifest = manifest[:block_start] + block + manifest[block_end:]

# Use the same cross-activity bridge API as current Meta ActivityPanel samples.
old_bridge = '''        SpatialActivityManager.executeOnAppSystemActivity { appActivity ->
            (appActivity as? SpatialGeoGebraActivity)?.onSpatialFilePickerPanelResult(uri)
        }
'''
new_bridge = '''        SpatialActivityManager.executeOnVrActivity<SpatialGeoGebraActivity> { activity ->
            activity.onSpatialFilePickerPanelResult(uri)
        }
'''
if old_bridge in proxy:
    proxy = proxy.replace(old_bridge, new_bridge, 1)
elif "executeOnVrActivity<SpatialGeoGebraActivity>" not in proxy:
    raise RuntimeError("exp25 SpatialActivityManager bridge anchor not found")

# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    'host == "accounts.geogebra.org"',
    "isTrustedGeoGebraCallback(uri)",
    "return true",
    "EXP24_SPATIAL_ACTIVITY_PICKER",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
):
    if required not in panel:
        raise RuntimeError(f"exp25 panel requirement missing: {required}")

for required in (
    "com.oculus.vrdesktop.fbpermission.CREATE_ACTIVITY_CONTAINER",
    'android:name=".SpatialFilePickerPanelActivity"',
    'android:allowEmbedded="true"',
    'android:theme="@style/PanelAppThemeTransparent"',
):
    if required not in manifest:
        raise RuntimeError(f"exp25 manifest requirement missing: {required}")

for required in (
    "class SpatialFilePickerPanelActivity : Activity()",
    "Intent.ACTION_OPEN_DOCUMENT",
    "SpatialActivityManager.executeOnVrActivity<SpatialGeoGebraActivity>",
    "activity.onSpatialFilePickerPanelResult(uri)",
):
    if required not in proxy:
        raise RuntimeError(f"exp25 proxy requirement missing: {required}")

if "SpatialActivityManager.executeOnAppSystemActivity" in proxy:
    raise RuntimeError("exp25 old ActivityPanel result bridge remains")

panel_path.write_text(panel, encoding="utf-8")
manifest_path.write_text(manifest, encoding="utf-8")
proxy_path.write_text(proxy, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "popup_guard=exp25" not in text:
        text += (
            "popup_guard=exp25 strict remote popup whitelist: accounts/callback only; "
            "materials handoff to MAIN, all other GeoGebra popup routes blocked\n"
        )
    if "spatial_picker_container=exp25" not in text:
        text += (
            "spatial_picker_container=exp25 allowEmbedded + CREATE_ACTIVITY_CONTAINER + "
            "executeOnVrActivity result bridge\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp25 strict popup whitelist + Meta-compliant embedded picker container installed")
