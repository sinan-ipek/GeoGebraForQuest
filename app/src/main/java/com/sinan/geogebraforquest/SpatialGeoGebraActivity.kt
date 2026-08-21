package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
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
 * GeoGebraForQuest v0.8.0 source-stereo host.
 *
 * GeoGebra itself now renders a full-colour SBS pair directly in its WebGL
 * drawing buffer. Spatial SDK already owns a GPU texture for this WebView panel;
 * QuestStereoPortalRenderer samples that same texture per eye. No frame leaves
 * the GPU, and the old readPixels/JPEG/Base64/Bitmap/VideoSurface path is gone.
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

    private var geoGebraPanelEntity: Entity? = null
    private var geoGebraPanelTexture: SceneTexture? = null
    private var stereoPortal: QuestStereoPortalRenderer? = null

    private var pendingStereo = false
    private var pendingPortalVisible = false
    private var pendingPortalRect: String? = null
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
                        shape =
                            QuadShapeOptions(
                                width = PANEL_WIDTH_METERS,
                                height = PANEL_HEIGHT_METERS,
                            ),
                        display =
                            DpDisplayOptions(
                                width = PANEL_WIDTH_DP,
                                height = PANEL_HEIGHT_DP,
                            ),
                        style =
                            PanelStyleOptions(
                                themeResourceId = R.style.PanelAppThemeTransparent,
                            ),
                    )
                },
                panelSetupWithRootView = { rootView, panelSceneObject, _ ->
                    val webView = rootView.findViewById<WebView>(R.id.geogebra_webview)
                    configureGeoGebraWebView(
                        webView = webView,
                        spatialMode = true,
                        startStereo = false,
                    )

                    // Spatial SDK's LayoutXML panel already has a live GPU texture.
                    // Reuse it directly as the stereo source; there is no copy.
                    geoGebraPanelTexture = panelSceneObject.getTexture()
                    runOnUiThread { ensureStereoPortal() }
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()

        SpatialBridgeBus.onStereoChanged = { enabled ->
            pendingStereo = enabled
            StereoDebugState.onStereoChanged(enabled)
            runOnUiThread { applyPortalVisibility() }
        }

        SpatialBridgeBus.onPortalVisibilityChanged = { visible ->
            pendingPortalVisible = visible
            StereoDebugState.onPortalPresentationAllowed(visible)
            runOnUiThread { applyPortalVisibility() }
        }

        SpatialBridgeBus.onPortalRect = { json ->
            pendingPortalRect = json
            StereoDebugState.onPortalRect()
            runOnUiThread {
                ensureStereoPortal()
                stereoPortal?.updateRect(
                    json = json,
                    panelWidthMeters = PANEL_WIDTH_METERS,
                    panelHeightMeters = PANEL_HEIGHT_METERS,
                )
            }
        }

        // v0.8.0 deliberately has no frame callback. The source-rendered SBS
        // image never crosses JavaScript/Android memory.
        SpatialBridgeBus.onStereoFrame = null
        SpatialBridgeBus.onPanelReady = {
            runOnUiThread { ensureStereoPortal() }
        }

        requestScenePermissionIfNeeded()
    }

    private fun ensureStereoPortal() {
        if (stereoPortal != null) return
        val parent = geoGebraPanelEntity ?: return
        val texture = geoGebraPanelTexture ?: return

        stereoPortal =
            QuestStereoPortalRenderer(
                activity = this,
                parent = parent,
                panelTexture = texture,
            )

        StereoDebugState.onPortalEntityReady()
        StereoDebugState.onSurfaceAttached()
        StereoDebugState.onPortalNonHittable()

        pendingPortalRect?.let {
            stereoPortal?.updateRect(
                json = it,
                panelWidthMeters = PANEL_WIDTH_METERS,
                panelHeightMeters = PANEL_HEIGHT_METERS,
            )
        }
        applyPortalVisibility()
    }

    private fun applyPortalVisibility() {
        ensureStereoPortal()
        val visible = pendingStereo && pendingPortalVisible
        stereoPortal?.setVisible(visible)
        if (visible) StereoDebugState.onPortalVisible()
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

        ensureStereoPortal()
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        stereoPortal?.release()
        stereoPortal = null
        geoGebraPanelTexture = null
        geoGebraPanelEntity = null
        super.onDestroy()
    }
}
