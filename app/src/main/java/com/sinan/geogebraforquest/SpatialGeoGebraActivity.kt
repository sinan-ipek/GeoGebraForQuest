package com.sinan.geogebraforquest

import android.content.pm.PackageManager
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

/**
 * GeoGebraForQuest v0.6.2 — raw GeoGebra stereo-capture diagnostic.
 *
 * v0.6.1 proved that the native Android -> Spatial SDK -> StereoMode.LeftRight
 * path is correct: Quest showed a different image to each eye and eye ordering
 * was correct.
 *
 * This build therefore tests ONLY the upstream half. When GeoGebra's JavaScript
 * capture sends an SBS frame, that frame is displayed directly as the stereo
 * panel. No WebView screenshot, portal compositing, or UI duplication is used.
 *
 * Expected result when capture works:
 *   left eye  -> "GEOGEBRA RAW - LEFT" + left 3D eye image
 *   right eye -> "GEOGEBRA RAW - RIGHT" + right 3D eye image
 *
 * If the headset button is pressed and this raw screen never appears, the
 * failure is before Quest/Spatial presentation: GeoGebra/WebGL capture is not
 * producing submitStereoFrame().
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
    }

    private val stereoFrameSurface = StereoFrameSurface()

    private var geoGebraPanelEntity: Entity? = null
    private var stereoFullPanelEntity: Entity? = null
    private var pendingStereo = false
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
            }
        }

        // Geometry is deliberately irrelevant in this diagnostic. We display
        // the captured SBS frame over the complete panel.
        SpatialBridgeBus.onPortalRect = { _ -> Unit }

        SpatialBridgeBus.onStereoFrame = { dataUrl, eyeWidth, eyeHeight ->
            if (!pendingStereo || dataUrl.isBlank()) return@onStereoFrame

            stereoFrameSurface.submitRawStereoDataUrl(
                dataUrl = dataUrl,
                reportedEyeWidth = eyeWidth,
                reportedEyeHeight = eyeHeight,
                onPresented = {
                    runOnMainThread {
                        if (pendingStereo) {
                            stereoFullPanelEntity?.setComponent(Visible(true))
                        }
                    }
                },
            )
        }

        SpatialBridgeBus.onPanelReady = {
            // Nothing to mirror natively.
        }

        requestScenePermissionIfNeeded()
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
        super.onDestroy()
    }
}
