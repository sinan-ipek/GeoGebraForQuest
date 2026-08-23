package com.sinan.geogebraforquest

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
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
import android.webkit.ValueCallback
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

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

object GeoGebraLocalFilePicker {
    const val REQUEST_CODE = 9025

    private var pendingCallback: ValueCallback<Array<Uri>>? = null

    fun launch(
        activity: Activity?,
        callback: ValueCallback<Array<Uri>>,
        params: WebChromeClient.FileChooserParams,
    ): Boolean {
        if (activity == null) {
            callback.onReceiveValue(null)
            return false
        }

        pendingCallback?.onReceiveValue(null)
        pendingCallback = callback

        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(
                Intent.EXTRA_ALLOW_MULTIPLE,
                params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE,
            )
        }

        return try {
            @Suppress("DEPRECATION")
            activity.startActivityForResult(intent, REQUEST_CODE)
            true
        } catch (_: Throwable) {
            pendingCallback = null
            callback.onReceiveValue(null)
            false
        }
    }

    fun handleActivityResult(
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ): Boolean {
        if (requestCode != REQUEST_CODE) return false

        val callback = pendingCallback
        pendingCallback = null
        if (callback == null) return true

        if (resultCode != Activity.RESULT_OK || data == null) {
            callback.onReceiveValue(null)
            return true
        }

        val clipData = data.clipData
        val result = when {
            clipData != null && clipData.itemCount > 0 ->
                Array(clipData.itemCount) { index -> clipData.getItemAt(index).uri }
            data.data != null -> arrayOf(data.data!!)
            else -> null
        }

        callback.onReceiveValue(result)
        return true
    }

    fun cancelPending() {
        pendingCallback?.onReceiveValue(null)
        pendingCallback = null
    }
}

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

    fun toggleContextMenu(): Boolean {
        val main = mainWebView.get() ?: return false
        main.post {
            main.evaluateJavascript(
                "if(window.__ggqToggleContextMenu){window.__ggqToggleContextMenu();}",
                null,
            )
        }
        return true
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

private fun injectControllerContextMenuSupport(view: WebView) {
    view.evaluateJavascript(
        """
        (function () {
          if (window.__ggqContextSupportInstalled) return;
          window.__ggqContextSupportInstalled = true;
          window.__ggqContextMenuVisible = false;
          window.__ggqLastPointer = {
            x: Math.max(1, Math.round(window.innerWidth / 2)),
            y: Math.max(1, Math.round(window.innerHeight / 2))
          };

          function rememberPointer(event) {
            if (typeof event.clientX === 'number' && typeof event.clientY === 'number') {
              window.__ggqLastPointer = { x: event.clientX, y: event.clientY };
            }
          }

          document.addEventListener('pointermove', rememberPointer, true);
          document.addEventListener('mousemove', rememberPointer, true);
          document.addEventListener('pointerdown', rememberPointer, true);
          document.addEventListener('click', function () {
            window.__ggqContextMenuVisible = false;
          }, true);

          function sendEscape(target) {
            try {
              target.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Escape', code: 'Escape', keyCode: 27, which: 27,
                bubbles: true, cancelable: true
              }));
              target.dispatchEvent(new KeyboardEvent('keyup', {
                key: 'Escape', code: 'Escape', keyCode: 27, which: 27,
                bubbles: true, cancelable: true
              }));
            } catch (e) {}
          }

          window.__ggqToggleContextMenu = function () {
            var p = window.__ggqLastPointer || { x: 1, y: 1 };

            if (window.__ggqContextMenuVisible) {
              window.__ggqContextMenuVisible = false;
              sendEscape(document.activeElement || document.body);
              sendEscape(document);
              return 'closed';
            }

            var target = document.elementFromPoint(p.x, p.y) || document.body;
            var mouseDown = new MouseEvent('mousedown', {
              bubbles: true, cancelable: true, view: window,
              clientX: p.x, clientY: p.y, button: 2, buttons: 2
            });
            var mouseUp = new MouseEvent('mouseup', {
              bubbles: true, cancelable: true, view: window,
              clientX: p.x, clientY: p.y, button: 2, buttons: 0
            });
            var contextMenu = new MouseEvent('contextmenu', {
              bubbles: true, cancelable: true, view: window,
              clientX: p.x, clientY: p.y, button: 2, buttons: 2
            });

            try {
              if (window.PointerEvent) {
                target.dispatchEvent(new PointerEvent('pointerdown', {
                  bubbles: true, cancelable: true,
                  clientX: p.x, clientY: p.y,
                  pointerId: 1, pointerType: 'mouse',
                  button: 2, buttons: 2, isPrimary: true
                }));
              }
            } catch (e) {}

            target.dispatchEvent(mouseDown);
            target.dispatchEvent(mouseUp);
            target.dispatchEvent(contextMenu);
            window.__ggqContextMenuVisible = true;
            return 'opened';
          };
        })();
        """.trimIndent(),
        null,
    )
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

private fun refreshImeConnection(view: View) {
    view.requestFocus()
    val imm = view.context.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
    imm?.restartInput(view)
}

private class GeoGebraChromeClient(
    private val spatialMode: Boolean,
    private val assetLoader: WebViewAssetLoader,
    private val hostActivity: Activity?,
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
            hostActivity = hostActivity,
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

    override fun onShowFileChooser(
        webView: WebView,
        filePathCallback: ValueCallback<Array<Uri>>,
        fileChooserParams: FileChooserParams,
    ): Boolean = GeoGebraLocalFilePicker.launch(
        activity = hostActivity,
        callback = filePathCallback,
        params = fileChooserParams,
    )
}

@SuppressLint("SetJavaScriptEnabled", "ClickableViewAccessibility")
private fun configureWebViewCore(
    webView: WebView,
    spatialMode: Boolean,
    assetLoader: WebViewAssetLoader,
    injectStereoScripts: Boolean,
    registerAsMain: Boolean,
    hostActivity: Activity?,
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
        settings.allowContentAccess = true
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        settings.mediaPlaybackRequiresUserGesture = false
        settings.setSupportMultipleWindows(true)
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.userAgentString = settings.userAgentString + " GeoGebraForQuest/0.9.26"

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

        setOnTouchListener { touchedView, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }

        setOnKeyListener { _, keyCode, event ->
            keyCode == KeyEvent.KEYCODE_BACK &&
                event.action == KeyEvent.ACTION_DOWN &&
                GeoGebraWebNavigation.handleBack()
        }

        webChromeClient = GeoGebraChromeClient(spatialMode, assetLoader, hostActivity)
        webViewClient = object : WebViewClientCompat() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean = redirectLocalLoginCallback(view, request.url)

            @Suppress("DEPRECATION")
            override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean =
                redirectLocalLoginCallback(view, Uri.parse(url))

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
                } else {
                    view.post { refreshImeConnection(view) }
                }
                if (registerAsMain) {
                    injectControllerContextMenuSupport(view)
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
    hostActivity: Activity? = webView.context.findActivity(),
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
        hostActivity = hostActivity,
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
