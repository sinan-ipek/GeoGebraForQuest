package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.Surface
import android.webkit.WebView
import android.widget.Button
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
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.14.
 *
 * v0.9.11 established the only Quest presentation path that has been physically
 * verified to separate the eyes: a registered VideoSurfacePanel whose entity is
 * just Panel + Transform + Grabbable and whose MediaPanelRenderOptions uses
 * StereoMode.LeftRight.
 *
 * v0.9.13 successfully sent the live GeoGebra SBS frame to that surface, but it
 * also added IsdkPanelResize and an explicit Scale component to the media-panel
 * entity. On Quest the result regressed to a single ordinary panel showing the
 * complete L|R image side by side.
 *
 * v0.9.14 therefore restores the stereo entity to the minimal v0.9.11 structure.
 * IsdkPanelResize is not used at all. Scaling is deliberately kept outside the
 * media-panel renderer: a tiny ordinary control panel changes only the ECS Scale
 * transform of either target panel. Until the user presses a scale button, the
 * stereo entity is byte-for-byte equivalent in component composition to the
 * working v0.9.11 Panel + Transform + Grabbable path.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val STEREO_PANEL_WIDTH_METERS = 0.82f
        private const val STEREO_PANEL_HEIGHT_METERS = 0.82f
        private const val STEREO_TEXTURE_WIDTH = 1440
        private const val STEREO_TEXTURE_HEIGHT = 720

        private const val CONTROLS_PANEL_WIDTH_METERS = 0.58f
        private const val CONTROLS_PANEL_HEIGHT_METERS = 0.10f
        private const val CONTROLS_PANEL_WIDTH_DP = 420f
        private const val CONTROLS_PANEL_HEIGHT_DP = 72f

        private const val MIN_PANEL_HEIGHT = 0.35f
        private const val MAX_PANEL_HEIGHT = 3.00f
        private const val MIN_PANEL_SCALE = 0.50f
        private const val MAX_PANEL_SCALE = 3.00f
        private const val SCALE_STEP = 0.15f

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
    }

    private var sceneReady = false
    private var vrReady = false

    private var geogebraPanelEntity: Entity? = null
    private var stereoPanelEntity: Entity? = null
    private var scaleControlsEntity: Entity? = null
    private var stereoSurface: Surface? = null

    private var geogebraScale = 1.0f
    private var stereoScale = 1.0f

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
            LayoutXMLPanelRegistration(
                R.id.scale_controls_panel,
                layoutIdCreator = { R.layout.scale_controls_panel },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(
                            width = CONTROLS_PANEL_WIDTH_METERS,
                            height = CONTROLS_PANEL_HEIGHT_METERS,
                        ),
                        display = DpDisplayOptions(
                            width = CONTROLS_PANEL_WIDTH_DP,
                            height = CONTROLS_PANEL_HEIGHT_DP,
                        ),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                    )
                },
                panelSetupWithRootView = { rootView, _, _ ->
                    rootView.findViewById<Button>(R.id.geo_scale_down).setOnClickListener {
                        adjustGeoGebraScale(-SCALE_STEP)
                    }
                    rootView.findViewById<Button>(R.id.geo_scale_up).setOnClickListener {
                        adjustGeoGebraScale(SCALE_STEP)
                    }
                    rootView.findViewById<Button>(R.id.stereo_scale_down).setOnClickListener {
                        adjustStereoScale(-SCALE_STEP)
                    }
                    rootView.findViewById<Button>(R.id.stereo_scale_up).setOnClickListener {
                        adjustStereoScale(SCALE_STEP)
                    }
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

    private fun movablePanel(): Grabbable =
        Grabbable(
            enabled = true,
            type = GrabbableType.PIVOT_Y,
            minHeight = MIN_PANEL_HEIGHT,
            maxHeight = MAX_PANEL_HEIGHT,
        )

    private fun adjustGeoGebraScale(delta: Float) {
        geogebraScale = (geogebraScale + delta).coerceIn(MIN_PANEL_SCALE, MAX_PANEL_SCALE)
        geogebraPanelEntity?.setComponent(Scale(Vector3(geogebraScale)))
        Log.i(TAG, "v0.9.14 GeoGebra scale=$geogebraScale")
    }

    private fun adjustStereoScale(delta: Float) {
        stereoScale = (stereoScale + delta).coerceIn(MIN_PANEL_SCALE, MAX_PANEL_SCALE)
        stereoPanelEntity?.setComponent(Scale(Vector3(stereoScale)))
        Log.i(TAG, "v0.9.14 stereo scale=$stereoScale")
    }

    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
        vrReady = true

        geogebraPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(-0.20f, 1.25f, 1.55f))),
                movablePanel(),
            )

        // Keep this initial entity composition exactly on the v0.9.11 path:
        // Panel + Transform + Grabbable. In particular, no IsdkPanelResize and
        // no Scale component is attached at creation time.
        stereoPanelEntity =
            Entity.create(
                Panel(R.id.stereo_surface_probe_panel),
                Transform(Pose(Vector3(1.00f, 1.28f, 1.18f))),
                movablePanel(),
            )

        scaleControlsEntity =
            Entity.create(
                Panel(R.id.scale_controls_panel),
                Transform(Pose(Vector3(0.38f, 0.72f, 1.15f))),
                movablePanel(),
            )

        Log.i(TAG, "v0.9.14 minimal LeftRight media panel + external scale controls active")
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null

        geogebraPanelEntity?.destroy()
        geogebraPanelEntity = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null

        scaleControlsEntity?.destroy()
        scaleControlsEntity = null

        super.onDestroy()
    }
}
