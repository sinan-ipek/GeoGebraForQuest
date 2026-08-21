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
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject

private const val LOCAL_APP_URL =
    "https://appassets.androidplatform.net/assets/web/index.html"
private const val PROJECTION_PATCH_URL =
    "https://appassets.androidplatform.net/assets/web/quest-projection-patch.js"
private const val COLOR_PATCH_URL =
    "https://appassets.androidplatform.net/assets/web/quest-color-patch.js"
private const val STEREO_CAPTURE_URL =
    "https://appassets.androidplatform.net/assets/web/quest-stereo-capture.js"
private const val DEBUG_OVERLAY_URL =
    "https://appassets.androidplatform.net/assets/web/quest-debug-overlay.js"
private const val STEREO_CAPTURE_ASSET = "web/quest-stereo-capture.js"
private const val APPASSETS_ORIGIN = "https://appassets.androidplatform.net"

private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
) {
    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        if (spatialMode) SpatialBridgeBus.stereoChanged(enabled)
    }

    @JavascriptInterface
    fun setPortalVisible(visible: Boolean) {
        if (spatialMode) SpatialBridgeBus.portalVisibilityChanged(visible)
    }

    @JavascriptInterface
    fun updatePortalRect(json: String) {
        if (spatialMode) SpatialBridgeBus.portalRect(json)
    }

    @JavascriptInterface
    fun submitStereoFrame(dataUrl: String, eyeWidth: Int, eyeHeight: Int) {
        if (spatialMode && dataUrl.isNotBlank()) {
            SpatialBridgeBus.stereoFrame(dataUrl, eyeWidth, eyeHeight)
        }
    }

    @JavascriptInterface
    fun getStereoDebugStatus(): String = StereoDebugState.toJson()

    @JavascriptInterface
    fun updateScene(@Suppress("UNUSED_PARAMETER") json: String) = Unit

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

/**
 * v0.7.4 returns to the architecture that actually produced Quest depth:
 * the LeftRight media portal is rendered in front of the 3D rectangle.
 *
 * While stereo is active the original GeoGebra WebGL canvas is made almost
 * transparent. It stays in the DOM and remains pointer-interactive, so when the
 * front media panel is made non-hittable the controller ray can continue to the
 * real GeoGebra canvas behind it. We no longer try to punch alpha through the
 * complete Android WebView panel; that underlay approach was the reason v0.7.2
 * and v0.7.3 presented valid eye frames without visible depth.
 */
private fun injectStereoOverlayCss(view: WebView) {
    view.evaluateJavascript(
        """
        (function () {
          if (document.getElementById('ggq-stereo-overlay-css')) return;
          var style = document.createElement('style');
          style.id = 'ggq-stereo-overlay-css';
          style.textContent =
            'html[data-ggq-stereo="on"] .ggq-stereo-canvas{' +
              'opacity:0.001!important;' +
              'pointer-events:auto!important;' +
            '}' +
            'html[data-ggq-stereo="off"] .ggq-stereo-canvas{' +
              'opacity:1!important;' +
            '}';
          (document.head || document.documentElement).appendChild(style);
        })();
        """.trimIndent(),
        null,
    )
}

private fun installStereoCaptureAtDocumentStart(view: WebView, context: Context) {
    if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) return

    try {
        val script = context.assets
            .open(STEREO_CAPTURE_ASSET)
            .bufferedReader(Charsets.UTF_8)
            .use { it.readText() }

        WebViewCompat.addDocumentStartJavaScript(
            view,
            script,
            setOf(APPASSETS_ORIGIN),
        )
    } catch (_: Throwable) {
        // onPageFinished injects the same script as fallback.
    }
}

private fun injectQuestScripts(view: WebView) {
    injectStereoOverlayCss(view)
    injectAssetScript(view, "ggq-projection-patch", PROJECTION_PATCH_URL)
    injectAssetScript(view, "ggq-color-patch", COLOR_PATCH_URL)
    injectAssetScript(view, "ggq-stereo-capture", STEREO_CAPTURE_URL)
    injectAssetScript(view, "ggq-debug-overlay", DEBUG_OVERLAY_URL)
}

private fun bootStereoWhenReady(view: WebView) {
    view.evaluateJavascript(
        """
        (function () {
          if (window.__ggqStereoBootTimer) clearInterval(window.__ggqStereoBootTimer);
          var attempts = 0;
          window.__ggqStereoBootTimer = setInterval(function () {
            attempts++;
            try {
              if (window.GeoGebraQuestStereoCapture &&
                  typeof window.GeoGebraQuestStereoCapture.enable === 'function') {
                window.GeoGebraQuestStereoCapture.enable();
              } else if (window.GeoGebraForQuest &&
                         typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
                window.GeoGebraForQuest.setStereoEnabled(true);
              }
              if (document.documentElement.dataset.ggqStereo === 'on' || attempts > 100) {
                clearInterval(window.__ggqStereoBootTimer);
                window.__ggqStereoBootTimer = null;
              }
            } catch (_) {}
          }, 250);
        })();
        """.trimIndent(),
        null,
    )
}

@SuppressLint("SetJavaScriptEnabled")
fun configureGeoGebraWebView(
    webView: WebView,
    spatialMode: Boolean,
    startStereo: Boolean,
) {
    val context = webView.context
    val assetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()

    webView.apply {
        setLayerType(View.LAYER_TYPE_HARDWARE, null)
        setBackgroundColor(if (spatialMode) Color.TRANSPARENT else Color.WHITE)

        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        settings.mediaPlaybackRequiresUserGesture = false
        settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.7.4"

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

                if (spatialMode && startStereo) bootStereoWhenReady(view)
            }
        }

        addJavascriptInterface(QuestBridge(context, spatialMode), "QuestBridge")
        installStereoCaptureAtDocumentStart(this, context)
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
