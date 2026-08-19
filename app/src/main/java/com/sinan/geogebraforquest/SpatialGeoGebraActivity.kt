package com.sinan.geogebraforquest

import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.composePanel
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector2
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.LayerConfig
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelDimensions
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.2
 *
 * The whole app runs inside Spatial SDK from launch, but it intentionally presents just one
 * ordinary GeoGebra panel. This lets us keep the original 2D GeoGebra interface while using
 * a true stereo Spatial SDK layer only behind the 3D graphics viewport.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f
    }

    private var panelEntity: Entity? = null
    private var portalRenderer: StereoPortalRenderer? = null

    private var pendingStereo = false
    private var pendingPortalRect: String? = null
    private var pendingScene: String? = null

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(
            VRFeature(this),
            ComposeFeature(),
        )
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            PanelRegistration(R.id.geogebra_panel) {
                config {
                    themeResourceId = R.style.PanelAppThemeTransparent
                    layoutWidthInDp = PANEL_WIDTH_DP
                    layoutHeightInDp = PANEL_HEIGHT_DP
                    layerConfig = LayerConfig()
                    enableTransparent = true
                    includeGlass = false
                }

                composePanel {
                    setContent {
                        GeoGebraWebPanel(
                            onStereoChanged = { enabled ->
                                runOnUiThread {
                                    pendingStereo = enabled
                                    portalRenderer?.setStereoEnabled(enabled)
                                }
                            },
                            onPortalRect = { json ->
                                runOnUiThread {
                                    pendingPortalRect = json
                                    portalRenderer?.updatePortalRect(json)
                                }
                            },
                            onSceneChanged = { json ->
                                runOnUiThread {
                                    pendingScene = json
                                    portalRenderer?.updateScene(json)
                                }
                            },
                        )
                    }
                }
            },
        )
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)

        // No black "second VR room": the user keeps seeing the real world while GeoGebra
        // floats in front of them. Hole punching is used only for the 3D viewport.
        scene.enablePassthrough(true)
        scene.enableHolePunching(true)
        scene.setViewOrigin(0f, 0f, 0f, 0f)

        val panel = Entity.create(
            listOf(
                PanelDimensions(Vector2(PANEL_WIDTH_METERS, PANEL_HEIGHT_METERS)),
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.30f, 2.0f))),
            ),
        )
        panelEntity = panel

        portalRenderer = StereoPortalRenderer(
            panelEntity = panel,
            panelWidthMeters = PANEL_WIDTH_METERS,
            panelHeightMeters = PANEL_HEIGHT_METERS,
        ).also { renderer ->
            pendingPortalRect?.let(renderer::updatePortalRect)
            pendingScene?.let(renderer::updateScene)
            renderer.setStereoEnabled(pendingStereo)
        }
    }

    override fun onDestroy() {
        portalRenderer?.destroy()
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
