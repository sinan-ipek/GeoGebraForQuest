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
 * GeoGebraForQuest v0.6.7 — stereo pipeline diagnostic.
 *
 * The rendering path remains the same as v0.6.6: the normal GeoGebra WebView is
 * visible and the StereoMode.LeftRight media surface covers only the 3D Graphics
 * rectangle. This build adds counters only, so a screenshot can tell us whether
 * a direct eye pair reached Android, was accepted by the EGL writer, was actually
 * presented, and whether the portal entity became visible.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701
        private const val PORTAL_Z = -0.006f
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
                    StereoDebugState.onSurfaceAttached()
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
        StereoDebugState.reset()

        SpatialBridgeBus.onStereoChanged = { enabled ->
            pendingStereo = enabled
            StereoDebugState.onStereoChanged(enabled)
            if (!enabled) {
                runOnMainThread {
                    stereoPortalEntity?.setComponent(Visible(false))
                }
            }
        }

        SpatialBridgeBus.onPortalRect = { json ->
            pendingPortalRect = json
            StereoDebugState.onPortalRect()
            applyPortalRect(json)
        }

        SpatialBridgeBus.onStereoFrame = frame@{ dataUrl, eyeWidth, eyeHeight ->
            StereoDebugState.onFrameReceived(eyeWidth, eyeHeight)

            if (!pendingStereo || dataUrl.isBlank()) {
                StereoDebugState.onFrameRejected()
                return@frame
            }

            if (!stereoFrameSurface.canAcceptFrame()) {
                StereoDebugState.onFrameDroppedBusy()
                return@frame
            }

            val accepted = stereoFrameSurface.submitRawStereoDataUrl(
                dataUrl = dataUrl,
                reportedEyeWidth = eyeWidth,
                reportedEyeHeight = eyeHeight,
                onPresented = {
                    StereoDebugState.onFramePresented()
                    runOnMainThread {
                        if (pendingStereo) {
                            pendingPortalRect?.let { applyPortalRect(it) }
                            stereoPortalEntity?.setComponent(Visible(true))
                            StereoDebugState.onPortalVisible()
                        }
                    }
                },
                onFinished = {
                    StereoDebugState.onFrameFinished()
                },
            )

            if (accepted) {
                StereoDebugState.onFrameAccepted()
            } else {
                StereoDebugState.onFrameDroppedBusy()
            }
        }

        SpatialBridgeBus.onPanelReady = {
            // No native GeoGebra geometry mirror is used.
        }

        requestScenePermissionIfNeeded()
    }

    private fun applyPortalRect(json: String) {
        val entity = stereoPortalEntity ?: return

        try {
            val data = JSONObject(json)
            val left = data.optDouble("left", Double.NaN)
            val top = data.optDouble("top", Double.NaN)
            val width = data.optDouble("width", Double.NaN)
            val height = data.optDouble("height", Double.NaN)
            val viewWidth = data.optDouble("viewWidth", Double.NaN)
            val viewHeight = data.optDouble("viewHeight", Double.NaN)

            if (
                !left.isFinite() || !top.isFinite() ||
                !width.isFinite() || !height.isFinite() ||
                !viewWidth.isFinite() || !viewHeight.isFinite() ||
                width <= 0.0 || height <= 0.0 ||
                viewWidth <= 0.0 || viewHeight <= 0.0
            ) {
                return
            }

            val centerXPixels = left + width / 2.0
            val centerYPixels = top + height / 2.0

            val centerX = (
                centerXPixels / viewWidth - 0.5
            ).toFloat() * PANEL_WIDTH_METERS

            val centerY = (
                0.5 - centerYPixels / viewHeight
            ).toFloat() * PANEL_HEIGHT_METERS

            val widthMeters = (
                width / viewWidth
            ).toFloat() * PANEL_WIDTH_METERS

            val heightMeters = (
                height / viewHeight
            ).toFloat() * PANEL_HEIGHT_METERS

            runOnMainThread {
                entity.setComponent(
                    Transform(
                        Pose(
                            Vector3(
                                centerX,
                                centerY,
                                PORTAL_Z,
                            ),
                        ),
                    ),
                )
                entity.setComponent(
                    Scale(
                        Vector3(
                            widthMeters,
                            heightMeters,
                            1f,
                        ),
                    ),
                )
            }
        } catch (_: Throwable) {
            // Ignore one malformed or transient DOM rectangle.
        }
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

        val stereoPanel = Entity(R.id.stereo_portal_panel)
        stereoPanel.setComponents(
            listOf(
                Panel(R.id.stereo_portal_panel),
                TransformParent(geoPanel),
                Transform(Pose(Vector3(0f, 0f, PORTAL_Z))),
                Scale(Vector3(0.01f, 0.01f, 1f)),
                Visible(false),
            ),
        )
        stereoPortalEntity = stereoPanel
        StereoDebugState.onPortalEntityReady()

        pendingPortalRect?.let { applyPortalRect(it) }
    }

    override fun onDestroy() {
        SpatialBridgeBus.clear()
        stereoFrameSurface.release()
        stereoPortalEntity = null
        geoGebraPanelEntity = null
        super.onDestroy()
    }
}
