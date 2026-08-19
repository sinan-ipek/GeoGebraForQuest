package com.sinan.geogebraforquest

import android.os.Handler
import android.os.Looper
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
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature

/**
 * Spatial host used only after the user requests Stereo 3D.
 *
 * Visually this is still the same GeoGebra panel. Only the rectangle occupied
 * by GeoGebra's 3D Graphics canvas is allowed to reveal native Spatial SDK
 * geometry, which Quest renders independently for the two eyes.
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

    private var pendingStereo = true
    private var pendingPortalRect: String? = null
    private var pendingScene: String? = null
    private var webReady = false

    private val mainHandler = Handler(Looper.getMainLooper())
    private val startupWatchdog = Runnable {
        // Never strand the user in an empty spatial session. If the embedded
        // GeoGebra panel did not report ready, return to the still-running 2D panel.
        if (!webReady && !isFinishing) {
            finish()
        }
    }

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
                            spatialMode = true,
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
                            onReady = {
                                runOnUiThread {
                                    webReady = true
                                    mainHandler.removeCallbacks(startupWatchdog)
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
        scene.enablePassthrough(true)
        scene.enableHolePunching(true)

        // Match Meta's HybridSample convention: the user's view starts two metres
        // from the origin, facing back toward the spatial UI placed near z=0.
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)
    }

    override fun onVRReady() {
        super.onVRReady()

        // Dynamic panels are safest after VR is ready. Use the registered entity
        // ID instead of creating an unrelated anonymous entity.
        val panel = Entity(R.id.geogebra_panel)
        panel.setComponents(
            listOf(
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

        mainHandler.postDelayed(startupWatchdog, 20_000L)
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(startupWatchdog)
        portalRenderer?.destroy()
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
