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
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.13 live stereo panel build.
 *
 * The normal GeoGebra LayoutXML/WebView panel remains fully interactive. Its
 * active 3D WebGL canvas is already rendered by the patched GeoGebra source as
 * one full-colour 2x-wide L|R SBS frame. quest-stereo-layout.js mirrors that
 * live SBS canvas through QuestBridge.updateStereoFrame().
 *
 * LiveStereoFrameSink decodes only the newest available frame and paints it
 * into the registered VideoSurface panel. The panel itself uses
 * StereoMode.LeftRight, so the Meta compositor sends the left half to the left
 * Quest eye and the right half to the right Quest eye.
 *
 * Both panels are created as ordinary dynamic panel entities with Grabbable,
 * Scale and IsdkPanelResize components. This mirrors Meta's official panel
 * resize sample more closely than changing components on a pre-addressed Entity.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        // StereoMode.LeftRight samples half of this texture for each eye. A 2:1
        // source surface therefore gives each eye a square sampling region.
        private const val STEREO_PANEL_WIDTH_METERS = 0.82f
        private const val STEREO_PANEL_HEIGHT_METERS = 0.82f
        private const val STEREO_TEXTURE_WIDTH = 1440
        private const val STEREO_TEXTURE_HEIGHT = 720

        private const val MIN_PANEL_HEIGHT = 0.35f
        private const val MAX_PANEL_HEIGHT = 3.00f

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

    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
        vrReady = true

        // Create the GeoGebra panel through the same dynamic Panel entity pattern
        // used by Meta's official resize sample. IsdkPanelResize now participates
        // from entity creation rather than being added later to a fixed-id entity.
        geogebraPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(-0.20f, 1.25f, 1.55f))),
                Scale(Vector3(1f)),
                Grabbable(
                    enabled = true,
                    type = GrabbableType.PIVOT_Y,
                    minHeight = MIN_PANEL_HEIGHT,
                    maxHeight = MAX_PANEL_HEIGHT,
                ),
                IsdkPanelResize(),
            )

        // Independent live stereo panel. It is movable and receives the same
        // native resize affordance as the GeoGebra panel.
        stereoPanelEntity =
            Entity.create(
                Panel(R.id.stereo_surface_probe_panel),
                Transform(Pose(Vector3(1.00f, 1.28f, 1.18f))),
                Scale(Vector3(1f)),
                Grabbable(
                    enabled = true,
                    type = GrabbableType.PIVOT_Y,
                    minHeight = MIN_PANEL_HEIGHT,
                    maxHeight = MAX_PANEL_HEIGHT,
                ),
                IsdkPanelResize(),
            )

        Log.i(TAG, "v0.9.13 live GeoGebra SBS stereo + two resizable panels active")
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
