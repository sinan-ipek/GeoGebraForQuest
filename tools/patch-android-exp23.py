#!/usr/bin/env python3
"""Exp23: eliminate popup app-shell escape and isolate embedded topology from DocumentsUI.

Bug 1 hypothesis
----------------
MAIN is already guarded by Exp20, but WebChromeClient.onCreateWindow creates a
MATCH_PARENT popup with registerAsMain=false. That popup is intentionally exempt
from the MAIN guard. If GeoGebra authentication redirects that popup into a full
remote GeoGebra application, the popup visually covers our local patched MAIN and
has no Quest stereo injection. Exp23 detects a remote GeoGebra app shell (known
app URL or a popup that exposes ggbApplet), hands any session/material back to
MAIN, hides the popup immediately, and destroys it. A remote app can therefore no
longer become the visible application surface.

Bug 2 hypothesis
----------------
v0.9.29 used the same ACTION_OPEN_DOCUMENT callback successfully. The major
runtime difference is the experimental embedded topology: B and C are children of
A when DocumentsUI takes immersive focus away. Exp23 therefore does not try to
repair Controller/Avatar components after the fact. Instead, before launching the
system picker on the Android UI thread, a Spatial-system frame suspends embedded
B/C into a v0.9.29-like standalone/non-child state. On return the topology is
restored and the latest embedded layout is reapplied. Exp22 AvatarSystem recovery
is removed entirely so this hypothesis is isolated.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp23.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
system_path = root / "app/src/main/java/com/sinan/geogebraforquest/EmbeddedStereoTestSystem.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
system = system_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# BUG 1: registered popup WebViews may never become a remote GeoGebra app shell.
# ---------------------------------------------------------------------------
if "EXP23_POPUP_APP_SHELL_QUARANTINE" not in panel:
    anchor = "private fun refreshImeConnection(view: View) {\n"
    if anchor not in panel:
        raise RuntimeError("exp23 popup helper anchor not found")

    helpers = r'''private fun isLikelyRemoteGeoGebraAppShell(uri: Uri): Boolean {
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
        path == "/suite" || path.startsWith("/suite/")
}

// EXP23_POPUP_APP_SHELL_QUARANTINE: a popup is allowed to perform authentication,
// but it is never allowed to turn into the visible GeoGebra application. MAIN is
// the only application surface and is always our local patched AppW.
private val exp23QuarantinedPopups = java.util.WeakHashMap<WebView, Boolean>()

private fun quarantineRemoteGeoGebraAppPopup(view: WebView, url: String) {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return
    synchronized(exp23QuarantinedPopups) {
        if (exp23QuarantinedPopups[view] == true) return
        exp23QuarantinedPopups[view] = true
    }

    // Remove the remote app from the visible panel immediately. Token/file handoff
    // continues independently on MAIN, so the popup never needs to remain visible.
    view.visibility = View.INVISIBLE

    val uri = try { Uri.parse(url) } catch (_: Throwable) { null }
    if (uri != null && isGeoGebraMaterialUri(uri)) {
        GeoGebraWebNavigation.deliverOpenFromGgt(uri.toString())
    }

    val token = popupGeoGebraSessionToken(view)
    if (!token.isNullOrBlank()) {
        GeoGebraWebNavigation.armLoginAck(view, token)
        GeoGebraWebNavigation.deliverLoginToken(token)
    }

    view.postDelayed({
        if (GeoGebraWebNavigation.isRegisteredPopup(view)) {
            GeoGebraWebNavigation.closePopup(view)
        }
    }, 350L)
}

private fun inspectPopupForRemoteAppShell(view: WebView, url: String) {
    if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return
    val uri = try { Uri.parse(url) } catch (_: Throwable) { return }
    if (!isRemoteGeoGebraUri(uri)) return

    // Known application entry points are quarantined without waiting for GWT.
    if (isLikelyRemoteGeoGebraAppShell(uri)) {
        quarantineRemoteGeoGebraAppPopup(view, url)
        return
    }

    // Backup detector: some material/profile routes bootstrap Classic without a
    // canonical /classic path. Detect the actual remote ggbApplet instead.
    fun probe(delayMs: Long) {
        view.postDelayed({
            if (!GeoGebraWebNavigation.isRegisteredPopup(view)) return@postDelayed
            view.evaluateJavascript(
                "(function(){try{return !!(window.ggbApplet && typeof window.ggbApplet.openFile === 'function');}catch(_){return false;}})();"
            ) { result ->
                if (result == "true" && GeoGebraWebNavigation.isRegisteredPopup(view)) {
                    quarantineRemoteGeoGebraAppPopup(view, view.url ?: url)
                }
            }
        }, delayMs)
    }
    probe(0L)
    probe(350L)
    probe(1200L)
}

''' + anchor
    panel = panel.replace(anchor, helpers, 1)

    page_anchor = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
'''
    page_insert = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                if (!registerAsMain) {
                    inspectPopupForRemoteAppShell(view, url)
                }
'''
    if page_anchor not in panel:
        raise RuntimeError("exp23 onPageFinished anchor not found")
    panel = panel.replace(page_anchor, page_insert, 1)

# ---------------------------------------------------------------------------
# BUG 2: launch ACTION_OPEN_DOCUMENT only after Spatial B/C topology is suspended.
# ---------------------------------------------------------------------------
old_launch = '''        return try {
            @Suppress("DEPRECATION")
            activity.startActivityForResult(intent, REQUEST_CODE)
            true
        } catch (_: Throwable) {
            pendingCallback = null
            callback.onReceiveValue(null)
            false
        }
'''
new_launch = '''        return try {
            if (activity is SpatialGeoGebraActivity) {
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
        } catch (_: Throwable) {
            pendingCallback = null
            callback.onReceiveValue(null)
            false
        }
'''
if old_launch not in panel:
    if "EXP23_PICKER_SAFE_TOPOLOGY_LAUNCH" not in panel:
        raise RuntimeError("exp23 local picker launch anchor not found")
else:
    panel = panel.replace(old_launch, new_launch, 1)

# Remove Exp22 AvatarSystem recovery field / registration / callbacks. This failed
# on device and would confound the new topology-boundary hypothesis.
activity = activity.replace(
    '''\n    // EXP22_AVATAR_CONTROLLER_RETURN\n    private lateinit var controllerPresentationRecoverySystem: QuestControllerPresentationRecoverySystem\n''',
    "",
    1,
)
activity = activity.replace(
    '''        controllerPresentationRecoverySystem = QuestControllerPresentationRecoverySystem()\n        systemManager.registerSystem(controllerPresentationRecoverySystem)\n        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n''',
    '''        systemManager.registerSystem(QuestControllerShortcutSystem(this))\n''',
    1,
)

helper_start = activity.find("    private fun requestControllerPresentationRecovery(reason: String) {")
if helper_start >= 0:
    helper_end = activity.find('    @Suppress("DEPRECATION")\n    override fun onBackPressed()', helper_start)
    if helper_end < 0:
        raise RuntimeError("exp23 could not remove exp22 recovery helper")
    activity = activity[:helper_start] + activity[helper_end:]

activity = activity.replace(
    '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            requestControllerPresentationRecovery("local-file-result")
            return
        }
''',
    '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            requestEmbeddedTopologyRestoreAfterLocalFilePicker()
            return
        }
''',
    1,
)
activity = activity.replace(
    '''    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) {
            requestControllerPresentationRecovery("vr-ready-return")
            return
        }
''',
    '''    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
''',
    1,
)

# Add cross-thread picker boundary state next to embedded layout fields.
if "EXP23_EXTERNAL_PICKER_TOPOLOGY_BOUNDARY" not in activity:
    field_anchor = '''    @Volatile
    private var pendingEmbeddedLayout: String? = null
    private var lastAppliedEmbeddedLayout: String? = null
'''
    field_insert = field_anchor + r'''

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
    if field_anchor not in activity:
        raise RuntimeError("exp23 embedded layout field anchor not found")
    activity = activity.replace(field_anchor, field_insert, 1)

    method_anchor = '''    internal fun onQuestAButtonPressed() {
'''
    methods = r'''    internal fun requestLocalFilePickerLaunch(intent: Intent, requestCode: Int): Boolean {
        if (pendingLocalFilePickerIntent != null || embeddedTopologySuspendedForPicker) return false
        pendingLocalFilePickerRequestCode = requestCode
        pendingLocalFilePickerIntent = intent
        return true
    }

    private fun requestEmbeddedTopologyRestoreAfterLocalFilePicker() {
        embeddedTopologyRestoreRequested = true
    }

    /**
     * Runs only on the Spatial system thread from EmbeddedStereoTestSystem.
     * The external picker is launched only after B and C no longer form an
     * embedded child-panel topology. This mirrors the important topology property
     * of v0.9.29 while preserving Exp21's direct WebView URI callback.
     */
    internal fun processLocalFilePickerTopologyBoundary() {
        if (embeddedTopologyRestoreRequested) {
            embeddedTopologyRestoreRequested = false
            embeddedTopologySuspendedForPicker = false
            lastAppliedEmbeddedLayout = null

            val geoPanel = geoPanelEntity
            val backplate = embeddedBackplateEntity
            if (geoPanel != null && backplate != null) {
                backplate.setComponent(TransformParent(geoPanel))
                backplate.setComponent(
                    Transform(Pose(Vector3(0f, 0f, EMBEDDED_BACKPLATE_DEPTH_METERS)))
                )
                backplate.setComponent(Scale(EMBEDDED_BACKPLATE_SCALE))
                backplate.setComponent(Hittable(MeshCollision.NoCollision))
                backplate.setComponent(Visible(true))
            }
            Log.i(TAG, "exp23 local picker return: embedded topology re-enabled")
        }

        val intent = pendingLocalFilePickerIntent ?: return
        if (embeddedTopologySuspendedForPicker) return

        val requestCode = pendingLocalFilePickerRequestCode
        pendingLocalFilePickerIntent = null
        embeddedTopologySuspendedForPicker = true
        lastAppliedEmbeddedLayout = null

        // B: standalone and hidden; C: detached and hidden. No embedded child
        // panel remains when DocumentsUI changes the immersive session state.
        stereoPanelEntity?.let { panel ->
            panel.setComponent(TransformParent())
            panel.setComponent(Transform(INITIAL_STEREO_POSE))
            panel.setComponent(Scale(Vector3(1f, 1f, 1f)))
            panel.setComponent(Grabbable(false))
            panel.setComponent(Hittable(MeshCollision.NoCollision))
            panel.setComponent(Visible(false))
        }
        embeddedBackplateEntity?.let { backplate ->
            backplate.setComponent(TransformParent())
            backplate.setComponent(Visible(false))
        }

        Log.i(TAG, "exp23 local picker launch: embedded B/C topology suspended")
        window.decorView.post {
            try {
                @Suppress("DEPRECATION")
                startActivityForResult(intent, requestCode)
            } catch (t: Throwable) {
                Log.w(TAG, "exp23 local picker launch failed", t)
                GeoGebraLocalFilePicker.cancelPending()
                embeddedTopologyRestoreRequested = true
            }
        }
    }

''' + method_anchor
    if method_anchor not in activity:
        raise RuntimeError("exp23 activity method anchor not found")
    activity = activity.replace(method_anchor, methods, 1)

# Prevent stale WebView layout messages from re-embedding B/C while picker owns focus.
apply_anchor = '''    internal fun applyPendingEmbeddedLayout() {
        val panel = stereoPanelEntity ?: return
'''
apply_replacement = '''    internal fun applyPendingEmbeddedLayout() {
        if (embeddedTopologySuspendedForPicker) return
        val panel = stereoPanelEntity ?: return
'''
if apply_anchor in activity:
    activity = activity.replace(apply_anchor, apply_replacement, 1)
elif "if (embeddedTopologySuspendedForPicker) return" not in activity:
    raise RuntimeError("exp23 applyPendingEmbeddedLayout anchor not found")

# Spatial system owns both prepare/restore and normal layout application.
old_system = '''    override fun execute() {
        activity.applyPendingEmbeddedLayout()
    }
'''
new_system = '''    override fun execute() {
        activity.processLocalFilePickerTopologyBoundary()
        activity.applyPendingEmbeddedLayout()
    }
'''
if old_system in system:
    system = system.replace(old_system, new_system, 1)
elif "processLocalFilePickerTopologyBoundary()" not in system:
    raise RuntimeError("exp23 EmbeddedStereoTestSystem anchor not found")

# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
for required in (
    "EXP23_POPUP_APP_SHELL_QUARANTINE",
    "inspectPopupForRemoteAppShell(view, url)",
    "quarantineRemoteGeoGebraAppPopup",
    "window.ggbApplet",
    "EXP20_CANONICAL_MAIN_GUARD",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP21_PROVEN_LOCAL_FILE_PATH",
    "EXP23_PICKER_SAFE_TOPOLOGY_LAUNCH",
):
    if required not in panel:
        raise RuntimeError(f"exp23 panel requirement missing: {required}")

for required in (
    "EXP23_EXTERNAL_PICKER_TOPOLOGY_BOUNDARY",
    "requestLocalFilePickerLaunch",
    "processLocalFilePickerTopologyBoundary",
    "embeddedTopologySuspendedForPicker",
    "requestEmbeddedTopologyRestoreAfterLocalFilePicker",
    "EXP19_NATIVE_LAYOUT_REARM",
):
    if required not in activity:
        raise RuntimeError(f"exp23 activity requirement missing: {required}")

for forbidden in (
    "requestControllerPresentationRecovery(",
    "controllerPresentationRecoverySystem",
):
    if forbidden in activity:
        raise RuntimeError(f"exp23 exp22 Avatar recovery residue remains: {forbidden}")

if "processLocalFilePickerTopologyBoundary()" not in system:
    raise RuntimeError("exp23 spatial system does not own picker boundary")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
system_path.write_text(system, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "popup_guard=exp23" not in text:
        text += (
            "popup_guard=exp23 registered popup remote-app-shell quarantine; "
            "MAIN is the only visible GeoGebra application surface\n"
        )
    if "local_picker_boundary=exp23" not in text:
        text += (
            "local_picker_boundary=exp23 suspend embedded B/C topology before DocumentsUI; "
            "restore/reapply layout after direct URI callback; no AvatarSystem recovery\n"
        )
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp23 popup quarantine + pre-picker embedded-topology suspension installed")
