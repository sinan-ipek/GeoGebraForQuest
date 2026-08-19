package com.sinan.geogebraforquest

import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.runtime.StereoMode
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
import com.meta.spatial.toolkit.MediaPanelRenderOptions
import com.meta.spatial.toolkit.MediaPanelSettings
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.PixelDisplayOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature
import org.json.JSONObject

/**
 * GeoGebraForQuest v0.5.1
 *
 * One Spatial activity, one ordinary GeoGebra panel, one eye-selective media
 * surface exactly over GeoGebra's 3D Graphics rectangle.
 *
 * The headset button does NOT launch another activity or immersive mode. It
 * arms capture of GeoGebra's own PROJECTION_GLASSES left/right renders. The
 * stereo media panel remains hidden until the first SBS frame has actually
 * reached its Surface and eglSwapBuffers() succeeds. Therefore a capture miss
 * cannot blank the working GeoGebra 3D view.
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

    private val stereoFrameSurface = StereoFrameSurface()

    private var geoGebraPanelEntity: Entity? = null
    private var stereoPortalEntity: Entity? = null
    private var pendingStereo = false
    private var pendingPortalRect: String? = null
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
            VideoSurfacePanelRegistration(
                R.id.stereo_portal_panel,
                surfaceConsumer = { _, surface ->
                    stereoFrameSurface.attach(surface)
                },
                settingsCreator = {
                    MediaPanelSettings(
                        shape = QuadShapeOptions(width = 1f, height = 1f),
                        display = PixelDisplayOptions(
                            width = StereoFrameSurface.SURFACE_WIDTH,
                            height = StereoFrameSurface.SURFACE_HEIGHT,
                        ),
                        rendering = MediaPanelRenderOptions(
                            stereoMode = StereoMode.LeftRight,
                            zIndex = 1,
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

        SpatialBridgeBus.onStereoChanged = { enabled ->
            pendingStereo = enabled
            if (!enabled) {
                runOnMainThread {
                    stereoPortalEntity?.setComponent(Visible(false))
                }
            }
            // When enabling, deliberately keep the portal hidden. The original
            // GeoGebra canvas remains visible until onStereoFrame has actually
            // presented a valid SBS frame to the Spatial SDK surface.
        }

        SpatialBridgeBus.onPortalRect = { json ->
            pendingPortalRect = json
            runOnMainThread {
                updateStereoPortalTransform(json)
            }
        }

        SpatialBridgeBus.onStereoFrame = { dataUrl, _, _ ->
            if (pendingStereo) {
                stereoFrameSurface.submitDataUrl(dataUrl) {
                    runOnMainThread {
                        if (pendingStereo) {
                            stereoPortalEntity?.setComponent(Visible(true))
                        }
                    }
                }
            }
        }

        SpatialBridgeBus.onPanelReady = {
            // Every visible 3D pixel comes from GeoGebra's renderer; no native
            // object-by-object mirror is created.
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

        val stereoPanel = Entity(R.id.stereo_portal_panel)
        stereoPanel.setComponents(
            listOf(
                Panel(R.id.stereo_portal_panel),
                TransformParent(geoPanel),
                Transform(Pose(Vector3(0f, 0f, -0.006f))),
                Scale(Vector3(0.01f, 0.01f, 1f)),
                Visible(false),
            ),
        )
        stereoPortalEntity = stereoPanel

        pendingPortalRect?.let(::updateStereoPortalTransform)
    }

    private fun updateStereoPortalTransform(json: String) {
        val portal = stereoPortalEntity ?: return

        try {
            val data = JSONObject(json)
            val left = data.optDouble("left", 0.0).toFloat()
            val top = data.optDouble("top", 0.0).toFloat()
            val width = data.optDouble("width", 1.0).toFloat().coerceAtLeast(1f)
            val height = data.optDouble("height", 1.0).toFloat().coerceAtLeast(1f)
            val viewWidth = data.optDouble("viewWidth", PANEL_WIDTH_DP.toDouble())
                .toFloat()
                .coerceAtLeast(1f)
            val viewHeight = data.optDouble("viewHeight", PANEL_HEIGHT_DP.toDouble())
                .toFloat()
                .coerceAtLeast(1f)

            val centerXRatio = (left + width * 0.5f) / viewWidth
            val centerYRatio = (top + height * 0.5f) / viewHeight
            val centerX = (centerXRatio - 0.5f) * PANEL_WIDTH_METERS
            val centerY = (0.5f - centerYRatio) * PANEL_HEIGHT_METERS
            val widthMeters = PANEL_WIDTH_METERS * width / viewWidth
            val heightMeters = PANEL_HEIGHT_METERS * height / viewHeight

            if (
                !centerX.isFinite() || !centerY.isFinite() ||
                !widthMeters.isFinite() || !heightMeters.isFinite() ||
                widthMeters <= 0f || heightMeters <= 0f
            ) {
                return
            }

            portal.setComponents(
                Transform(Pose(Vector3(centerX, centerY, -0.006f))),
                Scale(Vector3(widthMeters, heightMeters, 1f)),
            )
        } catch (_: Throwable) {
            // A transient GeoGebra layout rectangle must never crash Spatial SDK.
        }
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        stereoFrameSurface.release()
        stereoPortalEntity = null
        geoGebraPanelEntity = null
        super.onDestroy()
    }
}
