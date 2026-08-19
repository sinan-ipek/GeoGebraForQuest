package com.sinan.geogebraforquest

import android.os.Bundle
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector2
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.ActivityPanelRegistration
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelDimensions
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature

/**
 * GeoGebraForQuest v0.3
 *
 * There is only one visible GeoGebra window. The app enters Spatial SDK once at
 * startup, embeds the already-proven PancakeActivity as that window, and keeps it
 * fully interactive. The native stereo scene is revealed only through the existing
 * GeoGebra 3D Graphics viewport when the replacement Anaglyph/Headset projection
 * button is selected.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_DP_PER_METER = 720f
    }

    private var panelEntity: Entity? = null
    private var portalRenderer: StereoPortalRenderer? = null

    private var pendingStereo = false
    private var pendingPortalRect: String? = null
    private var pendingScene: String? = null

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(VRFeature(this))
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            ActivityPanelRegistration(
                R.id.geogebra_panel,
                classIdCreator = { PancakeActivity::class.java },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(
                            width = PANEL_WIDTH_METERS,
                            height = PANEL_HEIGHT_METERS,
                        ),
                        display = DpPerMeterDisplayOptions(dpPerMeter = PANEL_DP_PER_METER),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                    )
                },
            ),
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
            // Reserved for diagnostics. The Activity-backed panel itself is the
            // already-proven GeoGebra path, so no second activity transition exists.
        }
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
        scene.enablePassthrough(true)
        scene.enableHolePunching(true)

        // Follow Meta's HybridSample convention: the panel sits near z=0 and the
        // view origin starts two metres away facing it.
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
