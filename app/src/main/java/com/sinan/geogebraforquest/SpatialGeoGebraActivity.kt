package com.sinan.geogebraforquest

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.Surface
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
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
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.toolkit.getAbsoluteTransform
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.26.
 *
 * v0.9.26 keeps the v0.9.24/v0.9.25 stereo path intact and adds:
 * - a host-Activity backed Android local-file picker;
 * - Quest A as a GeoGebra right-click/context-menu toggle;
 * - Quest B as a stereo-panel controller-palette toggle;
 * - a slightly user-facing initial stereo-panel yaw;
 * - the new user supplied L/R startup splash pair.
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

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701

        private val INITIAL_STEREO_POSE = Pose(
            Vector3(1.10f, 1.30f, 1.15f),
            Quaternion(0f, 15f, 0f),
        )

        // Local pose relative to the right-controller entity while palette mode is active.
        private val CONTROLLER_PALETTE_POSE = Pose(
            Vector3(-0.17f, 0.08f, 0.10f),
            Quaternion(-55f, 0f, -18f),
        )
    }

    private var sceneReady = false
    private var vrReady = false
    private var stereoPanelEntity: Entity? = null
    private var stereoSurface: Surface? = null
    private var stereoPaletteAttached = false
    private var stereoPaletteRestorePose: Pose? = null

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
                        hostActivity = this,
                    )
                },
            ),
            VideoSurfacePanelRegistration(
                R.id.geogebra_stereo_panel,
                surfaceConsumer = { _, surface ->
                    stereoSurface?.let { previous ->
                        if (previous !== surface) {
                            LiveStereoFrameSink.detachSurface(previous)
                        }
                    }

                    stereoSurface = surface
                    LiveStereoFrameSink.attachSurface(surface, resources)
                    LiveStereoFrameSink.setEnabled(true)
                    Log.i(TAG, "v0.9.26 1440x720 stereo VideoSurface attached")
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
        LiveStereoFrameSink.setEnabled(true)
        systemManager.registerSystem(QuestControllerShortcutSystem(this))
        requestScenePermissionIfNeeded()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (!GeoGebraWebNavigation.handleBack()) {
            super.onBackPressed()
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    internal fun onQuestAButtonPressed() {
        GeoGebraWebNavigation.toggleContextMenu()
    }

    internal fun onQuestBButtonPressed(rightControllerEntity: Entity) {
        val panel = stereoPanelEntity ?: return

        if (!stereoPaletteAttached) {
            stereoPaletteRestorePose = getAbsoluteTransform(panel)
            panel.setComponent(TransformParent(rightControllerEntity))
            panel.setComponent(Transform(CONTROLLER_PALETTE_POSE))
            panel.setComponent(Grabbable(false))
            stereoPaletteAttached = true
            Log.i(TAG, "v0.9.26 stereo palette attached to right controller")
            return
        }

        val restorePose = stereoPaletteRestorePose ?: INITIAL_STEREO_POSE
        panel.setComponent(TransformParent())
        panel.setComponent(Transform(restorePose))
        panel.setComponent(Grabbable())
        stereoPaletteRestorePose = null
        stereoPaletteAttached = false
        Log.i(TAG, "v0.9.26 stereo palette restored to pre-B pose")
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

        Entity(R.id.geogebra_panel).setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(),
            ),
        )

        stereoPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_stereo_panel),
                Transform(INITIAL_STEREO_POSE),
                Grabbable(),
            )

        Log.i(TAG, "v0.9.26 stereo panel ready at x=1.10m with 15-degree inward yaw")
    }

    override fun onDestroy() {
        GeoGebraLocalFilePicker.cancelPending()
        SpatialBridgeBus.clear()
        LiveStereoFrameSink.setEnabled(false)

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null
        stereoPaletteRestorePose = null
        stereoPaletteAttached = false

        super.onDestroy()
    }
}
