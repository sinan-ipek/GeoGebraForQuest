package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Surface
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.isdk.IsdkPanelResize
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
 * GeoGebraForQuest v0.9.12 movable/resizable panel build.
 *
 * v0.9.11 proved the registered VideoSurfacePanel + StereoMode.LeftRight path
 * performs real Quest left/right eye separation. v0.9.12 keeps that stereo test
 * unchanged and adds native panel interaction:
 *
 * - GeoGebra panel: freely grabbable in space, including nearer/farther motion.
 * - GeoGebra panel: native Meta ISDK resize/scale handles via IsdkPanelResize.
 * - Stereo panel: independently grabbable and movable, not parented to GeoGebra.
 *
 * No stereo rendering logic changes are made in this release.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val PROBE_WIDTH_METERS = 0.80f
        private const val PROBE_HEIGHT_METERS = 0.45f
        private const val PROBE_TEXTURE_WIDTH = 800
        private const val PROBE_TEXTURE_HEIGHT = 400

        private const val MIN_PANEL_HEIGHT = 0.40f
        private const val MAX_PANEL_HEIGHT = 3.00f

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var sceneReady = false
    private var vrReady = false
    private var stereoSurfaceProbeEntity: Entity? = null
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
                    stereoSurface = surface
                    drawStereoProbeRepeatedly(surface)
                },
                settingsCreator = {
                    MediaPanelSettings(
                        shape = QuadShapeOptions(
                            width = PROBE_WIDTH_METERS,
                            height = PROBE_HEIGHT_METERS,
                        ),
                        display = PixelDisplayOptions(
                            width = PROBE_TEXTURE_WIDTH,
                            height = PROBE_TEXTURE_HEIGHT,
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

    private fun drawStereoProbeRepeatedly(surface: Surface) {
        StereoSurfaceProbe.draw(surface)
        mainHandler.postDelayed(
            { if (surface.isValid) StereoSurfaceProbe.draw(surface) },
            250L,
        )
        mainHandler.postDelayed(
            { if (surface.isValid) StereoSurfaceProbe.draw(surface) },
            1000L,
        )
        Log.i(TAG, "v0.9.12 registered stereo surface delivered")
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

        // GeoGebra panel:
        // PIVOT_Y lets the panel be grabbed and moved nearer/farther while
        // keeping a comfortable upright panel orientation. IsdkPanelResize
        // supplies Meta's native panel resize/scale affordance.
        Entity(R.id.geogebra_panel).setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(
                    enabled = true,
                    type = GrabbableType.PIVOT_Y,
                    minHeight = MIN_PANEL_HEIGHT,
                    maxHeight = MAX_PANEL_HEIGHT,
                ),
                IsdkPanelResize(),
            ),
        )

        // The registered stereo surface panel is a completely independent
        // spatial entity. It can be grabbed and moved without moving GeoGebra.
        stereoSurfaceProbeEntity =
            Entity.create(
                Panel(R.id.stereo_surface_probe_panel),
                Transform(Pose(Vector3(0.95f, 1.30f, 1.15f))),
                Grabbable(
                    enabled = true,
                    type = GrabbableType.PIVOT_Y,
                    minHeight = MIN_PANEL_HEIGHT,
                    maxHeight = MAX_PANEL_HEIGHT,
                ),
            )

        Log.i(TAG, "v0.9.12 movable stereo panel + resizable GeoGebra panel active")
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        SpatialBridgeBus.clear()

        stereoSurface = null
        stereoSurfaceProbeEntity?.destroy()
        stereoSurfaceProbeEntity = null

        super.onDestroy()
    }
}
