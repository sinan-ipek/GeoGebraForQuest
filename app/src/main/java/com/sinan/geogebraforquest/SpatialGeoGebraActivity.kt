package com.sinan.geogebraforquest

import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Surface
import android.webkit.WebView
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ButtonBits
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.runtime.StereoMode
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Hittable
import com.meta.spatial.toolkit.LayoutXMLPanelRegistration
import com.meta.spatial.toolkit.MediaPanelRenderOptions
import com.meta.spatial.toolkit.MediaPanelSettings
import com.meta.spatial.toolkit.MeshCollision
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelInputOptions
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
 * v0.9.30-exp5: embedded-stereo layering and fill test.
 *
 * Exp4 successfully replaced the magenta proof panel with the real SBS VideoSurface at 3 mm.
 * Exp5 keeps that geometry unchanged and lowers the VideoSurface compositor z-index from 20 to 0
 * so GeoGebra UI/menu layers can remain visually in front while the stereo image is visible through
 * the selective 3D hole. C remains at the established 10 cm safety depth with 106% overscan.
 *
 * Live eye frames are also stretched to fill each half of the SBS texture in LiveStereoFrameSink;
 * the physical stereo panel's dynamic non-uniform scale then restores the GeoGebra 3D-view aspect.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    companion object {
        const val PANEL_WIDTH_METERS = 1.50f
        const val PANEL_HEIGHT_METERS = 1.00f
        const val PANEL_WIDTH_DP = 1080f
        const val PANEL_HEIGHT_DP = 720f

        private const val STEREO_PANEL_WIDTH_METERS = 0.82f
        private const val STEREO_PANEL_HEIGHT_METERS = 0.82f
        private const val STEREO_TEXTURE_WIDTH = 1440
        private const val STEREO_TEXTURE_HEIGHT = 720

        private const val EMBEDDED_STEREO_DEPTH_METERS = 0.003f
        private const val EMBEDDED_BACKPLATE_DEPTH_METERS = 0.10f
        private val EMBEDDED_BACKPLATE_SCALE = Vector3(1.06f, 1.06f, 1f)

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701

        private val CONTROLLER_PALETTE_POSE = Pose(
            Vector3(-0.13f, 0.01f, 0.10f),
            Quaternion(35f, 0f, -18f),
        )

        private val CONTROLLER_PALETTE_SCALE = Vector3(0.30f, 0.30f, 0.30f)
    }

    private var sceneReady = false
    private var vrReady = false
    private var geoPanelEntity: Entity? = null
    private var stereoPanelEntity: Entity? = null
    private var embeddedBackplateEntity: Entity? = null
    private var stereoSurface: Surface? = null
    private var stereoPaletteAttached = false

    private var embeddedStereoPose = Pose(Vector3(0f, 0f, EMBEDDED_STEREO_DEPTH_METERS))
    private var embeddedStereoScale = Vector3(0.01f, 0.01f, 1f)
    private var embeddedStereoVisible = false

    @Volatile
    private var pendingEmbeddedLayout: String? = null
    private var lastAppliedEmbeddedLayout: String? = null

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
                        input = PanelInputOptions(
                            ButtonBits.ButtonTriggerL or ButtonBits.ButtonTriggerR,
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
                        hostActivity = this,
                    )

                    // JavaScript owns the selective 3D hole. C remains solid white 10 cm behind A
                    // with centered 6% overscan. The live stereo VideoSurface fills the hole.
                    rootView.setBackgroundColor(Color.TRANSPARENT)
                    webView.setBackgroundColor(Color.TRANSPARENT)
                    rootView.alpha = 1f
                    webView.alpha = 1f
                },
            ),
            LayoutXMLPanelRegistration(
                R.id.embedded_backplate_panel,
                layoutIdCreator = { R.layout.spatial_embedded_backplate_panel },
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
            ),
            VideoSurfacePanelRegistration(
                R.id.geogebra_stereo_panel,
                surfaceConsumer = { _, surface ->
                    stereoSurface?.let { previous ->
                        if (previous !== surface) {
                            LiveStereoFrameSink.detachSurface(previous)
                        }
                    }

                    stereoSurface = surface
                    LiveStereoFrameSink.attachSurface(surface, resources)
                    LiveStereoFrameSink.setEnabled(true)
                    Log.i(TAG, "embedded-exp5 1440x720 live stereo VideoSurface attached")
                },
                settingsCreator = {
                    MediaPanelSettings(
                        shape = QuadShapeOptions(
                            width = STEREO_PANEL_WIDTH_METERS,
                            height = STEREO_PANEL_HEIGHT_METERS,
                        ),
                        display = PixelDisplayOptions(
                            width = STEREO_TEXTURE_WIDTH,
                            height = STEREO_TEXTURE_HEIGHT,
                        ),
                        rendering = MediaPanelRenderOptions(
                            stereoMode = StereoMode.LeftRight,
                            zIndex = 0,
                        ),
                    )
                },
            ),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        StereoDebugState.reset()
        SpatialBridgeBus.clear()
        SpatialBridgeBus.onStereoLayout = { json -> pendingEmbeddedLayout = json }
        LiveStereoFrameSink.setEnabled(true)
        systemManager.registerSystem(QuestControllerShortcutSystem(this))
        systemManager.registerSystem(EmbeddedStereoTestSystem(this))
        requestScenePermissionIfNeeded()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (!GeoGebraWebNavigation.handleBack()) {
            super.onBackPressed()
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (GeoGebraLocalFilePicker.handleActivityResult(requestCode, resultCode, data)) {
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    internal fun onQuestAButtonPressed() {
        GeoGebraWebNavigation.toggleContextMenu()
    }

    internal fun onQuestBButtonPressed(rightControllerEntity: Entity) {
        val panel = stereoPanelEntity ?: return

        if (!stereoPaletteAttached) {
            panel.setComponent(TransformParent(rightControllerEntity))
            panel.setComponent(Transform(CONTROLLER_PALETTE_POSE))
            panel.setComponent(Scale(CONTROLLER_PALETTE_SCALE))
            panel.setComponent(Grabbable(false))
            panel.setComponent(Hittable(MeshCollision.NoCollision))
            panel.setComponent(Visible(true))
            stereoPaletteAttached = true
            Log.i(TAG, "embedded-exp5 live stereo palette attached at 30% scale with ray pass-through")
            return
        }

        val geoPanel = geoPanelEntity ?: return
        panel.setComponent(TransformParent(geoPanel))
        panel.setComponent(Transform(embeddedStereoPose))
        panel.setComponent(Scale(embeddedStereoScale))
        panel.setComponent(Grabbable(false))
        panel.setComponent(Hittable(MeshCollision.NoCollision))
        panel.setComponent(Visible(embeddedStereoVisible))
        stereoPaletteAttached = false
        Log.i(TAG, "embedded-exp5 live stereo palette restored to 3D view")
    }

    /** Runs on the Spatial system thread via EmbeddedStereoTestSystem. */
    internal fun applyPendingEmbeddedLayout() {
        val panel = stereoPanelEntity ?: return
        val json = pendingEmbeddedLayout ?: return
        if (json == lastAppliedEmbeddedLayout) return
        lastAppliedEmbeddedLayout = json

        try {
            val root = JSONObject(json)
            if (!root.optBoolean("active", true)) {
                embeddedStereoVisible = false
                if (!stereoPaletteAttached) {
                    panel.setComponent(Visible(false))
                }
                return
            }

            val stereo = root.optJSONObject("stereo") ?: return
            val viewWidth = root.optDouble("viewWidth", 0.0)
            val viewHeight = root.optDouble("viewHeight", 0.0)
            val left = stereo.optDouble("left", 0.0)
            val top = stereo.optDouble("top", 0.0)
            val width = stereo.optDouble("width", 0.0)
            val height = stereo.optDouble("height", 0.0)

            if (viewWidth <= 1.0 || viewHeight <= 1.0 || width <= 1.0 || height <= 1.0) {
                embeddedStereoVisible = false
                if (!stereoPaletteAttached) {
                    panel.setComponent(Visible(false))
                }
                return
            }

            val widthMeters = (PANEL_WIDTH_METERS * width / viewWidth).toFloat()
            val heightMeters = (PANEL_HEIGHT_METERS * height / viewHeight).toFloat()
            val centerX = (
                PANEL_WIDTH_METERS * ((left + width * 0.5) / viewWidth - 0.5)
            ).toFloat()
            val centerY = (
                PANEL_HEIGHT_METERS * (0.5 - (top + height * 0.5) / viewHeight)
            ).toFloat()

            embeddedStereoPose = Pose(
                Vector3(centerX, centerY, EMBEDDED_STEREO_DEPTH_METERS),
            )
            embeddedStereoScale = Vector3(
                widthMeters / STEREO_PANEL_WIDTH_METERS,
                heightMeters / STEREO_PANEL_HEIGHT_METERS,
                1f,
            )
            embeddedStereoVisible = true

            if (!stereoPaletteAttached) {
                panel.setComponent(Transform(embeddedStereoPose))
                panel.setComponent(Scale(embeddedStereoScale))
                panel.setComponent(Visible(true))
            }
        } catch (t: Throwable) {
            Log.w(TAG, "embedded-exp5 live stereo layout parse/apply failed", t)
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
        geoPanelEntity = geoPanel
        geoPanel.setComponents(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.25f, 1.50f))),
                Grabbable(),
            ),
        )

        embeddedBackplateEntity = Entity(R.id.embedded_backplate_panel).also { panel ->
            panel.setComponents(
                listOf(
                    Panel(R.id.embedded_backplate_panel),
                    TransformParent(geoPanel),
                    Transform(Pose(Vector3(0f, 0f, EMBEDDED_BACKPLATE_DEPTH_METERS))),
                    Scale(EMBEDDED_BACKPLATE_SCALE),
                    Hittable(MeshCollision.NoCollision),
                    Visible(true),
                ),
            )
        }

        stereoPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_stereo_panel),
                TransformParent(geoPanel),
                Transform(embeddedStereoPose),
                Scale(embeddedStereoScale),
                Grabbable(false),
                Hittable(MeshCollision.NoCollision),
                Visible(false),
            )

        Log.i(
            TAG,
            "embedded-exp5 ready: A GeoGebra, live SBS stereo at 3mm zIndex=0, solid white C at 10cm and 106% scale",
        )
    }

    override fun onDestroy() {
        GeoGebraLocalFilePicker.cancelPending()
        SpatialBridgeBus.clear()
        LiveStereoFrameSink.setEnabled(false)

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null

        embeddedBackplateEntity = null
        geoPanelEntity = null
        pendingEmbeddedLayout = null
        lastAppliedEmbeddedLayout = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null
        stereoPaletteAttached = false
        embeddedStereoVisible = false

        super.onDestroy()
    }
}
