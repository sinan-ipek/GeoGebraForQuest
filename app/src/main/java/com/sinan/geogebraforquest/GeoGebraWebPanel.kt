package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject

/** Messages from the embedded local GeoGebra page to Android. */
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
            WebView(context).apply {
                setBackgroundColor(Color.TRANSPARENT)

                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.allowFileAccess = true
                settings.allowContentAccess = true
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.mediaPlaybackRequiresUserGesture = false
                settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.1"

                CookieManager.getInstance().setAcceptCookie(true)
                CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

                webChromeClient = WebChromeClient()
                webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView, url: String) {
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

                // The HTML shell is always local. It prefers a local Math Apps Bundle
                // when present and falls back to GeoGebra's official CDN otherwise.
                loadUrl("file:///android_asset/web/index.html")
            }
        },
    )
}
