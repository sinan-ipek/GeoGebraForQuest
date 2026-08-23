package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.Uri
import android.os.Message
import android.view.View
import android.view.ViewGroup
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
import java.lang.ref.WeakReference
import org.json.JSONObject

private const val LOCAL_APP_URL =
    "https://appassets.androidplatform.net/assets/web/index.html"
private const val STEREO_LAYOUT_URL =
    "https://appassets.androidplatform.net/assets/web/quest-stereo-layout.js"

object GeoGebraWebNavigation {
    private var mainWebView = WeakReference<WebView>(null)
    private val popupWebViews = mutableListOf<WeakReference<WebView>>()

    fun registerMain(webView: WebView) {
        mainWebView = WeakReference(webView)
    }

    fun registerPopup(webView: WebView) {
        cleanupPopups()
        popupWebViews.add(WeakReference(webView))
    }

    fun unregisterPopup(webView: WebView) {
        popupWebViews.removeAll { reference ->
            val candidate = reference.get()
            candidate == null || candidate === webView
        }
    }

    private fun cleanupPopups() {
        popupWebViews.removeAll { it.get() == null }
    }

    private fun currentPopup(): WebView? {
        cleanupPopups()
        for (index in popupWebViews.indices.reversed()) {
            val candidate = popupWebViews[index].get()
            if (candidate != null && candidate.parent != null) return candidate
        }
        return null
    }

    fun closePopup(webView: WebView) {
        unregisterPopup(webView)
        (webView.parent as? ViewGroup)?.removeView(webView)
        try {
            webView.stopLoading()
            webView.removeJavascriptInterface("QuestBridge")
            webView.destroy()
        } catch (_: Throwable) {
        }
    }

    fun handleBack(): Boolean {
        val popup = currentPopup()
        if (popup != null) {
            if (popup.canGoBack()) {
                popup.goBack()
            } else {
                closePopup(popup)
            }
            return true
        }

        val main = mainWebView.get()
        if (main != null && main.canGoBack()) {
            main.goBack()
            return true
        }
        return false
    }
}

private class QuestBridge(
    private val spatialMode: Boolean,
) {
    @JavascriptInterface
    fun updateStereoLayout(json: String) {
        if (spatialMode && json.isNotBlank()) {
            SpatialBridgeBus.stereoLayout(json)
        }
    }

    @JavascriptInterface
    fun updateStereoEyes(leftDataUrl: String, rightDataUrl: String) {
        if (
            spatialMode &&
            leftDataUrl.isNotBlank() &&
            rightDataUrl.isNotBlank()
        ) {
            LiveStereoFrameSink.submitEyeDataUrls(leftDataUrl, rightDataUrl)
        }
    }

    @JavascriptInterface
    fun getStereoDebugStatus(): String = StereoDebugState.toJson()

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
    injectAssetScript(view, "ggq-stereo-layout", STEREO_LAYOUT_URL)
}

private class GeoGebraChromeClient(
    private val spatialMode: Boolean,
    private val assetLoader: WebViewAssetLoader,
) : WebChromeClient() {
    override fun onCreateWindow(
        view: WebView,
        isDialog: Boolean,
        isUserGesture: Boolean,
        resultMsg: Message,
    ): Boolean {
        val parent = view.parent as? ViewGroup ?: return false
        val transport = resultMsg.obj as? WebView.WebViewTransport ?: return false

        val popup = WebView(view.context)
        configureWebViewCore(
            webView = popup,
            spatialMode = spatialMode,
            assetLoader = assetLoader,
            injectStereoScripts = false,
            registerAsMain = false,
        )
        parent.addView(
            popup,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        GeoGebraWebNavigation.registerPopup(popup)

        transport.webView = popup
        resultMsg.sendToTarget()
        return true
    }

    override fun onCloseWindow(window: WebView) {
        GeoGebraWebNavigation.closePopup(window)
    }
}

@SuppressLint("SetJavaScriptEnabled")
private fun configureWebViewCore(
    webView: WebView,
    spatialMode: Boolean,
    assetLoader: WebViewAssetLoader,
    injectStereoScripts: Boolean,
    registerAsMain: Boolean,
) {
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
        settings.setSupportMultipleWindows(true)
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.9.18"

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

        webChromeClient = GeoGebraChromeClient(spatialMode, assetLoader)
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
                if (injectStereoScripts) {
                    injectQuestScripts(view)
                }
            }
        }

        if (registerAsMain) {
            addJavascriptInterface(QuestBridge(spatialMode), "QuestBridge")
            GeoGebraWebNavigation.registerMain(this)
        }
    }
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

    configureWebViewCore(
        webView = webView,
        spatialMode = spatialMode,
        assetLoader = assetLoader,
        injectStereoScripts = true,
        registerAsMain = true,
    )
    webView.loadUrl(LOCAL_APP_URL)
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
