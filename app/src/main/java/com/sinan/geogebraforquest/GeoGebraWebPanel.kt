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
private const val STEREO_CAPTURE_URL =
    "https://appassets.androidplatform.net/assets/web/quest-stereo-capture.js"
private const val STEREO_CAPTURE_ASSET = "web/quest-stereo-capture.js"
private const val APPASSETS_ORIGIN = "https://appassets.androidplatform.net"

/**
 * JavaScript bridge for the single integrated GeoGebra panel.
 *
 * v0.6.5 keeps the normal GeoGebra WebView as the visible/interactive 2D UI.
 * JavaScript captures GeoGebra's actual left- and right-eye 3D render passes and
 * sends only the SBS 3D image to Android. Spatial SDK places that stereo surface
 * over the exact 3D Graphics rectangle, leaving the rest of GeoGebra untouched.
 */
private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
) {
    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        if (spatialMode) {
            SpatialBridgeBus.stereoChanged(enabled)
        }
    }

    @JavascriptInterface
    fun updatePortalRect(json: String) {
        if (spatialMode) {
            SpatialBridgeBus.portalRect(json)
        }
    }

    @JavascriptInterface
    fun submitStereoFrame(dataUrl: String, eyeWidth: Int, eyeHeight: Int) {
        if (spatialMode && dataUrl.isNotBlank()) {
            SpatialBridgeBus.stereoFrame(dataUrl, eyeWidth, eyeHeight)
        }
    }

    /**
     * Kept because the older bootstrap still emits scene JSON. v0.6.5 does not
     * mirror GeoGebra objects as native Spatial SDK meshes.
     */
    @JavascriptInterface
    fun updateScene(@Suppress("UNUSED_PARAMETER") json: String) = Unit

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        if (base64.isNotBlank()) {
            GeoGebraSession.save(context, base64)
        }
    }

    @JavascriptInterface
    fun panelReady() {
        if (spatialMode) {
            SpatialBridgeBus.panelReady()
        }
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

private fun injectFullPanelStereoSafety(view: WebView) {
    view.evaluateJavascript(
        """
        (function () {
          if (document.getElementById('ggq-full-panel-stereo-safety')) return;
          var style = document.createElement('style');
          style.id = 'ggq-full-panel-stereo-safety';
          style.textContent =
            '.ggq-stereo-canvas{opacity:1!important;}' +
            'html[data-ggq-stereo="on"] #ggb-element{background:#fff!important;}';
          (document.head || document.documentElement).appendChild(style);
        })();
        """.trimIndent(),
        null,
    )
}

/**
 * Install the capture script before any page JavaScript executes.
 *
 * This is the important v0.6.5 change. GeoGebra creates its WebGL context very
 * early. Injecting our hook only in onPageFinished is too late to guarantee that
 * GeoGebra has not cached WebGL methods. AndroidX WebKit's document-start API
 * runs the capture script before deployggb.js / GGBApplet creates the renderer.
 */
private fun installStereoCaptureAtDocumentStart(
    view: WebView,
    context: Context,
) {
    if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
        return
    }

    try {
        val script = context.assets
            .open(STEREO_CAPTURE_ASSET)
            .bufferedReader(Charsets.UTF_8)
            .use { reader -> reader.readText() }

        WebViewCompat.addDocumentStartJavaScript(
            view,
            script,
            setOf(APPASSETS_ORIGIN),
        )
    } catch (_: Throwable) {
        // onPageFinished still injects the same script as a fallback.
    }
}

private fun injectQuestScripts(view: WebView) {
    // Keep the ordinary WebView fully visible. The Spatial stereo surface is
    // independently positioned over only the 3D Graphics rectangle.
    injectFullPanelStereoSafety(view)
    injectAssetScript(view, "ggq-projection-patch", PROJECTION_PATCH_URL)

    // Fallback for WebView implementations without DOCUMENT_START_SCRIPT.
    // The v0.6.5 script has a global guard, so this is harmless when the same
    // source already ran at document start.
    injectAssetScript(view, "ggq-stereo-capture", STEREO_CAPTURE_URL)
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
            } catch (e) {}
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
        .addPathHandler(
            "/assets/",
            WebViewAssetLoader.AssetsPathHandler(context),
        )
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
        settings.userAgentString =
            settings.userAgentString + " GeoGebraForQuest/0.6.5"

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

                injectQuestScripts(view)

                val state = GeoGebraSession.load(context)
                if (!state.isNullOrBlank()) {
                    val quoted = JSONObject.quote(state)
                    view.evaluateJavascript(
                        "window.GeoGebraForQuest && window.GeoGebraForQuest.importBase64($quoted);",
                        null,
                    )
                }

                if (spatialMode && startStereo) {
                    bootStereoWhenReady(view)
                }
            }
        }

        addJavascriptInterface(
            QuestBridge(context, spatialMode),
            "QuestBridge",
        )

        // Must happen before loadUrl(): the hook then executes before GeoGebra's
        // own JavaScript and catches the real WebGL context at creation time.
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
                configureGeoGebraWebView(
                    webView = webView,
                    spatialMode = spatialMode,
                    startStereo = startStereo,
                )
            }
        },
    )
}
