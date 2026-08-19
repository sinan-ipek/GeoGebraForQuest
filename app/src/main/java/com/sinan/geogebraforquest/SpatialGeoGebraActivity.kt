package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
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
 * GeoGebraForQuest v0.4.1
 *
 * Single-window mixed-reality architecture:
 * - The app starts once as a Spatial SDK activity.
 * - One Android/WebView GeoGebra panel is placed in front of the user.
 * - Stereo starts OFF, so GeoGebra initially looks like an ordinary flat app.
 * - Selecting the replacement Anaglyph/headset option does NOT launch a second
 *   Activity or window. Only the existing 3D Graphics rectangle becomes a native
 *   stereo depth portal inside the same GeoGebra panel.
 *
 * v0.4.0 could show only passthrough because panel creation silently swallowed a
 * failure while adding components that LayoutXMLPanelRegistration does not need.
 * v0.4.1 follows Meta's Object3DSampleIsdk pattern exactly: create the registered
 * panel entity with Panel + Transform + Grabbable only. The registration itself
 * owns the panel's physical/display dimensions.
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

    private var panelEntity: Entity? = null
    private var portalRenderer: StereoPortalRenderer? = null

    private var pendingStereo = false
    private var pendingPortalRect: String? = null
    private var pendingScene: String? = null
    private var geoGebraPanelReady = false
    private var sceneReady = false

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
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        pendingStereo = false

        SpatialBridgeBus.onStereoChanged = { enabled ->
            runOnUiThread {
                pendingStereo = enabled
                if (geoGebraPanelReady) {
                    ensurePortalRenderer()
                }
                portalRenderer?.setStereoEnabled(enabled)
            }
        }

        SpatialBridgeBus.onPortalRect = { json ->
            runOnUiThread {
                pendingPortalRect = json
                portalRenderer?.updatePortalRect(json)
            }
        }

        SpatialBridgeBus.onSceneChanged = { json ->
            runOnUiThread {
                pendingScene = json
                portalRenderer?.updateScene(json)
            }
        }

        SpatialBridgeBus.onPanelReady = {
            runOnUiThread {
                geoGebraPanelReady = true
                ensurePortalRenderer()
            }
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
        scene.enableHolePunching(true)

        // Same coordinate convention as Meta's HybridSample: the viewer begins
        // around z=2 and faces the content placed around z=0.
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)
        enablePassthroughWhenSafe()

        // IMPORTANT: LayoutXMLPanelRegistration already owns width/height/display
        // configuration. Meta's official Object3DSampleIsdk creates a registered
        // XML panel entity using these three components only. v0.4.0 added
        // PanelDimensions/Visible and then swallowed any exception, which could
        // leave panelEntity null and produce exactly the "room only" symptom.
        panelEntity = Entity.create(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.30f, 0f))),
                Grabbable(),
            ),
        )
    }

    private fun ensurePortalRenderer() {
        if (portalRenderer != null || !geoGebraPanelReady) {
            return
        }

        val panel = panelEntity ?: return
        val renderer = StereoPortalRenderer(
            panelEntity = panel,
            panelWidthMeters = PANEL_WIDTH_METERS,
            panelHeightMeters = PANEL_HEIGHT_METERS,
        )

        portalRenderer = renderer
        pendingPortalRect?.let(renderer::updatePortalRect)
        pendingScene?.let(renderer::updateScene)
        renderer.setStereoEnabled(pendingStereo)
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        portalRenderer?.destroy()
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
