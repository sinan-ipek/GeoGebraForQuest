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
 * Bridge used by the embedded, local GeoGebra web app.
 *
 * v0.2 has no "open a second VR activity" call. The application already runs in
 * Spatial SDK from the beginning; the replacement headset icon simply turns the
 * current GeoGebra 3D viewport into a transparent stereo portal.
 */
private class QuestBridge(
    private val context: Context,
    private val onStereoChanged: (Boolean) -> Unit,
    private val onPortalRect: (String) -> Unit,
    private val onSceneChanged: (String) -> Unit,
) {
    @JavascriptInterface
    fun setStereoEnabled(enabled: Boolean) {
        onStereoChanged(enabled)
    }

    @JavascriptInterface
    fun updatePortalRect(json: String) {
        onPortalRect(json)
    }

    @JavascriptInterface
    fun updateScene(json: String) {
        onSceneChanged(json)
    }

    @JavascriptInterface
    fun saveConstruction(base64: String) {
        GeoGebraSession.save(context, base64)
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeoGebraWebPanel(
    onStereoChanged: (Boolean) -> Unit = {},
    onPortalRect: (String) -> Unit = {},
    onSceneChanged: (String) -> Unit = {},
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
                // The Spatial SDK panel itself supports transparency. GeoGebra still paints
                // its ordinary UI opaque; only the 3D WebGL canvas is made transparent by JS
                // while Stereo 3D is enabled.
                setBackgroundColor(Color.TRANSPARENT)

                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.mediaPlaybackRequiresUserGesture = false
                settings.userAgentString =
                    settings.userAgentString + " GeoGebraForQuest/0.2.0"

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
                    QuestBridge(
                        context = context,
                        onStereoChanged = onStereoChanged,
                        onPortalRect = onPortalRect,
                        onSceneChanged = onSceneChanged,
                    ),
                    "QuestBridge",
                )

                loadUrl(LOCAL_APP_URL)
            }
        },
    )
}
