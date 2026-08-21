package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SpatialSDKExperimentalAPI
import com.meta.spatial.core.Vector3
import com.meta.spatial.core.Vector4
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
 * GeoGebraForQuest v0.9.0.
 *
 * There is one GeoGebra panel and one input surface. GeoGebra itself renders
 * the 3D canvas as full-colour SBS on the GPU. A full-panel, non-hittable visual
 * mesh samples the live panel SceneTexture per eye; ordinary UI stays mono while
 * only the 3D rectangle becomes stereo. No 3D-window overlay/panel is created.
 */
@OptIn(SpatialSDKExperimentalAPI::class)
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701

        // Keep the real Android panel composited so its live texture/input path
        // cannot be optimized away, while making it visually imperceptible.
        private const val INPUT_LAYER_ALPHA = 0.001f
    }

    private var geoGebraPanelEntity: Entity? = null
    private var geoGebraPanelTexture: SceneTexture? = null
    private var stereoPanelVisual: QuestStereoPanelRenderer? = null
    private var pendingStereoLayout: String? = null

    private var sceneReady = false
    private var vrReady = false

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

                    // Spatial SDK already owns the continuously updated GPU
                    // texture for this Android panel. Reuse it; never read it
                    // back through CPU memory.
                    geoGebraPanelTexture = panelSceneObject.getTexture()

                    // The same PanelSceneObject must stay alive because it is
                    // the controller/input target. We only suppress its default
                    // visual layer; QuestStereoPanelRenderer becomes the visible
                    // representation of this exact same panel.
                    panelSceneObject.getLayer()?.setColorScaleBias(
                        Vector4(1f, 1f, 1f, INPUT_LAYER_ALPHA),
                        Vector4(0f),
                    )

                    runOnUiThread { ensureStereoPanelVisual() }
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()

        SpatialBridgeBus.onStereoLayout = { json ->
            pendingStereoLayout = json
            runOnUiThread {
                ensureStereoPanelVisual()
                stereoPanelVisual?.updateLayout(json)
            }
        }
        SpatialBridgeBus.onPanelReady = {
            runOnUiThread { ensureStereoPanelVisual() }
        }

        requestScenePermissionIfNeeded()
    }

    private fun ensureStereoPanelVisual() {
        if (stereoPanelVisual != null) return
        val parent = geoGebraPanelEntity ?: return
        val texture = geoGebraPanelTexture ?: return

        stereoPanelVisual = QuestStereoPanelRenderer(
            activity = this,
            parent = parent,
            panelTexture = texture,
            panelWidthMeters = PANEL_WIDTH_METERS,
            panelHeightMeters = PANEL_HEIGHT_METERS,
        )

        pendingStereoLayout?.let { stereoPanelVisual?.updateLayout(it) }
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
        ensureStereoPanelVisual()
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        stereoPanelVisual?.release()
        stereoPanelVisual = null
        geoGebraPanelTexture = null
        geoGebraPanelEntity = null
        super.onDestroy()
    }
}
