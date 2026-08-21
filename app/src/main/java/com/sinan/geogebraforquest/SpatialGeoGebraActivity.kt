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
 * GeoGebraForQuest v0.9.8 eye-pass stereo build.
 *
 * The stable startup architecture remains unchanged: one ordinary interactive
 * LayoutXML/WebView panel is created and its PanelSceneObject mesh is never
 * replaced. GeoGebra's source renderer writes full-colour L|R SBS into the 3D
 * WebGL backing store.
 *
 * After the scene, VR, WebView, live panel texture and measured 3D rectangle are
 * all ready, a non-interactive child SceneObject is placed over only the 3D
 * rectangle. Its shader sends the left SBS half to the left Quest eye and the
 * right SBS half to the right Quest eye. Popup/settings overlaps are punched out
 * locally by the portal shader; they no longer disable the whole stereo layer.
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
        private const val PORTAL_START_DELAY_MS = 1500L
        private const val PORTAL_TEXTURE_RETRY_MS = 250L
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var geoGebraPanelEntity: Entity? = null
    private var geoGebraPanelSceneObject: PanelSceneObject? = null
    private var panelTexture: SceneTexture? = null
    private var stereoPortalRenderer: QuestStereoPortalRenderer? = null
    private var pendingStereoLayout: String? = null

    private var sceneReady = false
    private var vrReady = false
    private var webPanelReady = false
    private var portalStartScheduled = false
    private var portalDisabledForLaunch = false

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

                    // Never replace the interactive panel's own mesh. Keep a
                    // reference so getTexture() can be retried if the first call
                    // happens before Spatial has produced the live panel texture.
                    geoGebraPanelSceneObject = panelSceneObject
                    panelTexture = panelSceneObject.getTexture()
                    schedulePortalStartIfReady()
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

                val renderer = stereoPortalRenderer
                if (renderer != null) {
                    renderer.updateLayout(
                        json = layout,
                        panelWidthMeters = PANEL_WIDTH_METERS,
                        panelHeightMeters = PANEL_HEIGHT_METERS,
                    )
                } else {
                    schedulePortalStartIfReady()
                }
            }
        }

        SpatialBridgeBus.onPanelReady = {
            webPanelReady = true
            schedulePortalStartIfReady()
        }

        requestScenePermissionIfNeeded()
    }

    private fun schedulePortalStartIfReady() {
        if (portalDisabledForLaunch || stereoPortalRenderer != null || portalStartScheduled) return
        if (!sceneReady || !vrReady || !webPanelReady) return
        if (geoGebraPanelEntity == null || pendingStereoLayout.isNullOrBlank()) return

        if (panelTexture == null) {
            panelTexture = geoGebraPanelSceneObject?.getTexture()
        }

        if (panelTexture == null) {
            // v0.9.7.1 gave up forever if getTexture() returned null once.
            // Keep the normal panel alive and retry until Spatial publishes it.
            portalStartScheduled = true
            mainHandler.postDelayed(
                {
                    portalStartScheduled = false
                    schedulePortalStartIfReady()
                },
                PORTAL_TEXTURE_RETRY_MS,
            )
            return
        }

        portalStartScheduled = true
        mainHandler.postDelayed(
            {
                portalStartScheduled = false
                createPortalIfStillReady()
            },
            PORTAL_START_DELAY_MS,
        )
    }

    private fun createPortalIfStillReady() {
        if (portalDisabledForLaunch || stereoPortalRenderer != null) return
        if (!sceneReady || !vrReady || !webPanelReady) return

        val parent = geoGebraPanelEntity ?: return
        val texture = panelTexture ?: geoGebraPanelSceneObject?.getTexture() ?: run {
            schedulePortalStartIfReady()
            return
        }
        panelTexture = texture

        val layout = pendingStereoLayout ?: return

        try {
            val renderer =
                QuestStereoPortalRenderer(
                    activity = this,
                    parent = parent,
                    panelTexture = texture,
                )

            stereoPortalRenderer = renderer
            renderer.updateLayout(
                json = layout,
                panelWidthMeters = PANEL_WIDTH_METERS,
                panelHeightMeters = PANEL_HEIGHT_METERS,
            )
            Log.i(TAG, "Stereo eye-pass portal active")
        } catch (error: Throwable) {
            // Never sacrifice the working WebView panel to the stereo overlay.
            portalDisabledForLaunch = true
            stereoPortalRenderer = null
            Log.e(TAG, "Stereo portal disabled for this launch", error)
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
        schedulePortalStartIfReady()
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
        schedulePortalStartIfReady()
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        mainHandler.removeCallbacksAndMessages(null)

        stereoPortalRenderer?.release()
        stereoPortalRenderer = null
        pendingStereoLayout = null
        panelTexture = null
        geoGebraPanelSceneObject = null
        geoGebraPanelEntity = null

        super.onDestroy()
    }
}
