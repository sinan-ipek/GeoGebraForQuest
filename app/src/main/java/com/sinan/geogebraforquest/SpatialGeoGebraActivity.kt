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
import com.meta.spatial.runtime.PanelSceneObject
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.runtime.SceneTexture
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
 * GeoGebraForQuest v0.9.9 late panel-mesh stereo build.
 *
 * v0.9.7.1/v0.9.8 used a separate child SceneObject as a visual stereo portal.
 * The Quest recordings showed no visible difference between those releases,
 * which means that overlay never became the layer the user was actually seeing.
 *
 * v0.9.9 therefore removes the overlay architecture. Startup is still the known
 * working single LayoutXML/WebView panel. Only after the scene, VR, WebView,
 * live panel texture and measured 3D rectangle have all been stable for several
 * seconds do we replace the render mesh of that *same* PanelSceneObject with the
 * stereo material. The WebView surface and input target stay unchanged.
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

        // v0.9.7 changed the mesh during panel setup and could crash at startup.
        // Wait until the complete Spatial/Web/GeoGebra stack is settled.
        private const val STEREO_MESH_START_DELAY_MS = 3500L
        private const val TEXTURE_RETRY_MS = 250L
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var geoGebraPanelSceneObject: PanelSceneObject? = null
    private var panelTexture: SceneTexture? = null
    private var stereoPanelRenderer: QuestStereoPanelRenderer? = null
    private var pendingStereoLayout: String? = null

    private var sceneReady = false
    private var vrReady = false
    private var webPanelReady = false
    private var stereoStartScheduled = false
    private var stereoDisabledForLaunch = false

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
                panelSetupWithRootView = { rootView, panelSceneObject, _ ->
                    val webView = rootView.findViewById<WebView>(R.id.geogebra_webview)
                    configureGeoGebraWebView(
                        webView = webView,
                        spatialMode = true,
                        startStereo = true,
                    )

                    // Keep startup identical to the working ordinary panel.
                    // Do not change panelSceneObject.mesh here.
                    geoGebraPanelSceneObject = panelSceneObject
                    panelTexture = panelSceneObject.getTexture()
                    scheduleStereoMeshIfReady()
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()

        SpatialBridgeBus.onStereoLayout = { layout ->
            if (layout.isNotBlank()) {
                pendingStereoLayout = layout

                val renderer = stereoPanelRenderer
                if (renderer != null) {
                    renderer.updateLayout(layout)
                } else {
                    scheduleStereoMeshIfReady()
                }
            }
        }

        SpatialBridgeBus.onPanelReady = {
            webPanelReady = true
            scheduleStereoMeshIfReady()
        }

        requestScenePermissionIfNeeded()
    }

    private fun scheduleStereoMeshIfReady() {
        if (
            stereoDisabledForLaunch ||
            stereoPanelRenderer != null ||
            stereoStartScheduled
        ) {
            return
        }

        if (!sceneReady || !vrReady || !webPanelReady) return
        if (geoGebraPanelSceneObject == null || pendingStereoLayout.isNullOrBlank()) return

        if (panelTexture == null) {
            panelTexture = geoGebraPanelSceneObject?.getTexture()
        }

        if (panelTexture == null) {
            stereoStartScheduled = true
            mainHandler.postDelayed(
                {
                    stereoStartScheduled = false
                    scheduleStereoMeshIfReady()
                },
                TEXTURE_RETRY_MS,
            )
            return
        }

        stereoStartScheduled = true
        mainHandler.postDelayed(
            {
                stereoStartScheduled = false
                createLateStereoPanelRenderer()
            },
            STEREO_MESH_START_DELAY_MS,
        )
    }

    private fun createLateStereoPanelRenderer() {
        if (stereoDisabledForLaunch || stereoPanelRenderer != null) return
        if (!sceneReady || !vrReady || !webPanelReady) return

        val panelSceneObject = geoGebraPanelSceneObject ?: return
        val texture =
            panelTexture ?: panelSceneObject.getTexture() ?: run {
                scheduleStereoMeshIfReady()
                return
            }
        panelTexture = texture

        val layout = pendingStereoLayout ?: return

        try {
            val renderer =
                QuestStereoPanelRenderer(
                    activity = this,
                    panelSceneObject = panelSceneObject,
                    panelTexture = texture,
                    panelWidthMeters = PANEL_WIDTH_METERS,
                    panelHeightMeters = PANEL_HEIGHT_METERS,
                )

            stereoPanelRenderer = renderer
            renderer.updateLayout(layout)
            Log.i(TAG, "v0.9.9 late stereo mesh takeover active")
        } catch (error: Throwable) {
            // If Spatial rejects the late mesh swap as a normal runtime
            // exception, leave the already-working WebView panel alive.
            stereoDisabledForLaunch = true
            stereoPanelRenderer = null
            Log.e(TAG, "v0.9.9 late stereo mesh takeover disabled", error)
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
        scheduleStereoMeshIfReady()
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

        scheduleStereoMeshIfReady()
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        mainHandler.removeCallbacksAndMessages(null)

        stereoPanelRenderer?.release()
        stereoPanelRenderer = null
        pendingStereoLayout = null
        panelTexture = null
        geoGebraPanelSceneObject = null

        super.onDestroy()
    }
}
