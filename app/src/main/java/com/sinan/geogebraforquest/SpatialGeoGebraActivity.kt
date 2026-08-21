package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.9.10 official-stereo diagnostic build.
 *
 * The GeoGebra panel is intentionally left on the known-working v0.9.6-style
 * LayoutXML/WebView path. No portal is created from its texture and its render
 * mesh is never replaced.
 *
 * Separately, after Spatial scene + VR are ready, a small world-space probe is
 * created using only Meta Spatial SDK's stock SceneMaterial and
 * StereoMode.LeftRight. The probe source is a synthetic L|R bitmap, so this
 * release answers one narrow question without any GeoGebra/WebView variables:
 * does the SDK actually route L to the left Quest eye and R to the right eye?
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
        private const val PROBE_START_DELAY_MS = 1800L
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var sceneReady = false
    private var vrReady = false
    private var probeScheduled = false
    private var stereoProbe: OfficialStereoProbeRenderer? = null

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
                    // v0.9.10 diagnostic rule: do not touch the panel SceneObject.
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

    private fun scheduleProbeIfReady() {
        if (stereoProbe != null || probeScheduled) return
        if (!sceneReady || !vrReady) return

        probeScheduled = true
        mainHandler.postDelayed(
            {
                probeScheduled = false
                createOfficialStereoProbe()
            },
            PROBE_START_DELAY_MS,
        )
    }

    private fun createOfficialStereoProbe() {
        if (stereoProbe != null || !sceneReady || !vrReady) return

        try {
            stereoProbe = OfficialStereoProbeRenderer(this)
            Log.i(TAG, "v0.9.10 official StereoMode.LeftRight probe active")
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.10 official stereo probe creation failed", error)
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
        scheduleProbeIfReady()
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

        scheduleProbeIfReady()
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        SpatialBridgeBus.clear()

        stereoProbe?.release()
        stereoProbe = null

        super.onDestroy()
    }
}
