package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.net.Uri
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
 * Messages from the embedded GeoGebra page to the Spatial SDK host.
 *
 * v0.3 deliberately keeps the exact Activity/WebView hosting path that already
 * rendered GeoGebra correctly on Quest. The Activity itself is embedded as a
 * Spatial SDK panel; therefore selecting Stereo 3D never launches another window.
 */
private class QuestBridge(
    private val context: Context,
) {
    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        SpatialBridgeBus.stereoChanged(enabled)
    }

    @JavascriptInterface
    fun updatePortalRect(json: String) {
        SpatialBridgeBus.portalRect(json)
    }

    @JavascriptInterface
    fun updateScene(json: String) {
        SpatialBridgeBus.sceneChanged(json)
    }

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        if (base64.isNotBlank()) {
            GeoGebraSession.save(context, base64)
        }
    }

    @JavascriptInterface
    fun panelReady() {
        SpatialBridgeBus.panelReady()
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeoGebraWebPanel() {
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
                // The HTML page is opaque white in normal mode. Keeping the Android
                // backing surface transparent lets the 3D canvas become a real hole
                // only when JavaScript explicitly makes that viewport transparent.
                setBackgroundColor(Color.TRANSPARENT)

                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.mediaPlaybackRequiresUserGesture = false
                settings.userAgentString =
                    settings.userAgentString + " GeoGebraForQuest/0.3.0"

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
                    }
                }

                addJavascriptInterface(
                    QuestBridge(context),
                    "QuestBridge",
                )

                loadUrl(LOCAL_APP_URL)
            }
        },
    )
}
