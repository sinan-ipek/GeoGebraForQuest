#!/usr/bin/env python3
"""Exp20: keep MAIN on the patched local Classic and rebuild XR after local file picking.

Single hypothesis: failures happen when the app leaves its canonical runtime
(local patched AppW + fresh Spatial/VR controller state) and does not return to
exactly that state.

Exp20 therefore applies one policy:
- MAIN WebView may not become a remote geogebra.org site shell. Remote material
  URLs are handed to the existing local ggbApplet.openFile bridge; other remote
  GeoGebra navigations are consumed.
- Login/material popups remain remote-capable and exp15/17/19 still own token and
  material handoff.
- ACTION_OPEN_DOCUMENT is treated as a hard runtime boundary. The selected .ggb
  bytes are staged in-process, the Activity is recreated (fresh VRFeature,
  controller entities, ray and panels), and the new local AppW opens the staged
  file from a private appassets URL.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp20.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Imports + constants for the staged local file virtual URL.
# ---------------------------------------------------------------------------
if "java.io.ByteArrayInputStream" not in panel:
    anchor = "import java.lang.ref.WeakReference\n"
    if anchor not in panel:
        raise RuntimeError("exp20 import anchor not found")
    panel = panel.replace(anchor, "import java.io.ByteArrayInputStream\n" + anchor, 1)

if "PENDING_LOCAL_GGB_URL" not in panel:
    anchor = 'private const val LOCAL_ASSET_HOST = "appassets.androidplatform.net"\n'
    insert = anchor + (
        'private const val PENDING_LOCAL_GGB_URL =\n'
        '    "https://appassets.androidplatform.net/pending/local.ggb"\n'
    )
    if anchor not in panel:
        raise RuntimeError("exp20 LOCAL_ASSET_HOST anchor not found")
    panel = panel.replace(anchor, insert, 1)

# ---------------------------------------------------------------------------
# Staged local file store + appassets path handler.
# ---------------------------------------------------------------------------
if "EXP20_PENDING_LOCAL_FILE" not in panel:
    anchor = "object GeoGebraLocalFilePicker {\n"
    insert = r'''// EXP20_PENDING_LOCAL_FILE: survives Activity.recreate() because the process
// remains alive. The bytes are exposed exactly once through a private appassets
// URL to the freshly-created local patched AppW.
private object GeoGebraPendingLocalFile {
    @Volatile
    private var bytes: ByteArray? = null

    fun stage(value: ByteArray) {
        bytes = value
    }

    fun hasPending(): Boolean = bytes != null

    fun consume(): ByteArray? {
        val value = bytes
        bytes = null
        return value
    }
}

private class PendingLocalFilePathHandler : WebViewAssetLoader.PathHandler {
    override fun handle(path: String): WebResourceResponse? {
        if (!path.endsWith("local.ggb")) return null
        val bytes = GeoGebraPendingLocalFile.consume() ?: return null
        return WebResourceResponse(
            "application/vnd.geogebra.file",
            null,
            ByteArrayInputStream(bytes),
        )
    }
}

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp20 local picker anchor not found")
    panel = panel.replace(anchor, insert, 1)

# ---------------------------------------------------------------------------
# Replace ordinary SAF callback continuation with a canonical-runtime restart.
# ---------------------------------------------------------------------------
start = panel.find("    fun handleActivityResult(\n")
end = panel.find("    fun cancelPending()", start)
if start < 0 or end < 0:
    raise RuntimeError("exp20 could not locate GeoGebraLocalFilePicker.handleActivityResult")

old_block = panel[start:end]
if "EXP20_CANONICAL_FILE_RESTART" not in old_block:
    new_block = r'''    // EXP20_CANONICAL_FILE_RESTART: do not resume the old Spatial/OpenXR
    // runtime after DocumentsUI. Stage the chosen file, cancel WebView's original
    // file-input callback, then recreate the Activity so VRFeature/controllers/ray
    // and all panels are created from a clean canonical state.
    fun handleActivityResult(
        activity: Activity,
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ): Boolean {
        if (requestCode != REQUEST_CODE) return false

        val callback = pendingCallback
        pendingCallback = null
        callback?.onReceiveValue(null)

        if (resultCode == Activity.RESULT_OK && data != null) {
            val uri = when {
                data.data != null -> data.data
                data.clipData != null && data.clipData!!.itemCount > 0 ->
                    data.clipData!!.getItemAt(0).uri
                else -> null
            }

            if (uri != null) {
                try {
                    val bytes = activity.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    if (bytes != null && bytes.isNotEmpty()) {
                        GeoGebraPendingLocalFile.stage(bytes)
                    }
                } catch (_: Throwable) {
                }
            }
        }

        activity.recreate()
        return true
    }

'''
    panel = panel[:start] + new_block + panel[end:]

# ---------------------------------------------------------------------------
# MAIN local app loader for the staged file after Activity recreation.
# ---------------------------------------------------------------------------
if "EXP20_OPEN_STAGED_LOCAL_FILE" not in panel:
    anchor = "    fun handleBack(): Boolean {\n"
    insert = r'''    // EXP20_OPEN_STAGED_LOCAL_FILE: the newly-created MAIN local AppW loads the
    // selected .ggb through the private same-origin appassets path. Retrying here
    // only waits for ggbApplet to finish booting; no remote GeoGebra page is used.
    fun openPendingLocalFileIfAny() {
        if (!GeoGebraPendingLocalFile.hasPending()) return
        val main = mainWebView.get() ?: return
        val jsUrl = JSONObject.quote(PENDING_LOCAL_GGB_URL)
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var url = $jsUrl;
                  var attempts = 0;
                  function tryOpen() {
                    attempts++;
                    try {
                      if (window.ggbApplet && typeof window.ggbApplet.openFile === 'function') {
                        window.ggbApplet.openFile(url);
                        return true;
                      }
                    } catch (_) {}
                    return false;
                  }
                  if (!tryOpen()) {
                    var timer = window.setInterval(function () {
                      if (tryOpen() || attempts >= 120) window.clearInterval(timer);
                    }, 100);
                  }
                })();
                """.trimIndent(),
                null,
            )
        }
    }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp20 navigation handleBack anchor not found")
    panel = panel.replace(anchor, insert, 1)

