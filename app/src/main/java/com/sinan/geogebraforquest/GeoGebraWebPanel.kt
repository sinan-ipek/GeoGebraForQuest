package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import org.json.JSONObject

private const val LOCAL_APP_URL =
    "https://appassets.androidplatform.net/assets/web/index.html"

/**
 * JavaScript bridge between the local GeoGebra app and Horizon/Spatial SDK.
 *
 * v0.2.1 starts in the proven ordinary 2D panel. When the replacement Stereo 3D
 * projection is selected, the bridge opens the spatial host. The spatial host
 * presents the same GeoGebra UI and reveals native stereo only through the 3D
 * Graphics viewport.
 */
private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
    private val onStereoChanged: (Boolean) -> Unit,
    private val onPortalRect: (String) -> Unit,
    private val onSceneChanged: (String) -> Unit,
    private val onReady: () -> Unit,
) {
    private var spatialLaunchRequested = false

    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        if (spatialMode) {
            onStereoChanged(enabled)
            return
        }

        if (enabled && !spatialLaunchRequested) {
            spatialLaunchRequested = true
            // The page continuously snapshots the .ggb state into GeoGebraSession.
            // A short delay lets the most recent snapshot finish before switching.
            Handler(Looper.getMainLooper()).postDelayed({
                val intent = Intent(context, SpatialGeoGebraActivity::class.java).apply {
                    action = Intent.ACTION_MAIN
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
            }, 350L)
        }
    }

    @JavascriptInterface
    fun updatePortalRect(json: String) {
        if (spatialMode) {
            onPortalRect(json)
        }
    }

    @JavascriptInterface
    fun updateScene(json: String) {
        if (spatialMode) {
            onSceneChanged(json)
        }
    }

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        if (base64.isNotBlank()) {
            GeoGebraSession.save(context, base64)
        }
    }

    @JavascriptInterface
    fun panelReady() {
        onReady()
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeoGebraWebPanel(
    spatialMode: Boolean = false,
    onStereoChanged: (Boolean) -> Unit = {},
    onPortalRect: (String) -> Unit = {},
    onSceneChanged: (String) -> Unit = {},
    onReady: () -> Unit = {},
) {
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { context ->
            val assetLoader = WebViewAssetLoader.Builder()
                .addPathHandler(
                    "/assets/",
                    WebViewAssetLoader.AssetsPathHandler(context),
                )
                .build()

            WebView(context).apply {
                setBackgroundColor(if (spatialMode) Color.TRANSPARENT else Color.WHITE)

                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.mediaPlaybackRequiresUserGesture = false
                settings.userAgentString =
                    settings.userAgentString + " GeoGebraForQuest/0.2.1"

                CookieManager.getInstance().setAcceptCookie(true)
                CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

                webChromeClient = WebChromeClient()
                webViewClient = object : WebViewClientCompat() {
                    override fun shouldInterceptRequest(
                        view: WebView,
                        request: WebResourceRequest,
                    ): WebResourceResponse? {
                        return assetLoader.shouldInterceptRequest(request.url)
                    }

                    @Suppress("DEPRECATION")
                    override fun shouldInterceptRequest(
                        view: WebView,
                        url: String,
                    ): WebResourceResponse? {
                        return assetLoader.shouldInterceptRequest(Uri.parse(url))
                    }

                    override fun onPageFinished(view: WebView, url: String) {
                        super.onPageFinished(view, url)

                        val state = GeoGebraSession.load(context)
                        if (!state.isNullOrBlank()) {
                            val quoted = JSONObject.quote(state)
                            view.evaluateJavascript(
                                "window.GeoGebraForQuest && window.GeoGebraForQuest.importBase64($quoted);",
                                null,
                            )
                        }

                        // Wait for the GeoGebra API, report readiness, and keep a recent
                        // construction snapshot. This lets the 2D -> spatial transition
                        // preserve the same work without modifying GeoGebra's own UI.
                        val bootScript = """
                            (function ggqBoot(){
                              if (window.ggbApplet && typeof window.ggbApplet.getBase64 === 'function') {
                                try { QuestBridge.panelReady(); } catch(e) {}
                                if (!window.__ggqAutoSave) {
                                  window.__ggqAutoSave = setInterval(function(){
                                    try {
                                      window.ggbApplet.getBase64(function(b64){
                                        if (b64) QuestBridge.saveConstruction(b64);
                                      });
                                    } catch(e) {}
                                  }, 500);
                                }
                                ${if (spatialMode) "setTimeout(function(){ if(window.GeoGebraForQuest){ window.GeoGebraForQuest.setStereoEnabled(true); } }, 450);" else ""}
                              } else {
                                setTimeout(ggqBoot, 200);
                              }
                            })();
                        """.trimIndent()
                        view.evaluateJavascript(bootScript, null)
                    }
                }

                addJavascriptInterface(
                    QuestBridge(
                        context = context,
                        spatialMode = spatialMode,
                        onStereoChanged = onStereoChanged,
                        onPortalRect = onPortalRect,
                        onSceneChanged = onSceneChanged,
                        onReady = onReady,
                    ),
                    "QuestBridge",
                )

                loadUrl(LOCAL_APP_URL)
            }
        },
    )
}
