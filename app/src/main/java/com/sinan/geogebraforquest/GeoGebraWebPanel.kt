package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
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

/** Messages from the embedded GeoGebra page to Android. */
private class QuestBridge(
    private val context: Context,
    private val spatialMode: Boolean,
    private val onPortalChanged: (Boolean) -> Unit,
) {
    @JavascriptInterface
    fun enterSpatial(base64: String) {
        GeoGebraSession.save(context, base64)
        if (!spatialMode) {
            val intent = Intent(context, SpatialGeoGebraActivity::class.java).apply {
                action = Intent.ACTION_MAIN
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        } else {
            onPortalChanged(true)
        }
    }

    @JavascriptInterface
    fun setPortalEnabled(enabled: Boolean) {
        onPortalChanged(enabled)
    }

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        GeoGebraSession.save(context, base64)
    }

    @JavascriptInterface
    fun returnToPanel(base64: String) {
        GeoGebraSession.save(context, base64)
        if (spatialMode) {
            (context as? Activity)?.finish()
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeoGebraWebPanel(
    spatialMode: Boolean,
    onPortalChanged: (Boolean) -> Unit = {},
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
                // Keep startup completely opaque and identical to the proven v0.1.2 path.
                setBackgroundColor(Color.WHITE)

                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.mediaPlaybackRequiresUserGesture = false
                settings.userAgentString =
                    settings.userAgentString + " GeoGebraForQuest/0.2.2"

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

                        view.evaluateJavascript(
                            "window.GeoGebraForQuest && window.GeoGebraForQuest.setSpatialMode(${if (spatialMode) "true" else "false"});",
                            null,
                        )
                    }
                }

                addJavascriptInterface(
                    QuestBridge(context, spatialMode, onPortalChanged),
                    "QuestBridge",
                )

                loadUrl(LOCAL_APP_URL)
            }
        },
    )
}