# ---------------------------------------------------------------------------
# MAIN navigation guard. Login popup remains exempt because registerAsMain=false.
# ---------------------------------------------------------------------------
if "EXP20_CANONICAL_MAIN_GUARD" not in panel:
    anchor = "private fun refreshImeConnection(view: View) {\n"
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

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp20 refreshImeConnection anchor not found")
    panel = panel.replace(anchor, helpers, 1)

panel = panel.replace(
    "): Boolean = handleGeoGebraLoginCallback(view, request.url)",
    "): Boolean = handleGeoGebraNavigation(view, request.url, registerAsMain)",
)
panel = panel.replace(
    "handleGeoGebraLoginCallback(view, Uri.parse(url))",
    "handleGeoGebraNavigation(view, Uri.parse(url), registerAsMain)",
)

# Add a fallback for redirects/navigation types WebView may not expose through
# shouldOverrideUrlLoading. If MAIN ever begins a remote GeoGebra page, stop it
# and return to history/local Classic rather than allowing the site shell to own A.
if "EXP20_REMOTE_ESCAPE_FALLBACK" not in panel:
    anchor = '''            override fun onPageFinished(view: WebView, url: String) {
'''
    fallback = r'''            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                if (registerAsMain) {
                    val uri = Uri.parse(url)
                    if (isRemoteGeoGebraUri(uri)) {
                        // EXP20_REMOTE_ESCAPE_FALLBACK
                        view.stopLoading()
                        view.post {
                            if (view.canGoBack()) {
                                view.goBack()
                            } else {
                                view.loadUrl(LOCAL_APP_URL)
                            }
                        }
                    }
                }
            }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp20 onPageFinished anchor not found")
    panel = panel.replace(anchor, fallback, 1)

# When the fresh local app reaches a finished document, arm the staged-file loader.
old = '''                if (registerAsMain) {
                    injectControllerContextMenuSupport(view)
                }
'''
new = '''                if (registerAsMain) {
                    injectControllerContextMenuSupport(view)
                    GeoGebraWebNavigation.openPendingLocalFileIfAny()
                }
'''
if old in panel:
    panel = panel.replace(old, new, 1)
elif "GeoGebraWebNavigation.openPendingLocalFileIfAny()" not in panel:
    raise RuntimeError("exp20 main onPageFinished anchor not found")

# Dynamic same-origin handler for the staged .ggb.
old_loader = '''    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()
'''
new_loader = '''    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .addPathHandler("/pending/", PendingLocalFilePathHandler())
        .build()
'''
if old_loader in panel:
    panel = panel.replace(old_loader, new_loader, 1)
elif 'addPathHandler("/pending/", PendingLocalFilePathHandler())' not in panel:
    raise RuntimeError("exp20 assetLoader anchor not found")

# Activity callback must pass itself so the picker can stage bytes and recreate.
old_activity_call = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            recoverSpatialInputAfterExternalActivity()
            return
        }
'''
new_activity_call = '''        if (GeoGebraLocalFilePicker.handleActivityResult(this, requestCode, resultCode, data)) {
            return
        }
'''
if old_activity_call in activity:
    activity = activity.replace(old_activity_call, new_activity_call, 1)
else:
    old_activity_call2 = '''        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
'''
    if old_activity_call2 in activity:
        activity = activity.replace(old_activity_call2, new_activity_call, 1)
    elif "GeoGebraLocalFilePicker.handleActivityResult(this, requestCode" not in activity:
        raise RuntimeError("exp20 Activity onActivityResult anchor not found")

for required in (
    "EXP20_PENDING_LOCAL_FILE",
    "EXP20_CANONICAL_FILE_RESTART",
    "activity.recreate()",
    "EXP20_OPEN_STAGED_LOCAL_FILE",
    "PENDING_LOCAL_GGB_URL",
    'addPathHandler("/pending/", PendingLocalFilePathHandler())',
    "EXP20_CANONICAL_MAIN_GUARD",
    "handleGeoGebraNavigation(view, request.url, registerAsMain)",
    "EXP20_REMOTE_ESCAPE_FALLBACK",
    "GeoGebraWebNavigation.openPendingLocalFileIfAny()",
):
    if required not in panel:
        raise RuntimeError(f"exp20 panel requirement missing: {required}")

if "GeoGebraLocalFilePicker.handleActivityResult(this, requestCode" not in activity:
    raise RuntimeError("exp20 activity callback was not canonicalized")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "canonical_runtime=exp20" not in text:
        text += (
            "canonical_runtime=exp20 MAIN local-Classic remote guard; "
            "local picker stages GGB then Activity.recreate fresh XR runtime\n"
        )
        meta.write_text(text, encoding="utf-8")

print("[GGQ] exp20 canonical runtime guard + staged local-file restart installed")
