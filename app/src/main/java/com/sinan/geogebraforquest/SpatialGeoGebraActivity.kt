package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.Surface
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
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
import com.meta.spatial.toolkit.MediaPanelRenderOptions
import com.meta.spatial.toolkit.MediaPanelSettings
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.PixelDisplayOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.14.
 *
 * v0.9.13 proved that the live GeoGebra 3D SBS frame reaches the registered
 * VideoSurface, but adding IsdkPanelResize / explicit Scale to the media panel
 * changed the behaviour of the previously validated stereo presentation path:
 * the whole SBS texture was shown as one ordinary panel image.
 *
 * v0.9.14 restores the stereo panel entity to the same minimal composition that
 * worked in v0.9.11: Panel + Transform + Grabbable only. Scaling is requested
 * through Grabbable's two-hand scaling support instead of panel-resize logic, so
 * the MediaPanelRenderOptions(StereoMode.LeftRight) compositor configuration is
 * left untouched.
 *
 * The GeoGebra panel uses the same two-hand Grabbable scaling gesture. The live
 * JPEG bridge and preserveDrawingBuffer source patch from v0.9.13 remain intact.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        // Keep the registered media panel simple. The compositor, not an ISDK
        // resize component, owns LeftRight texture selection.
        private const val STEREO_PANEL_WIDTH_METERS = 0.82f
        private const val STEREO_PANEL_HEIGHT_METERS = 0.82f
        private const val STEREO_TEXTURE_WIDTH = 1440
        private const val STEREO_TEXTURE_HEIGHT = 720

        private const val MIN_PANEL_HEIGHT = 0.35f
        private const val MAX_PANEL_HEIGHT = 3.00f
        private const val MIN_PANEL_SCALE = 0.45f
        private const val MAX_PANEL_SCALE = 3.00f

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
    }

    private var sceneReady = false
    private var vrReady = false

    private var geogebraPanelEntity: Entity? = null
    private var stereoPanelEntity: Entity? = null
    private var stereoSurface: Surface? = null

    override fun registerFeatures(): List<SpatialFeature> = listOf(VRFeature(this))

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
                        startStereo = true,
                    )
                },
            ),
            VideoSurfacePanelRegistration(
                R.id.stereo_surface_probe_panel,
                surfaceConsumer = { _, surface ->
                    stereoSurface?.let { previous ->
                        if (previous !== surface) {
                            LiveStereoFrameSink.detachSurface(previous)
                        }
                    }
                    stereoSurface = surface
                    LiveStereoFrameSink.attachSurface(surface)
                    Log.i(TAG, "v0.9.14 live stereo VideoSurface attached")
                },
                settingsCreator = {
                    MediaPanelSettings(
                        shape = QuadShapeOptions(
                            width = STEREO_PANEL_WIDTH_METERS,
                            height = STEREO_PANEL_HEIGHT_METERS,
                        ),
                        display = PixelDisplayOptions(
                            width = STEREO_TEXTURE_WIDTH,
                            height = STEREO_TEXTURE_HEIGHT,
                        ),
                        rendering = MediaPanelRenderOptions(
                            stereoMode = StereoMode.LeftRight,
                            zIndex = 20,
                        ),
                    )
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()
        SpatialBridgeBus.clear()
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

    private fun scalableGrabbable(): Grabbable =
        Grabbable(
            enabled = true,
            type = GrabbableType.PIVOT_Y,
            minHeight = MIN_PANEL_HEIGHT,
            maxHeight = MAX_PANEL_HEIGHT,
            twoHandGrab = true,
            allowScaling = true,
            minScale = MIN_PANEL_SCALE,
            maxScale = MAX_PANEL_SCALE,
        )

    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
        vrReady = true

        // No IsdkPanelResize and no explicit Scale component. Two-hand scaling is
        // handled entirely by the existing Grabbable interaction path.
        geogebraPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(-0.20f, 1.25f, 1.55f))),
                scalableGrabbable(),
            )

        // IMPORTANT: preserve the v0.9.11 media-panel render path. This entity
        // deliberately contains only Panel + Transform + Grabbable.
        stereoPanelEntity =
            Entity.create(
                Panel(R.id.stereo_surface_probe_panel),
                Transform(Pose(Vector3(1.00f, 1.28f, 1.18f))),
                scalableGrabbable(),
            )

        Log.i(TAG, "v0.9.14 pure LeftRight media panel + two-hand scalable panels active")
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null

        geogebraPanelEntity?.destroy()
        geogebraPanelEntity = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null

        super.onDestroy()
    }
}
