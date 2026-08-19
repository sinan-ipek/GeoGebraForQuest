package com.sinan.geogebraforquest

import android.os.Bundle
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
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelDimensions
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature

/**
 * Spatial half of the safe hybrid architecture.
 *
 * The app does NOT launch here. It first opens the known-good normal 2D GeoGebra
 * panel. Only when the user selects the headset icon in GeoGebra's projection menu
 * do we enter this Activity. The visible UI is then recreated as one transparent
 * Spatial SDK Compose panel; native stereo is revealed only through the 3D viewport.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val EXTRA_START_STEREO = "start_stereo"
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
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
                    layoutWidthInDp = 1080f
                    layoutHeightInDp = 720f
                    layerConfig = LayerConfig()
                    enableTransparent = true
                    includeGlass = false
                }
                composePanel {
                    setContent {
                        GeoGebraWebPanel(
                            spatialMode = true,
                            startStereo = true,
                        )
                    }
                }
            },
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        SpatialBridgeBus.onStereoChanged = { enabled ->
            runOnUiThread {
                pendingStereo = enabled
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
            // The page itself drives the initial Stereo ON request after its 3D
            // WebGL viewport exists. Nothing has to be created from this callback.
        }
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)

        // These calls are intentionally guarded: a Horizon runtime difference must
        // never be able to crash the whole app at startup again.
        runCatching { scene.enablePassthrough(true) }
        runCatching { scene.enableHolePunching(true) }

        scene.setViewOrigin(0f, 0f, 2.0f, 180f)
    }

    override fun onVRReady() {
        super.onVRReady()

        val panel = Entity.create(
            listOf(
                Grabbable(type = GrabbableType.PIVOT_Y),
                Panel(R.id.geogebra_panel),
                PanelDimensions(Vector2(PANEL_WIDTH_METERS, PANEL_HEIGHT_METERS)),
                Transform(Pose(Vector3(0f, 1.30f, 0f))),
                Visible(true),
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
        SpatialBridgeBus.clear()
        portalRenderer?.destroy()
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
