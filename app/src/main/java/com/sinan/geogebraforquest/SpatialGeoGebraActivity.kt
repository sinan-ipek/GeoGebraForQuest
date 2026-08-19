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
 * Spatial half of GeoGebraForQuest.
 *
 * v0.3.5 deliberately follows Meta's supported ActivityPanelRegistration path
 * for Android UI. The normal app starts as the proven 2D GeoGebra panel. Only
 * after the user chooses the headset icon do we start this spatial host.
 *
 * The spatial host then shows the same GeoGebra UI through SpatialPanelActivity,
 * while the native stereo scene is revealed only through the 3D Graphics area.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val EXTRA_START_STEREO = "start_stereo"
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
        // ActivityPanelRegistration does not need ComposeFeature. Keeping the
        // feature list minimal removes the unsupported WebView-in-Compose-panel
        // path that caused v0.3.4 to terminate when entering stereo mode.
        return listOf(VRFeature(this))
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            ActivityPanelRegistration(
                R.id.geogebra_panel,
                classIdCreator = { SpatialPanelActivity::class.java },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(
                            width = PANEL_WIDTH_METERS,
                            height = PANEL_HEIGHT_METERS,
                        ),
                        display = DpPerMeterDisplayOptions(
                            dpPerMeter = PANEL_DP_PER_METER,
                        ),
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

        pendingStereo = intent?.getBooleanExtra(EXTRA_START_STEREO, false) == true

        SpatialBridgeBus.onStereoChanged = { enabled ->
            runOnUiThread {
                pendingStereo = enabled
                runCatching { portalRenderer?.setStereoEnabled(enabled) }
            }
        }

        SpatialBridgeBus.onPortalRect = { json ->
            runOnUiThread {
                pendingPortalRect = json
                runCatching { portalRenderer?.updatePortalRect(json) }
            }
        }

        SpatialBridgeBus.onSceneChanged = { json ->
            runOnUiThread {
                pendingScene = json
                runCatching { portalRenderer?.updateScene(json) }
            }
        }

        SpatialBridgeBus.onPanelReady = {
            // The embedded GeoGebra page drives the stereo request once its 3D
            // Graphics canvas exists.
        }
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)

        // Hole punching is the official Spatial SDK mechanism that lets native
        // spatial content appear through a transparent panel region.
        runCatching { scene.enableHolePunching(true) }

        // Passthrough is optional on some runtime configurations. Failure here
        // must not terminate the application.
        runCatching { scene.enablePassthrough(true) }

        scene.setViewOrigin(0f, 0f, 2.0f, 180f)
    }

    override fun onVRReady() {
        super.onVRReady()

        // Build only the supported panel first. If the native mirror has a
        // problem, GeoGebra itself must remain visible rather than killing the
        // whole spatial session.
        val panel = runCatching {
            Entity.create(
                listOf(
                    Grabbable(type = GrabbableType.PIVOT_Y),
                    Panel(R.id.geogebra_panel),
                    PanelDimensions(Vector2(PANEL_WIDTH_METERS, PANEL_HEIGHT_METERS)),
                    Transform(Pose(Vector3(0f, 1.30f, 0f))),
                    Visible(true),
                ),
            )
        }.getOrNull() ?: return

        panelEntity = panel

        portalRenderer = runCatching {
            StereoPortalRenderer(
                panelEntity = panel,
                panelWidthMeters = PANEL_WIDTH_METERS,
                panelHeightMeters = PANEL_HEIGHT_METERS,
            )
        }.getOrNull()

        portalRenderer?.let { renderer ->
            pendingPortalRect?.let { runCatching { renderer.updatePortalRect(it) } }
            pendingScene?.let { runCatching { renderer.updateScene(it) } }
            runCatching { renderer.setStereoEnabled(pendingStereo) }
        }
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        runCatching { portalRenderer?.destroy() }
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
