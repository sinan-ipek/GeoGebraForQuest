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
private const val PROJECTION_PATCH_URL =
    "https://appassets.androidplatform.net/assets/web/quest-projection-patch.js"

/**
 * JavaScript bridge for the single-activity integrated portal architecture.
 *
 * There is deliberately no Activity launch here. The application is already
 * running inside Spatial SDK from startup. Selecting the replacement
 * Anaglyph/headset control only switches the existing 3D Graphics viewport
 * between normal flat WebGL and the native spatial stereo portal.
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
    fun updateScene(json: String) {
        if (spatialMode) {
            SpatialBridgeBus.sceneChanged(json)
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
        if (spatialMode) {
            SpatialBridgeBus.panelReady()
        }
    }
}

private fun injectProjectionPatch(view: WebView) {
    val patchUrl = JSONObject.quote(PROJECTION_PATCH_URL)
    view.evaluateJavascript(
        """
        (function () {
          if (window.__ggqProjectionPatchInjected) return;
          window.__ggqProjectionPatchInjected = true;
          var script = document.createElement('script');
          script.id = 'ggq-projection-patch';
          script.src = $patchUrl;
          script.async = false;
          script.onerror = function () {
            window.__ggqProjectionPatchInjected = false;
            console.error('[GeoGebraForQuest] projection patch could not be loaded');
          };
          (document.head || document.documentElement).appendChild(script);
        })();
        """.trimIndent(),
        null,
    )
}

private fun bootStereoWhenReady(view: WebView) {
    view.evaluateJavascript(
        """
        (function () {
          if (window.__ggqStereoBootTimer) {
            clearInterval(window.__ggqStereoBootTimer);
          }
          var attempts = 0;
          window.__ggqStereoBootTimer = setInterval(function () {
            attempts++;
            try {
              if (window.GeoGebraForQuest &&
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
            settings.userAgentString + " GeoGebraForQuest/0.4.1"

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

                injectProjectionPatch(view)

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
