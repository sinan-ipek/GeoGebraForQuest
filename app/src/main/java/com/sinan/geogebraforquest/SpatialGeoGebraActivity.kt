package com.sinan.geogebraforquest

import android.content.pm.PackageManager
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
 * GeoGebraForQuest v0.4.0
 *
 * One activity, one GeoGebra panel, one mixed-reality scene.
 *
 * The application starts spatially in passthrough, but GeoGebra itself remains a
 * normal flat Android/WebView panel. The replacement Anaglyph/headset projection
 * option does NOT launch another activity or another window. It only makes the
 * existing GeoGebra 3D Graphics rectangle transparent and reveals native spatial
 * stereo geometry behind that exact rectangle via hole punching.
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

        // Stereo starts OFF. GeoGebra initially behaves exactly like its normal
        // 3D view. The headset option toggles only the integrated portal later.
        pendingStereo = false

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
        runCatching { scene.enablePassthrough(true) }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_USE_SCENE &&
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

        // Hole punching stays enabled underneath the panel. Nothing appears
        // spatial until JavaScript makes only the 3D Graphics viewport transparent.
        runCatching { scene.enableHolePunching(true) }

        // Put the user about two metres in front of the GeoGebra panel, matching
        // Meta's Spatial SDK sample coordinate convention.
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)
        enablePassthroughWhenSafe()

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
