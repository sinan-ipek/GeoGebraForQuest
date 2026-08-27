#!/usr/bin/env python3
"""Exp24: source-level profile/app-shell lock + Spatial Activity file picker.

Bug 1
-----
Exp23 reduced remote-app escapes but a deterministic profile/avatar path can still
open a remote GeoGebra page that has no ggbApplet and may not have an SSID cookie.
Waiting for the popup to become an app shell is therefore too late. Exp24 blocks
known profile/account/app-shell routes synchronously in shouldOverrideUrlLoading
for registered popup WebViews. Login on accounts.geogebra.org and material handoff
remain allowed. MAIN remains protected by Exp20.

Bug 2
-----
Exp23 proved that changing embedded B/C topology before ACTION_OPEN_DOCUMENT does
not preserve the right controller. Exp24 removes ACTION_OPEN_DOCUMENT from the
main AppSystemActivity path entirely. The picker is launched from a dedicated
ActivityPanelRegistration. The proxy Activity and DocumentsUI live in the spatial
panel activity stack; the main immersive AppSystemActivity stays in its OpenXR
session. The selected content Uri is returned to MAIN with SpatialActivityManager,
then delivered to the original WebView file chooser callback.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp24.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
system_path = root / "app/src/main/java/com/sinan/geogebraforquest/EmbeddedStereoTestSystem.kt"
manifest_path = root / "app/src/main/AndroidManifest.xml"
ids_path = root / "app/src/main/res/values/ids.xml"
proxy_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialFilePickerPanelActivity.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
system = system_path.read_text(encoding="utf-8")
manifest = manifest_path.read_text(encoding="utf-8")
ids = ids_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# BUG 1: stop profile/account/app-shell popup escapes before they render.
# ---------------------------------------------------------------------------
if "EXP24_PROFILE_ESCAPE_LOCK" not in panel:
    anchor = "private fun handleGeoGebraNavigation(\n"
    if anchor not in panel:
        raise RuntimeError("exp24 navigation helper anchor not found")

    helper = r'''// EXP24_PROFILE_ESCAPE_LOCK: these routes are never useful as an independent
// visible application surface in Quest mode. Authentication remains on
// accounts.geogebra.org and selected materials are handed to local MAIN.
private fun isForbiddenGeoGebraPopupRoute(uri: Uri): Boolean {
    if (!isRemoteGeoGebraUri(uri)) return false
    val host = uri.host.orEmpty().lowercase()
    if (host == "accounts.geogebra.org") return false

    val path = uri.path.orEmpty().trimEnd('/').lowercase()
    return path.isBlank() || path == "/" ||
        path == "/classic" || path.startsWith("/classic/") ||
        path == "/calculator" || path.startsWith("/calculator/") ||
        path == "/graphing" || path.startsWith("/graphing/") ||
        path == "/geometry" || path.startsWith("/geometry/") ||
        path == "/3d" || path.startsWith("/3d/") ||
        path == "/cas" || path.startsWith("/cas/") ||
        path == "/suite" || path.startsWith("/suite/") ||
        path == "/profile" || path.startsWith("/profile/") ||
        path == "/account" || path.startsWith("/account/") ||
        path == "/settings" || path.startsWith("/settings/") ||
        path.startsWith("/u/")
}

private fun closeForbiddenGeoGebraPopup(view: WebView, uri: Uri): Boolean {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return false
    if (!isForbiddenGeoGebraPopupRoute(uri)) return false

    // If a session cookie happens to exist, opportunistically synchronize MAIN
    // before closing. The close itself does not depend on SSID or ggbApplet.
    val token = popupGeoGebraSessionToken(view)
    if (!token.isNullOrBlank()) {
        GeoGebraWebNavigation.armLoginAck(view, token)
        GeoGebraWebNavigation.deliverLoginToken(token)
    }

    view.visibility = View.INVISIBLE
    view.post { GeoGebraWebNavigation.closePopup(view) }
    return true
}

''' + anchor
    panel = panel.replace(anchor, helper, 1)

# Insert the popup lock into the canonical navigation function before popup exemption.
old_nav = '''    if (handleGeoGebraLoginCallback(view, uri)) return true
    if (!registerAsMain) return false
    if (!isRemoteGeoGebraUri(uri)) return false
'''
new_nav = '''    if (handleGeoGebraLoginCallback(view, uri)) return true
    if (!registerAsMain) {
        if (closeForbiddenGeoGebraPopup(view, uri)) return true
        return false
    }
    if (!isRemoteGeoGebraUri(uri)) return false
'''
if old_nav in panel:
    panel = panel.replace(old_nav, new_nav, 1)
elif "closeForbiddenGeoGebraPopup(view, uri)" not in panel:
    raise RuntimeError("exp24 canonical navigation body anchor not found")

# ---------------------------------------------------------------------------
# BUG 2: replace main-Activity SAF launch with an Activity-based spatial panel.
# ---------------------------------------------------------------------------
# Add a direct result delivery function to the existing WebView callback owner.
if "EXP24_SPATIAL_PICKER_RESULT" not in panel:
    anchor = '''    fun cancelPending() {
        pendingCallback?.onReceiveValue(null)
        pendingCallback = null
    }
'''
    insert = r'''    // EXP24_SPATIAL_PICKER_RESULT: result comes from the Activity-based
    // spatial picker panel, not SpatialGeoGebraActivity.onActivityResult().
    fun deliverSpatialPickerResult(uri: Uri?) {
        val callback = pendingCallback
        pendingCallback = null
        if (callback == null) return
        callback.onReceiveValue(if (uri == null) null else arrayOf(uri))
    }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp24 cancelPending anchor not found")
    panel = panel.replace(anchor, insert, 1)

# Exp23 routes the main Activity through a topology boundary then starts DocumentsUI.
# In spatial mode Exp24 must never call startActivityForResult on MAIN.
old_exp23 = '''            if (activity is SpatialGeoGebraActivity) {
                // EXP23_PICKER_SAFE_TOPOLOGY_LAUNCH: the Spatial system first
                // detaches embedded B/C, then it launches DocumentsUI from UI thread.
                if (!activity.requestLocalFilePickerLaunch(intent, REQUEST_CODE)) {
                    pendingCallback = null
                    callback.onReceiveValue(null)
                    false
                } else {
                    true
                }
            } else {
                @Suppress("DEPRECATION")
                activity.startActivityForResult(intent, REQUEST_CODE)
                true
            }
'''
new_exp24 = '''            if (activity is SpatialGeoGebraActivity) {
                // EXP24_SPATIAL_ACTIVITY_PICKER: keep MAIN immersive/OpenXR alive.
                if (!activity.requestSpatialFilePickerPanel()) {
                    pendingCallback = null
                    callback.onReceiveValue(null)
                    false
                } else {
                    true
                }
            } else {
                // Non-spatial development fallback only.
                @Suppress("DEPRECATION")
                activity.startActivityForResult(intent, REQUEST_CODE)
                true
            }
'''
if old_exp23 in panel:
    panel = panel.replace(old_exp23, new_exp24, 1)
elif "EXP24_SPATIAL_ACTIVITY_PICKER" not in panel:
    raise RuntimeError("exp24 exp23 picker launch anchor not found")

# ---------------------------------------------------------------------------
# Remove Exp23's now-falsified topology boundary from Activity/System.
# ---------------------------------------------------------------------------
activity = activity.replace(
    '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            requestEmbeddedTopologyRestoreAfterLocalFilePicker()
            return
        }
''',
    '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
''',
    1,
)

# Remove Exp23 boundary fields.
field_block = r'''
    // EXP23_EXTERNAL_PICKER_TOPOLOGY_BOUNDARY
    @Volatile
    private var pendingLocalFilePickerIntent: Intent? = null
    @Volatile
    private var pendingLocalFilePickerRequestCode: Int = 0
    @Volatile
    private var embeddedTopologySuspendedForPicker = false
    @Volatile
    private var embeddedTopologyRestoreRequested = false
'''
activity = activity.replace(field_block, "", 1)

# Remove the contiguous Exp23 picker methods, keeping onQuestAButtonPressed.
start = activity.find("    internal fun requestLocalFilePickerLaunch(intent: Intent, requestCode: Int): Boolean {")
end = activity.find("    internal fun onQuestAButtonPressed() {", start)
if start >= 0 and end >= 0:
    activity = activity[:start] + activity[end:]

activity = activity.replace(
    '''    internal fun applyPendingEmbeddedLayout() {
        if (embeddedTopologySuspendedForPicker) return
        val panel = stereoPanelEntity ?: return
''',
    '''    internal fun applyPendingEmbeddedLayout() {
        val panel = stereoPanelEntity ?: return
''',
    1,
)

system = system.replace(
    '''    override fun execute() {
        activity.processLocalFilePickerTopologyBoundary()
        activity.applyPendingEmbeddedLayout()
    }
''',
    '''    override fun execute() {
        activity.processSpatialFilePickerPanelRequests()
        activity.applyPendingEmbeddedLayout()
    }
''',
    1,
)

# ---------------------------------------------------------------------------
# Register and control the dedicated Activity-based spatial picker panel.
# ---------------------------------------------------------------------------
if "com.meta.spatial.toolkit.ActivityPanelRegistration" not in activity:
    import_anchor = "import com.meta.spatial.toolkit.AppSystemActivity\n"
    if import_anchor not in activity:
        raise RuntimeError("exp24 ActivityPanelRegistration import anchor not found")
    activity = activity.replace(
        import_anchor,
        import_anchor + "import com.meta.spatial.toolkit.ActivityPanelRegistration\n",
        1,
    )

if "EXP24_SPATIAL_FILE_PICKER_PANEL" not in activity:
    # Add fields next to other panel entities.
    anchor = "    private var embeddedBackplateEntity: Entity? = null\n"
    insert = anchor + r'''    // EXP24_SPATIAL_FILE_PICKER_PANEL
    private var spatialFilePickerPanelEntity: Entity? = null
    @Volatile
    private var spatialFilePickerOpenRequested = false
    @Volatile
    private var spatialFilePickerCloseRequested = false
'''
    if anchor not in activity:
        raise RuntimeError("exp24 picker field anchor not found")
    activity = activity.replace(anchor, insert, 1)

    # Add the Activity panel registration before the stereo VideoSurface registration.
    reg_anchor = '''            VideoSurfacePanelRegistration(
                R.id.geogebra_stereo_panel,
'''
    registration = r'''            ActivityPanelRegistration(
                registrationId = R.id.local_file_picker_panel,
                classIdCreator = { SpatialFilePickerPanelActivity::class.java },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(width = 1.30f, height = 0.86f),
                        display = DpDisplayOptions(width = 1040f, height = 688f),
                        input = PanelInputOptions(
                            ButtonBits.ButtonTriggerL or ButtonBits.ButtonTriggerR,
                        ),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppTheme,
                        ),
                    )
                },
            ),
''' + reg_anchor
    if reg_anchor not in activity:
        raise RuntimeError("exp24 VideoSurface registration anchor not found")
    activity = activity.replace(reg_anchor, registration, 1)

    method_anchor = '''    internal fun onQuestAButtonPressed() {
'''
    methods = r'''    internal fun requestSpatialFilePickerPanel(): Boolean {
        if (spatialFilePickerPanelEntity != null || spatialFilePickerOpenRequested) return false
        spatialFilePickerOpenRequested = true
        return true
    }

    /** Called on the main Android thread by SpatialActivityManager from the panel Activity. */
    internal fun onSpatialFilePickerPanelResult(uri: android.net.Uri?) {
        GeoGebraLocalFilePicker.deliverSpatialPickerResult(uri)
        spatialFilePickerCloseRequested = true
    }

    /** Runs only on the Spatial system thread. */
    internal fun processSpatialFilePickerPanelRequests() {
        if (spatialFilePickerCloseRequested) {
            spatialFilePickerCloseRequested = false
            spatialFilePickerPanelEntity?.destroy()
            spatialFilePickerPanelEntity = null
            Log.i(TAG, "exp24 spatial file picker panel closed")
        }

        if (!spatialFilePickerOpenRequested || spatialFilePickerPanelEntity != null) return
        spatialFilePickerOpenRequested = false
        val geoPanel = geoPanelEntity ?: run {
            GeoGebraLocalFilePicker.deliverSpatialPickerResult(null)
            return
        }

        spatialFilePickerPanelEntity = Entity.create(
            Panel(R.id.local_file_picker_panel),
            TransformParent(geoPanel),
            // Slightly in front of A while the file browser is open.
            Transform(Pose(Vector3(0f, 0f, -0.025f))),
            Scale(Vector3(0.96f, 0.96f, 1f)),
            Grabbable(false),
        )
        Log.i(TAG, "exp24 spatial file picker panel opened; MAIN OpenXR remains active")
    }

''' + method_anchor
    if method_anchor not in activity:
        raise RuntimeError("exp24 activity method anchor not found")
    activity = activity.replace(method_anchor, methods, 1)

# Clean picker panel during shutdown.
destroy_anchor = '''        embeddedBackplateEntity = null
        geoPanelEntity = null
'''
destroy_replacement = '''        spatialFilePickerPanelEntity?.destroy()
        spatialFilePickerPanelEntity = null
        spatialFilePickerOpenRequested = false
        spatialFilePickerCloseRequested = false
        embeddedBackplateEntity = null
        geoPanelEntity = null
'''
if destroy_anchor in activity:
    activity = activity.replace(destroy_anchor, destroy_replacement, 1)
elif "spatialFilePickerPanelEntity?.destroy()" not in activity:
    raise RuntimeError("exp24 onDestroy picker cleanup anchor not found")

# ---------------------------------------------------------------------------
# Proxy Activity that launches DocumentsUI inside the Activity-panel task.
# ---------------------------------------------------------------------------
proxy = r'''package com.sinan.geogebraforquest

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.TextView
import com.meta.spatial.toolkit.SpatialActivityManager

/**
 * Exp24 proxy Activity hosted by ActivityPanelRegistration.
 *
 * ACTION_OPEN_DOCUMENT is launched from this panel Activity rather than from the
 * immersive AppSystemActivity. DocumentsUI therefore participates in the panel's
 * Android activity stack while the main Quest/OpenXR activity remains immersive.
 */
class SpatialFilePickerPanelActivity : Activity() {

    companion object {
        private const val REQUEST_OPEN_GGB = 9240
    }

    private var resultDelivered = false
    private var pickerStarted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(
            TextView(this).apply {
                text = "GeoGebra dosyası seçiliyor…"
                textSize = 22f
                gravity = android.view.Gravity.CENTER
                setPadding(32, 32, 32, 32)
            },
        )

        pickerStarted = savedInstanceState?.getBoolean("pickerStarted") ?: false
        if (!pickerStarted) {
            pickerStarted = true
            launchDocumentPicker()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("pickerStarted", pickerStarted)
        super.onSaveInstanceState(outState)
    }

    private fun launchDocumentPicker() {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        try {
            @Suppress("DEPRECATION")
            startActivityForResult(intent, REQUEST_OPEN_GGB)
        } catch (_: Throwable) {
            deliverAndFinish(null)
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_OPEN_GGB) return

        val uri = if (resultCode == RESULT_OK) data?.data else null
        if (uri != null) {
            try {
                val takeFlags = data?.flags?.and(Intent.FLAG_GRANT_READ_URI_PERMISSION) ?: 0
                if (takeFlags != 0) {
                    contentResolver.takePersistableUriPermission(uri, takeFlags)
                }
            } catch (_: Throwable) {
                // Immediate package-level read grant is enough for this open even
                // if the provider does not support persistable permissions.
            }
        }
        deliverAndFinish(uri)
    }

    private fun deliverAndFinish(uri: Uri?) {
        if (resultDelivered) return
        resultDelivered = true
        SpatialActivityManager.executeOnAppSystemActivity { appActivity ->
            (appActivity as? SpatialGeoGebraActivity)?.onSpatialFilePickerPanelResult(uri)
        }
        finish()
    }

    override fun onDestroy() {
        if (isFinishing && !resultDelivered) {
            deliverAndFinish(null)
        }
        super.onDestroy()
    }
}
'''
proxy_path.write_text(proxy, encoding="utf-8")

# Resource id for the Activity-based panel.
if 'name="local_file_picker_panel"' not in ids:
    ids = ids.replace(
        "</resources>",
        '    <item name="local_file_picker_panel" type="id" />\n</resources>',
        1,
    )

# Declare the proxy Activity. It is internal and is only instantiated as a panel.
if ".SpatialFilePickerPanelActivity" not in manifest:
    anchor = '''        <!-- Kept only as a non-launcher fallback for development/recovery. -->
'''
    decl = '''        <activity
            android:name=".SpatialFilePickerPanelActivity"
            android:exported="false"
            android:excludeFromRecents="true"
            android:resizeableActivity="true"
            android:theme="@style/PanelAppTheme" />

''' + anchor
    if anchor not in manifest:
        raise RuntimeError("exp24 manifest activity anchor not found")
    manifest = manifest.replace(anchor, decl, 1)

# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
for required in (
    "EXP24_PROFILE_ESCAPE_LOCK",
    "isForbiddenGeoGebraPopupRoute",
    "closeForbiddenGeoGebraPopup(view, uri)",
    "EXP24_SPATIAL_PICKER_RESULT",
    "deliverSpatialPickerResult",
    "EXP24_SPATIAL_ACTIVITY_PICKER",
    "requestSpatialFilePickerPanel()",
):
    if required not in panel:
        raise RuntimeError(f"exp24 panel requirement missing: {required}")

for required in (
    "EXP24_SPATIAL_FILE_PICKER_PANEL",
    "ActivityPanelRegistration",
    "R.id.local_file_picker_panel",
    "requestSpatialFilePickerPanel",
    "onSpatialFilePickerPanelResult",
    "processSpatialFilePickerPanelRequests",
):
    if required not in activity:
        raise RuntimeError(f"exp24 activity requirement missing: {required}")

for forbidden in (
    "requestLocalFilePickerLaunch(",
    "processLocalFilePickerTopologyBoundary(",
    "embeddedTopologySuspendedForPicker",
    "requestEmbeddedTopologyRestoreAfterLocalFilePicker",
):
    if forbidden in activity:
        raise RuntimeError(f"exp24 stale exp23 topology path remains: {forbidden}")

if "processSpatialFilePickerPanelRequests()" not in system:
    raise RuntimeError("exp24 Spatial picker processing missing from EmbeddedStereoTestSystem")
if "processLocalFilePickerTopologyBoundary()" in system:
    raise RuntimeError("exp24 stale exp23 topology system call remains")

for required in (
    "class SpatialFilePickerPanelActivity : Activity()",
    "Intent.ACTION_OPEN_DOCUMENT",
    "SpatialActivityManager.executeOnAppSystemActivity",
    "onSpatialFilePickerPanelResult(uri)",
):
    if required not in proxy:
        raise RuntimeError(f"exp24 proxy requirement missing: {required}")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
system_path.write_text(system, encoding="utf-8")
manifest_path.write_text(manifest, encoding="utf-8")
ids_path.write_text(ids, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "profile_escape_lock=exp24" not in text:
        text += (
            "profile_escape_lock=exp24 synchronous popup profile/app-shell block before render; "
            "accounts login and local material handoff preserved\n"
        )
    if "local_picker=exp24" not in text:
        text += (
            "local_picker=exp24 ActivityPanel proxy owns ACTION_OPEN_DOCUMENT; "
            "MAIN AppSystemActivity never leaves immersive OpenXR for local file selection\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp24 profile escape lock + ActivityPanel spatial file picker installed")
