package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.net.Uri
import android.os.Message
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
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
private const val LOCAL_ASSET_HOST = "appassets.androidplatform.net"
private const val REMOTE_LOGIN_CALLBACK_URL =
    "https://www.geogebra.org/apps/latest/web3d/html/ggtcallback.html"
private val MATERIAL_ID_REGEX = Regex("^[A-Za-z0-9_-]{3,80}$")
private val FRAGMENT_MATERIAL_REGEX = Regex("(?:^|/)material/([A-Za-z0-9_-]{3,80})(?:/|$)")

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

    fun openMaterialInLocalClassic(materialId: String, sourceView: WebView?): Boolean {
        val cleanId = materialId.trim()
        if (!MATERIAL_ID_REGEX.matches(cleanId)) return false

        val main = mainWebView.get() ?: return false
        val target = Uri.parse(LOCAL_APP_URL)
            .buildUpon()
            .appendQueryParameter("material_id", cleanId)
            .build()
            .toString()

        main.post {
            if (sourceView != null && sourceView !== main && sourceView.parent != null) {
                closePopup(sourceView)
            }
            main.loadUrl(target)
            main.requestFocus()
        }
        return true
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
    fun stereoInactive() {
        if (spatialMode) {
            LiveStereoFrameSink.clearForInactiveView()
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

private fun redirectLocalLoginCallback(view: WebView, uri: Uri): Boolean {
    val path = uri.path.orEmpty()
    if (
        !uri.host.equals(LOCAL_ASSET_HOST, ignoreCase = true) ||
        !path.endsWith("/ggtcallback.html")
    ) {
        return false
    }

    val remote = Uri.parse(REMOTE_LOGIN_CALLBACK_URL)
        .buildUpon()
        .encodedQuery(uri.encodedQuery)
        .build()
    view.loadUrl(remote.toString())
    return true
}

private fun isGeoGebraHost(host: String?): Boolean {
    val normalized = host?.lowercase().orEmpty()
    return normalized == "geogebra.org" || normalized.endsWith(".geogebra.org")
}

private fun validMaterialId(candidate: String?): String? {
    val clean = candidate?.trim()?.trim('/') ?: return null
    return clean.takeIf { MATERIAL_ID_REGEX.matches(it) }
}

private fun extractGeoGebraMaterialId(uri: Uri): String? {
    if (!isGeoGebraHost(uri.host)) return null

    validMaterialId(uri.getQueryParameter("material_id"))?.let { return it }

    val segments = uri.pathSegments
    for (index in segments.indices) {
        when (segments[index].lowercase()) {
            "m", "classic", "geometry", "3d" -> {
                validMaterialId(segments.getOrNull(index + 1))?.let { return it }
            }
            "id" -> {
                validMaterialId(segments.getOrNull(index + 1))?.let { return it }
            }
        }
    }

    val pathAllowsIdQuery = segments.any {
        it.equals("apps", ignoreCase = true) ||
            it.equals("material", ignoreCase = true) ||
            it.equals("m", ignoreCase = true)
    }
    if (pathAllowsIdQuery) {
        validMaterialId(uri.getQueryParameter("id"))?.let { return it }
    }

    val fragment = uri.fragment.orEmpty()
    FRAGMENT_MATERIAL_REGEX.find(fragment)?.groupValues?.getOrNull(1)?.let { raw ->
        validMaterialId(raw)?.let { return it }
    }

    return null
}

private fun routeMaterialToLocalClassic(view: WebView, uri: Uri): Boolean {
    val materialId = extractGeoGebraMaterialId(uri) ?: return false
    return GeoGebraWebNavigation.openMaterialInLocalClassic(materialId, view)
}

private fun refreshImeConnection(view: View) {
    view.requestFocus()
    val imm = view.context.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
    imm?.restartInput(view)
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
        popup.post { refreshImeConnection(popup) }

        transport.webView = popup
        resultMsg.sendToTarget()
        return true
    }

    override fun onCloseWindow(window: WebView) {
        GeoGebraWebNavigation.closePopup(window)
    }
}

@SuppressLint("SetJavaScriptEnabled", "ClickableViewAccessibility")
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
        isFocusable = true
        isFocusableInTouchMode = true

        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        settings.mediaPlaybackRequiresUserGesture = false
        settings.setSupportMultipleWindows(true)
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.9.25"

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

        setOnTouchListener { touchedView, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }

        setOnKeyListener { _, keyCode, event ->
            val isBack = keyCode == KeyEvent.KEYCODE_BUTTON_B || keyCode == KeyEvent.KEYCODE_BACK
            isBack && event.action == KeyEvent.ACTION_DOWN && GeoGebraWebNavigation.handleBack()
        }

        webChromeClient = GeoGebraChromeClient(spatialMode, assetLoader)
        webViewClient = object : WebViewClientCompat() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean =
                redirectLocalLoginCallback(view, request.url) ||
                    routeMaterialToLocalClassic(view, request.url)

            @Suppress("DEPRECATION")
            override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean {
                val uri = Uri.parse(url)
                return redirectLocalLoginCallback(view, uri) ||
                    routeMaterialToLocalClassic(view, uri)
            }

            override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) {
                super.doUpdateVisitedHistory(view, url, isReload)
                if (!url.isNullOrBlank()) {
                    routeMaterialToLocalClassic(view, Uri.parse(url))
                }
            }

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
                if (routeMaterialToLocalClassic(view, Uri.parse(url))) return

                if (injectStereoScripts) {
                    injectQuestScripts(view)
                } else {
                    view.post { refreshImeConnection(view) }
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
