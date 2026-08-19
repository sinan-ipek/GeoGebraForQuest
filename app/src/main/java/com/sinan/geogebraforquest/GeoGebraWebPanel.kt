package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.app.Activity
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
private const val PROJECTION_PATCH_URL =
    "https://appassets.androidplatform.net/assets/web/quest-projection-patch.js"

/**
 * Bridge between the local GeoGebra web app and Android/Spatial SDK.
 *
 * In normal panel mode a Stereo request starts the immersive host using the same
 * transition pattern as Meta's official HybridSample. In the immersive host the
 * exact same JavaScript calls are routed to the native stereo portal renderer.
 */
private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
) {
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var spatialLaunchRequested = false

    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        if (spatialMode) {
            SpatialBridgeBus.stereoChanged(enabled)
            return
        }

        if (!enabled || spatialLaunchRequested) {
            return
        }

        spatialLaunchRequested = true
        mainHandler.post {
            try {
                val intent = Intent(context, SpatialGeoGebraActivity::class.java).apply {
                    action = Intent.ACTION_MAIN
                    putExtra(SpatialGeoGebraActivity.EXTRA_START_STEREO, true)
                    if (context !is Activity) {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                }
                context.startActivity(intent)
            } catch (_: Throwable) {
                // Keep the 2D GeoGebra panel alive even if Horizon rejects the
                // immersive transition for any reason. A later tap can retry.
                spatialLaunchRequested = false
            }
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

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeoGebraWebPanel(
    spatialMode: Boolean,
    startStereo: Boolean,
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
                    settings.userAgentString + " GeoGebraForQuest/0.3.4"

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

                        // GeoGebra's current web UI paints projection icons as CSS
                        // background images. v0.3.4 injects a dedicated patch that
                        // identifies the real four-item projection table and replaces
                        // only the Anaglyph/Glasses item with the Quest headset icon.
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
                            // onPageFinished occurs before GeoGebra's applet necessarily has a
                            // visible 3D WebGL canvas. Retry inside the page until the existing
                            // 3D Graphics viewport exists, then enable only that stereo portal.
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
                                      if (document.documentElement.dataset.ggqStereo === 'on' || attempts > 80) {
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
                    }
                }

                addJavascriptInterface(
                    QuestBridge(context, spatialMode),
                    "QuestBridge",
                )

                loadUrl(LOCAL_APP_URL)
            }
        },
    )
}
