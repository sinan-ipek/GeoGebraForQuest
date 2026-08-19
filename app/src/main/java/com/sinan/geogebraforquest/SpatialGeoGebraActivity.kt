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
 * GeoGebraForQuest v0.4.2
 *
 * Single-window mixed-reality architecture:
 * - The app starts once as one Spatial SDK activity.
 * - GeoGebra is one normal flat Android/WebView panel in passthrough.
 * - Stereo starts OFF.
 * - Selecting the replacement Anaglyph/headset option does not launch another
 *   Activity or window; only the existing 3D Graphics rectangle becomes the
 *   native stereo depth portal inside the same GeoGebra panel.
 *
 * Important v0.4.2 correction:
 * registered Spatial SDK panels are positioned/activated in onVRReady(), after
 * the VR runtime and panel registrations are ready. This follows Meta's current
 * SpatialVideoSample pattern. v0.4.1 tried to create the registered panel in
 * onSceneReady(), which can leave the user looking only at passthrough.
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
    private var vrReady = false

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
                ensurePortalRenderer()
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

        // Match the coordinate convention used by Meta's current Spatial SDK
        // samples: origin at the user, forward content at positive Z.
        scene.setViewOrigin(0f, 0f, 0f, 0f)
        enablePassthroughWhenSafe()
    }

    override fun onVRReady() {
        super.onVRReady()
        if (vrReady) return
        vrReady = true

        // Meta's current samples configure registered UI panels here, after all
        // panel registrations and the VR runtime are ready. Entity(id) references
        // the registered panel; it should not be recreated as a fresh anonymous
        // Entity in onSceneReady().
        val panel = Entity(R.id.geogebra_panel)
        panel.setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(),
            ),
        )
        panelEntity = panel

        ensurePortalRenderer()
    }

    private fun ensurePortalRenderer() {
        if (portalRenderer != null || !geoGebraPanelReady || !vrReady) {
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
