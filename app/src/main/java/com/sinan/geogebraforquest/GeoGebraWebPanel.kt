package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.net.Uri
import android.view.View
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
private const val STEREO_LAYOUT_URL =
    "https://appassets.androidplatform.net/assets/web/quest-stereo-layout.js"

private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
) {
    @JavascriptInterface
    fun updateStereoLayout(json: String) {
        if (spatialMode && json.isNotBlank()) {
            SpatialBridgeBus.stereoLayout(json)
        }
    }

    @JavascriptInterface
    fun getStereoDebugStatus(): String = StereoDebugState.toJson()

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        if (base64.isNotBlank()) GeoGebraSession.save(context, base64)
    }

    @JavascriptInterface
    fun panelReady() {
        if (spatialMode) SpatialBridgeBus.panelReady()
    }
}

private fun injectAssetScript(view: WebView, id: String, url: String) {
    val quotedId = JSONObject.quote(id)
    val quotedUrl = JSONObject.quote(url)
    view.evaluateJavascript(
        """
        (function () {
          if (document.getElementById($quotedId)) return;
          var script = document.createElement('script');
          script.id = $quotedId;
          script.src = $quotedUrl;
          script.async = false;
          script.onerror = function () {
            try { script.remove(); } catch (e) {}
            console.error('[GeoGebraForQuest] could not load ' + $quotedUrl);
          };
          (document.head || document.documentElement).appendChild(script);
        })();
        """.trimIndent(),
        null,
    )
}

private fun injectQuestScripts(view: WebView) {
    // Source-built GeoGebra already runs PROJECTION_QUEST_STEREO.  This script
    // reports layout only; it never touches WebGL pixels or projection state.
    injectAssetScript(view, "ggq-stereo-layout", STEREO_LAYOUT_URL)
}

@SuppressLint("SetJavaScriptEnabled")
fun configureGeoGebraWebView(
    webView: WebView,
    spatialMode: Boolean,
    @Suppress("UNUSED_PARAMETER") startStereo: Boolean,
) {
    val context = webView.context
    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()

    webView.apply {
        setLayerType(View.LAYER_TYPE_HARDWARE, null)
        setBackgroundColor(Color.WHITE)

        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        settings.mediaPlaybackRequiresUserGesture = false
        settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.9.0"

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

        webChromeClient = WebChromeClient()
        webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest,
            ): WebResourceResponse? = assetLoader.shouldInterceptRequest(request.url)

            @Suppress("DEPRECATION")
            override fun shouldInterceptRequest(
                view: WebView,
                url: String,
            ): WebResourceResponse? = assetLoader.shouldInterceptRequest(Uri.parse(url))

            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                injectQuestScripts(view)

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

        addJavascriptInterface(QuestBridge(context, spatialMode), "QuestBridge")
        loadUrl(LOCAL_APP_URL)
    }
}

@Composable
fun GeoGebraWebPanel(
    spatialMode: Boolean,
    startStereo: Boolean,
) {
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { context ->
            WebView(context).also { webView ->
                configureGeoGebraWebView(webView, spatialMode, startStereo)
            }
        },
    )
}
