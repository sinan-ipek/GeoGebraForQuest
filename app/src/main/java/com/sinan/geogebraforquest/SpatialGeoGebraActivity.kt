package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.os.Bundle
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.runtime.StereoMode
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
import com.meta.spatial.toolkit.MediaPanelRenderOptions
import com.meta.spatial.toolkit.MediaPanelSettings
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.PixelDisplayOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature
import java.util.concurrent.atomic.AtomicBoolean

/**
 * GeoGebraForQuest v0.6.1 stereo-pipeline diagnostic build.
 *
 * v0.6.0 still produced no visible depth. Before changing GeoGebra capture again
 * we now isolate the final half of the pipeline. Pressing the headset button
 * shows a deterministic full-panel SBS calibration image generated natively:
 * the ordinary GeoGebra panel is identical in both eyes, while A/B/C targets
 * have positive/zero/negative horizontal disparity.
 *
 * If A/B/C occupy different apparent depths, the Android -> Spatial surface ->
 * StereoMode.LeftRight path is working and the remaining bug is upstream in
 * GeoGebra/anaglyph extraction. If all three are flat/identical, the bug is in
 * the Spatial stereo presentation path itself.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701

        // Temporary diagnostic switch for v0.6.1.
        private const val STEREO_PIPELINE_TEST = true
    }

    private val stereoFrameSurface = StereoFrameSurface()
    private val webCapturePending = AtomicBoolean(false)

    private var geoGebraPanelEntity: Entity? = null
    private var stereoFullPanelEntity: Entity? = null
    private var geoGebraWebView: WebView? = null
    private var pendingStereo = false
    private var pendingPortalRect: String? = null
    private var sceneReady = false
    private var vrReady = false

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(VRFeature(this))
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            LayoutXMLPanelRegistration(
                R.id.geogebra_panel,
                layoutIdCreator = { R.layout.spatial_geogebra_panel },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(
                            width = PANEL_WIDTH_METERS,
                            height = PANEL_HEIGHT_METERS,
                        ),
                        display = DpDisplayOptions(
                            width = PANEL_WIDTH_DP,
                            height = PANEL_HEIGHT_DP,
                        ),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                    )
                },
                panelSetupWithRootView = { rootView, _, _ ->
                    val webView = rootView.findViewById<WebView>(R.id.geogebra_webview)
                    geoGebraWebView = webView
                    configureGeoGebraWebView(
                        webView = webView,
                        spatialMode = true,
                        startStereo = false,
                    )
                },
            ),
            VideoSurfacePanelRegistration(
                R.id.stereo_portal_panel,
                surfaceConsumer = { _, surface ->
                    stereoFrameSurface.attach(surface)
                },
                settingsCreator = {
                    MediaPanelSettings(
                        shape = QuadShapeOptions(width = 1f, height = 1f),
                        display = PixelDisplayOptions(
                            width = StereoFrameSurface.SURFACE_WIDTH,
                            height = StereoFrameSurface.SURFACE_HEIGHT,
                        ),
                        rendering = MediaPanelRenderOptions(
                            stereoMode = StereoMode.LeftRight,
                            zIndex = 1,
                        ),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                    )
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        SpatialBridgeBus.onStereoChanged = { enabled ->
            pendingStereo = enabled
            if (!enabled) {
                runOnMainThread {
                    stereoFullPanelEntity?.setComponent(Visible(false))
                }
            } else if (STEREO_PIPELINE_TEST) {
                showStereoCalibrationFrame()
            }
        }

        SpatialBridgeBus.onPortalRect = { json ->
            pendingPortalRect = json
        }

        SpatialBridgeBus.onStereoFrame = { dataUrl, _, _ ->
            if (!STEREO_PIPELINE_TEST) {
                captureAndSubmitFullPanelFrame(dataUrl)
            }
        }

        SpatialBridgeBus.onPanelReady = {
            // No native GeoGebra geometry mirror is needed.
        }

        requestScenePermissionIfNeeded()
    }

    /**
     * Captures the ordinary WebView once and asks StereoFrameSurface to draw
     * deliberately displaced A/B/C targets into the left/right halves. No
     * GeoGebra WebGL capture is involved in this test.
     */
    private fun showStereoCalibrationFrame() {
        if (!pendingStereo) return
        if (!stereoFrameSurface.canAcceptFrame()) return
        if (!webCapturePending.compareAndSet(false, true)) return

        val webView = geoGebraWebView
        if (webView == null) {
            webCapturePending.set(false)
            return
        }

        webView.post {
            if (!pendingStereo || webView.width <= 0 || webView.height <= 0) {
                webCapturePending.set(false)
                return@post
            }

            var basePanel: Bitmap? = null
            try {
                basePanel = Bitmap.createBitmap(
                    webView.width,
                    webView.height,
                    Bitmap.Config.ARGB_8888,
                )
                val canvas = Canvas(basePanel)
                canvas.drawColor(Color.WHITE)
                webView.draw(canvas)

                val accepted = stereoFrameSurface.submitCalibration(
                    basePanel = basePanel,
                    onPresented = {
                        runOnMainThread {
                            if (pendingStereo) {
                                stereoFullPanelEntity?.setComponent(Visible(true))
                            }
                        }
                    },
                    onFinished = {
                        webCapturePending.set(false)
                    },
                )

                if (accepted) {
                    basePanel = null
                }
            } catch (_: Throwable) {
                // A failed diagnostic snapshot must not crash the app.
            } finally {
                basePanel?.let { bitmap ->
                    if (!bitmap.isRecycled) bitmap.recycle()
                }
                if (basePanel != null) {
                    webCapturePending.set(false)
                }
            }
        }
    }

    private fun captureAndSubmitFullPanelFrame(dataUrl: String) {
        if (!pendingStereo || dataUrl.isBlank()) return
        if (!stereoFrameSurface.canAcceptFrame()) return
        if (!webCapturePending.compareAndSet(false, true)) return

        val webView = geoGebraWebView
        if (webView == null) {
            webCapturePending.set(false)
            return
        }

        val portalRect = pendingPortalRect

        webView.post {
            if (!pendingStereo || webView.width <= 0 || webView.height <= 0) {
                webCapturePending.set(false)
                return@post
            }

            var basePanel: Bitmap? = null
            try {
                basePanel = Bitmap.createBitmap(
                    webView.width,
                    webView.height,
                    Bitmap.Config.ARGB_8888,
                )
                val canvas = Canvas(basePanel)
                canvas.drawColor(Color.WHITE)
                webView.draw(canvas)

                val accepted = stereoFrameSurface.submitCompositeDataUrl(
                    dataUrl = dataUrl,
                    basePanel = basePanel,
                    portalRectJson = portalRect,
                    onPresented = {
                        runOnMainThread {
                            if (pendingStereo) {
                                stereoFullPanelEntity?.setComponent(Visible(true))
                            }
                        }
                    },
                    onFinished = {
                        webCapturePending.set(false)
                    },
                )

                if (accepted) {
                    basePanel = null
                }
            } catch (_: Throwable) {
                // A failed WebView snapshot is just one dropped stereo frame.
            } finally {
                basePanel?.let { bitmap ->
                    if (!bitmap.isRecycled) bitmap.recycle()
                }
                if (basePanel != null) {
                    webCapturePending.set(false)
                }
            }
        }
    }

    private fun requestScenePermissionIfNeeded() {
        if (checkSelfPermission(PERMISSION_USE_SCENE) == PackageManager.PERMISSION_GRANTED) {
            enablePassthroughWhenSafe()
            return
        }
        requestPermissions(arrayOf(PERMISSION_USE_SCENE), REQUEST_USE_SCENE)
    }

    private fun enablePassthroughWhenSafe() {
        if (!sceneReady) return
        if (checkSelfPermission(PERMISSION_USE_SCENE) != PackageManager.PERMISSION_GRANTED) return
        scene.enablePassthrough(true)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (
            requestCode == REQUEST_USE_SCENE &&
            grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        ) {
            enablePassthroughWhenSafe()
        }
    }

    override fun onSceneReady() {
        super.onSceneReady()
        sceneReady = true
        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
        scene.setViewOrigin(0f, 0f, 0f, 0f)
        enablePassthroughWhenSafe()
    }

    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
        vrReady = true

        val geoPanel = Entity(R.id.geogebra_panel)
        geoPanel.setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(),
            ),
        )
        geoGebraPanelEntity = geoPanel

        val stereoPanel = Entity(R.id.stereo_portal_panel)
        stereoPanel.setComponents(
            listOf(
                Panel(R.id.stereo_portal_panel),
                TransformParent(geoPanel),
                Transform(Pose(Vector3(0f, 0f, -0.006f))),
                Scale(Vector3(PANEL_WIDTH_METERS, PANEL_HEIGHT_METERS, 1f)),
                Visible(false),
            ),
        )
        stereoFullPanelEntity = stereoPanel
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        stereoFrameSurface.release()
        stereoFullPanelEntity = null
        geoGebraPanelEntity = null
        geoGebraWebView = null
        super.onDestroy()
    }
}
