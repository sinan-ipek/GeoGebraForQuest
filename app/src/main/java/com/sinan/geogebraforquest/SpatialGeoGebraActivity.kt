package com.sinan.geogebraforquest

import android.os.Bundle
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector2
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
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
 * v0.3.6 uses Spatial SDK's native LayoutXMLPanelRegistration for WebView, the
 * same supported pattern demonstrated by Meta's MediaPlayerSample. This avoids
 * both unstable paths we tried before: WebView inside a Spatial Compose panel and
 * a nested ActivityPanel hosting the WebView.
 *
 * The spatial host recreates the same GeoGebra panel and reveals native stereo
 * only through the existing 3D Graphics viewport.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val EXTRA_START_STEREO = "start_stereo"
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
    private var geoGebraPanelReady = false

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
                        startStereo = true,
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
                if (geoGebraPanelReady) {
                    ensurePortalRenderer()
                }
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
            runOnUiThread {
                geoGebraPanelReady = true
                ensurePortalRenderer()
            }
        }
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
        runCatching { scene.enableHolePunching(true) }
        runCatching { scene.enablePassthrough(true) }
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)

        // Create the Android/WebView panel using the same stage at which Meta's
        // official immersive samples initialize their entities.
        panelEntity = runCatching {
            Entity.create(
                listOf(
                    Grabbable(type = GrabbableType.PIVOT_Y),
                    Panel(R.id.geogebra_panel),
                    PanelDimensions(Vector2(PANEL_WIDTH_METERS, PANEL_HEIGHT_METERS)),
                    Transform(Pose(Vector3(0f, 1.30f, 0f))),
                    Visible(true),
                ),
            )
        }.getOrNull()
    }

    private fun ensurePortalRenderer() {
        if (portalRenderer != null || !geoGebraPanelReady) {
            return
        }

        val panel = panelEntity ?: return
        val renderer = runCatching {
            StereoPortalRenderer(
                panelEntity = panel,
                panelWidthMeters = PANEL_WIDTH_METERS,
                panelHeightMeters = PANEL_HEIGHT_METERS,
            )
        }.getOrNull() ?: return

        portalRenderer = renderer
        pendingPortalRect?.let { runCatching { renderer.updatePortalRect(it) } }
        pendingScene?.let { runCatching { renderer.updateScene(it) } }
        runCatching { renderer.setStereoEnabled(pendingStereo) }
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        runCatching { portalRenderer?.destroy() }
        portalRenderer = null
        panelEntity = null
        super.onDestroy()
    }
}
