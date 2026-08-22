package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Surface
import android.webkit.WebView
import android.widget.Button
import android.widget.TextView
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
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.15 A/B stereo diagnostic.
 *
 * One and only one registered VideoSurface panel is used for both sources:
 * 1) TEST: the exact deterministic v0.9.11 red-left / blue-right probe.
 * 2) GEOGEBRA: the live full-colour GeoGebra SBS frame.
 *
 * The stereo media panel deliberately returns to the physically verified
 * v0.9.11 settings: 0.80 x 0.45 metres, 800 x 400 pixels, StereoMode.LeftRight,
 * and an entity containing only Panel + Transform + Grabbable().
 *
 * Switching source never recreates or reconfigures the stereo panel. It only
 * changes what is painted into the same Surface. This makes the headset test a
 * controlled comparison of compositor/panel routing versus live frame transfer.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val STEREO_PANEL_WIDTH_METERS = 0.80f
        private const val STEREO_PANEL_HEIGHT_METERS = 0.45f
        private const val STEREO_TEXTURE_WIDTH = 800
        private const val STEREO_TEXTURE_HEIGHT = 400

        private const val CONTROLS_PANEL_WIDTH_METERS = 0.64f
        private const val CONTROLS_PANEL_HEIGHT_METERS = 0.16f
        private const val CONTROLS_PANEL_WIDTH_DP = 520f
        private const val CONTROLS_PANEL_HEIGHT_DP = 128f

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
    }

    private enum class StereoSourceMode {
        TEST,
        GEOGEBRA,
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var sceneReady = false
    private var vrReady = false
    private var stereoPanelEntity: Entity? = null
    private var controlsPanelEntity: Entity? = null
    private var stereoSurface: Surface? = null
    private var modeStatusView: TextView? = null
    private var stereoSourceMode = StereoSourceMode.TEST

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
                    applyCurrentStereoSource(surface)
                    Log.i(
                        TAG,
                        "v0.9.15 shared 800x400 stereo VideoSurface attached; mode=$stereoSourceMode",
                    )
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
                    modeStatusView = rootView.findViewById(R.id.stereo_mode_status)
                    rootView.findViewById<Button>(R.id.stereo_test_mode).setOnClickListener {
                        switchToTestMode()
                    }
                    rootView.findViewById<Button>(R.id.stereo_geogebra_mode).setOnClickListener {
                        switchToGeoGebraMode()
                    }
                    updateModeStatus()
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()
        SpatialBridgeBus.clear()
        LiveStereoFrameSink.setEnabled(false)
        requestScenePermissionIfNeeded()
    }

    private fun applyCurrentStereoSource(surface: Surface) {
        when (stereoSourceMode) {
            StereoSourceMode.TEST -> {
                LiveStereoFrameSink.setEnabled(false)
                drawStereoProbeRepeatedly(surface)
            }

            StereoSourceMode.GEOGEBRA -> {
                LiveStereoFrameSink.setEnabled(true)
            }
        }
        updateModeStatus()
    }

    private fun switchToTestMode() {
        stereoSourceMode = StereoSourceMode.TEST
        LiveStereoFrameSink.setEnabled(false)
        stereoSurface?.let { surface ->
            if (surface.isValid) {
                drawStereoProbeRepeatedly(surface)
            }
        }
        updateModeStatus()
        Log.i(TAG, "v0.9.15 A/B source switched to TEST")
    }

    private fun switchToGeoGebraMode() {
        stereoSourceMode = StereoSourceMode.GEOGEBRA
        LiveStereoFrameSink.setEnabled(true)
        updateModeStatus()
        Log.i(TAG, "v0.9.15 A/B source switched to GEOGEBRA")
    }

    private fun drawStereoProbeRepeatedly(surface: Surface) {
        StereoSurfaceProbe.draw(surface)
        mainHandler.postDelayed(
            { if (stereoSourceMode == StereoSourceMode.TEST && surface.isValid) StereoSurfaceProbe.draw(surface) },
            250L,
        )
        mainHandler.postDelayed(
            { if (stereoSourceMode == StereoSourceMode.TEST && surface.isValid) StereoSurfaceProbe.draw(surface) },
            1000L,
        )
    }

    private fun updateModeStatus() {
        modeStatusView?.text = when (stereoSourceMode) {
            StereoSourceMode.TEST -> "STEREO KAYNAĞI: TEST"
            StereoSourceMode.GEOGEBRA -> "STEREO KAYNAĞI: GEOGEBRA"
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

        // Keep the normal GeoGebra panel on the same simple entity path used in
        // the successful v0.9.11 probe build.
        Entity(R.id.geogebra_panel).setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(),
            ),
        )

        // This is intentionally the exact v0.9.11 stereo entity composition.
        stereoPanelEntity =
            Entity.create(
                Panel(R.id.stereo_surface_probe_panel),
                Transform(Pose(Vector3(0.95f, 1.30f, 1.15f))),
                Grabbable(),
            )

        controlsPanelEntity =
            Entity.create(
                Panel(R.id.scale_controls_panel),
                Transform(Pose(Vector3(0.95f, 0.78f, 1.12f))),
                Grabbable(),
            )

        Log.i(TAG, "v0.9.15 A/B stereo diagnostic ready; default source=TEST")
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        SpatialBridgeBus.clear()
        LiveStereoFrameSink.setEnabled(false)

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null
        modeStatusView = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null

        controlsPanelEntity?.destroy()
        controlsPanelEntity = null

        super.onDestroy()
    }
}
