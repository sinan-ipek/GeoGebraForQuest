#!/usr/bin/env python3
"""Exp27: freeze Bug 1 and replace embedded DocumentsUI with a true cold-process handoff.

Bug 1
-----
Frozen exactly at Exp25/26. No popup/login/navigation behavior is modified.

Bug 2
-----
Exp26 video proved that the ActivityPanel DocumentsUI receives ray hover but does
not accept controller click. Do not keep tuning panel input. Exp27 removes the
picker from the Spatial panel path entirely:

1. MAIN launches a tiny non-spatial picker proxy in a separate :localpicker process.
2. The proxy opens ordinary Android ACTION_OPEN_DOCUMENT.
3. Once DocumentsUI is up, the proxy terminates the old main app process so the
   old OpenXR/VRFeature/controller session cannot be resumed.
4. The chosen .ggb is copied atomically into app-private storage.
5. The proxy starts a brand-new SpatialGeoGebraActivity task/process.
6. The fresh local patched AppW opens the staged file from a same-origin
   appassets URL (/pending-cold/local.ggb).

This is intentionally different from Exp20 Activity.recreate(): the old VR process
is discarded instead of reused/recreated in place.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp27.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
manifest_path = root / "app/src/main/AndroidManifest.xml"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
cold_path = root / "app/src/main/java/com/sinan/geogebraforquest/ColdLocalFilePickerActivity.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
manifest = manifest_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# BUG 2A: MAIN no longer creates/uses the embedded ActivityPanel picker.
# The WebView file input is deliberately cancelled because the old WebView/process
# will be destroyed. The selected file will be reopened automatically in fresh MAIN.
# ---------------------------------------------------------------------------
old_launch = '''            if (activity is SpatialGeoGebraActivity) {
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
new_launch = '''            if (activity is SpatialGeoGebraActivity) {
                // EXP27_COLD_PROCESS_PICKER: the current WebView callback belongs to
                // the VR process that will be intentionally discarded. Cancel it,
                // then let the separate picker process stage the chosen .ggb.
                pendingCallback = null
                callback.onReceiveValue(null)
                activity.startActivity(
                    Intent(activity, ColdLocalFilePickerActivity::class.java),
                )
                true
            } else {
                // Non-spatial development fallback only.
                @Suppress("DEPRECATION")
                activity.startActivityForResult(intent, REQUEST_CODE)
                true
            }
'''
if old_launch in panel:
    panel = panel.replace(old_launch, new_launch, 1)
elif "EXP27_COLD_PROCESS_PICKER" not in panel:
    raise RuntimeError("exp27 could not replace Exp24 spatial picker launch")

# ---------------------------------------------------------------------------
# BUG 2B: same-origin persistent staged-file loader for the fresh MAIN process.
# ---------------------------------------------------------------------------
if "EXP27_OPEN_COLD_PENDING_FILE" not in panel:
    anchor = "    fun handleBack(): Boolean {\n"
    helper = r'''    // EXP27_OPEN_COLD_PENDING_FILE: only the fresh local MAIN consumes the
    // ready marker. The actual file remains on disk while AppW fetches it through
    // the appassets path handler, so deleting the marker cannot race the fetch.
    private var coldLocalOpenInFlight = false

    fun openPendingColdLocalFileIfAny() {
        val main = mainWebView.get() ?: return
        val context = main.context.applicationContext
        if (!ColdLocalFileBridge.hasPending(context) || coldLocalOpenInFlight) return
        coldLocalOpenInFlight = true

        val jsUrl = JSONObject.quote(ColdLocalFileBridge.PENDING_URL)
        var attempts = 0

        fun attemptOpen() {
            attempts++
            main.evaluateJavascript(
                """
                (function () {
                  try {
                    if (window.ggbApplet && typeof window.ggbApplet.openFile === 'function') {
                      window.ggbApplet.openFile($jsUrl);
                      return 'opened';
                    }
                  } catch (_) {}
                  return 'wait';
                })();
                """.trimIndent(),
            ) { result ->
                if (result != null && result.contains("opened")) {
                    ColdLocalFileBridge.consumeReady(context)
                    coldLocalOpenInFlight = false
                } else if (attempts < 180) {
                    main.postDelayed({ attemptOpen() }, 100L)
                } else {
                    coldLocalOpenInFlight = false
                }
            }
        }

        main.post { attemptOpen() }
    }

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp27 navigation helper anchor not found")
    panel = panel.replace(anchor, helper, 1)

# Arm the cold staged-file loader whenever MAIN local AppW finishes a page.
old_inject = '''                    injectControllerContextMenuSupport(view)
'''
new_inject = '''                    injectControllerContextMenuSupport(view)
                    GeoGebraWebNavigation.openPendingColdLocalFileIfAny()
'''
if old_inject in panel and "GeoGebraWebNavigation.openPendingColdLocalFileIfAny()" not in panel:
    panel = panel.replace(old_inject, new_inject, 1)
elif "GeoGebraWebNavigation.openPendingColdLocalFileIfAny()" not in panel:
    raise RuntimeError("exp27 MAIN onPageFinished injection anchor not found")

# Expose the staged file under the local appassets origin.
old_loader = '''    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()
'''
new_loader = '''    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .addPathHandler("/pending-cold/", ColdLocalFilePathHandler(context.applicationContext))
        .build()
'''
if old_loader in panel:
    panel = panel.replace(old_loader, new_loader, 1)
elif 'addPathHandler("/pending-cold/", ColdLocalFilePathHandler' not in panel:
    raise RuntimeError("exp27 asset loader anchor not found")

# ---------------------------------------------------------------------------
# Separate-process picker + persistent staging bridge.
# ---------------------------------------------------------------------------
cold = r'''package com.sinan.geogebraforquest

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.webkit.WebResourceResponse
import androidx.webkit.WebViewAssetLoader
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/** Persistent, cross-process handoff for Exp27 local .ggb loading. */
internal object ColdLocalFileBridge {
    const val PENDING_URL =
        "https://appassets.androidplatform.net/pending-cold/local.ggb"

    private const val DIR_NAME = "ggq_pending_local"
    private const val FILE_NAME = "local.ggb"
    private const val TEMP_NAME = "local.ggb.tmp"
    private const val READY_NAME = "ready"

    private fun dir(context: Context): File =
        File(context.filesDir, DIR_NAME).apply { mkdirs() }

    private fun stagedFile(context: Context): File = File(dir(context), FILE_NAME)
    private fun readyFile(context: Context): File = File(dir(context), READY_NAME)

    fun clearReady(context: Context) {
        try { readyFile(context).delete() } catch (_: Throwable) {}
    }

    fun hasPending(context: Context): Boolean =
        readyFile(context).isFile && stagedFile(context).isFile && stagedFile(context).length() > 0L

    fun consumeReady(context: Context) {
        clearReady(context)
    }

    fun stage(context: Context, uri: Uri): Boolean {
        clearReady(context)
        val directory = dir(context)
        val target = File(directory, FILE_NAME)
        val temp = File(directory, TEMP_NAME)
        try { temp.delete() } catch (_: Throwable) {}

        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(temp).use { output ->
                    input.copyTo(output, 128 * 1024)
                    output.fd.sync()
                }
            } ?: return false

            if (!temp.isFile || temp.length() <= 0L) return false
            try { target.delete() } catch (_: Throwable) {}
            if (!temp.renameTo(target)) {
                FileInputStream(temp).use { input ->
                    FileOutputStream(target).use { output ->
                        input.copyTo(output, 128 * 1024)
                        output.fd.sync()
                    }
                }
                temp.delete()
            }
            if (!target.isFile || target.length() <= 0L) return false
            readyFile(context).writeText("ready")
            true
        } catch (_: Throwable) {
            try { temp.delete() } catch (_: Throwable) {}
            false
        }
    }

    fun webResponse(context: Context, path: String): WebResourceResponse? {
        if (!path.endsWith("local.ggb")) return null
        val file = stagedFile(context)
        if (!file.isFile || file.length() <= 0L) return null
        return try {
            WebResourceResponse(
                "application/vnd.geogebra.file",
                null,
                FileInputStream(file),
            )
        } catch (_: Throwable) {
            null
        }
    }
}

internal class ColdLocalFilePathHandler(
    private val context: Context,
) : WebViewAssetLoader.PathHandler {
    override fun handle(path: String): WebResourceResponse? =
        ColdLocalFileBridge.webResponse(context, path)
}

/**
 * EXP27_COLD_PICKER_PROXY
 *
 * Runs in :localpicker, outside the immersive process. It owns DocumentsUI,
 * kills the stale main process after the picker is visible, stages the selected
 * .ggb, then launches a completely fresh SpatialGeoGebraActivity.
 */
class ColdLocalFilePickerActivity : Activity() {
    companion object {
        private const val REQUEST_OPEN_GGB = 9270
        private const val KILL_MAIN_DELAY_MS = 300L
    }

    private var pickerStarted = false
    private var relaunching = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pickerStarted = savedInstanceState?.getBoolean("pickerStarted") ?: false
        if (!pickerStarted) {
            pickerStarted = true
            launchPicker()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("pickerStarted", pickerStarted)
        super.onSaveInstanceState(outState)
    }

    private fun launchPicker() {
        ColdLocalFileBridge.clearReady(applicationContext)
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        try {
            @Suppress("DEPRECATION")
            startActivityForResult(intent, REQUEST_OPEN_GGB)
            Handler(Looper.getMainLooper()).postDelayed(
                { killOldMainProcessIfAlive() },
                KILL_MAIN_DELAY_MS,
            )
        } catch (_: Throwable) {
            relaunchFreshMain()
        }
    }

    private fun killOldMainProcessIfAlive() {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager ?: return
        val selfPid = Process.myPid()
        val mainProcessName = packageName
        for (process in am.runningAppProcesses.orEmpty()) {
            if (process.pid != selfPid && process.processName == mainProcessName) {
                try { Process.killProcess(process.pid) } catch (_: Throwable) {}
            }
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_OPEN_GGB) return

        if (resultCode == RESULT_OK && data != null) {
            val uri = when {
                data.data != null -> data.data
                data.clipData != null && data.clipData!!.itemCount > 0 ->
                    data.clipData!!.getItemAt(0).uri
                else -> null
            }
            if (uri != null) {
                try {
                    contentResolver.takePersistableUriPermission(
                        uri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                } catch (_: Throwable) {}
                ColdLocalFileBridge.stage(applicationContext, uri)
            }
        } else {
            ColdLocalFileBridge.clearReady(applicationContext)
        }

        relaunchFreshMain()
    }

    private fun relaunchFreshMain() {
        if (relaunching) return
        relaunching = true
        val intent = Intent(this, SpatialGeoGebraActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        try {
            startActivity(intent)
        } finally {
            finish()
        }
    }
}
'''
cold_path.write_text(cold, encoding="utf-8")

# Declare the proxy in its own private process. Keeping the old Exp24 ActivityPanel
# declaration/registration dormant is harmless; Exp27 never requests that panel.
if 'android:name=".ColdLocalFilePickerActivity"' not in manifest:
    anchor = '''        <activity
            android:name=".SpatialFilePickerPanelActivity"
'''
    pos = manifest.find(anchor)
    if pos < 0:
        raise RuntimeError("exp27 manifest picker declaration anchor not found")
    decl = '''        <activity
            android:name=".ColdLocalFilePickerActivity"
            android:process=":localpicker"
            android:exported="false"
            android:excludeFromRecents="true"
            android:theme="@style/PanelAppThemeTransparent" />
'''
    manifest = manifest[:pos] + decl + manifest[pos:]

# ---------------------------------------------------------------------------
# Guards. Bug 1 must be byte-path frozen at its markers; no new navigation logic.
# ---------------------------------------------------------------------------
for required in (
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP22_LOGIN_READY_SUCCESS_HANDSHAKE",
    "EXP20_CANONICAL_MAIN_GUARD",
):
    if required not in panel:
        raise RuntimeError(f"exp27 frozen Bug 1 marker missing: {required}")

for required in (
    "EXP27_COLD_PROCESS_PICKER",
    "EXP27_OPEN_COLD_PENDING_FILE",
    "ColdLocalFilePickerActivity::class.java",
    'addPathHandler("/pending-cold/", ColdLocalFilePathHandler',
    "GeoGebraWebNavigation.openPendingColdLocalFileIfAny()",
):
    if required not in panel:
        raise RuntimeError(f"exp27 panel requirement missing: {required}")

for required in (
    "EXP27_COLD_PICKER_PROXY",
    'android:process=":localpicker"',
):
    target = cold if required.startswith("EXP27") else manifest
    if required not in target:
        raise RuntimeError(f"exp27 cold picker requirement missing: {required}")

for required in (
    "Process.killProcess(process.pid)",
    "ColdLocalFileBridge.stage(applicationContext, uri)",
    "Intent.FLAG_ACTIVITY_CLEAR_TASK",
    "SpatialGeoGebraActivity::class.java",
):
    if required not in cold:
        raise RuntimeError(f"exp27 cold-process behavior missing: {required}")

# Exp27 must not route spatial file selection through the Exp24 ActivityPanel anymore.
launch_pos = panel.find("EXP27_COLD_PROCESS_PICKER")
launch_check = panel[launch_pos:launch_pos + 1200] if launch_pos >= 0 else ""
if "requestSpatialFilePickerPanel()" in launch_check:
    raise RuntimeError("exp27 still routes file selection through ActivityPanel")

panel_path.write_text(panel, encoding="utf-8")
manifest_path.write_text(manifest, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    text = meta.read_text(encoding="utf-8")
    if "local_picker=exp27" not in text:
        text += (
            "local_picker=exp27 separate :localpicker process + ordinary SAF; old main process "
            "killed; selected GGB staged private and opened by fresh MAIN via /pending-cold/\n"
        )
    if "bug1=frozen-exp25" not in text:
        text += "bug1=frozen-exp25 strict popup whitelist; no Exp27 navigation changes\n"
    meta.write_text(text, encoding="utf-8")

print("[GGQ] exp27 cold-process local-file handoff installed; Bug 1 frozen")
