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
import com.meta.spatial.toolkit.getAbsoluteTransform
import com.meta.spatial.vr.VRFeature

/**
 * v0.9.30-exp2: full-panel alpha diagnostic, based directly on stable v0.9.29.
 *
 * Exp1 proved that the invisible GeoGebra 3D view could still receive ray/controller input, but
 * the rear test panel was hidden by a white layer. Exp2 removes all DOM-specific transparency
 * edits and tests the next layer directly: after a short visible baseline, the entire Android
 * GeoGebra root/WebView is faded to alpha 0 while a bright, non-hittable Spatial panel sits behind
 * the whole GeoGebra panel. If the bright panel appears, Spatial UI-panel alpha composition works.
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

        // Full-size rear panel for the compositor test. Two centimetres is intentionally much
        // larger than the final embedded target offset so there is no ambiguity during diagnosis.
        private const val EMBEDDED_TEST_DEPTH_METERS = 0.020f
        private const val ALPHA_DIAGNOSTIC_DELAY_MS = 10_000L

        private const val TAG = "GeoGebraForQuest"
        private const val PERMISSION_USE_SCENE = "com.oculus.permission.USE_SCENE"
        private const val REQUEST_USE_SCENE = 701

        private val INITIAL_STEREO_POSE = Pose(
            Vector3(1.10f, 1.30f, 1.15f),
            Quaternion(0f, 45f, 0f),
        )

        private val CONTROLLER_PALETTE_POSE = Pose(
            Vector3(-0.13f, 0.01f, 0.10f),
            Quaternion(35f, 0f, -18f),
        )

        private val CONTROLLER_PALETTE_SCALE = Vector3(0.30f, 0.30f, 0.30f)
    }

    private var sceneReady = false
    private var vrReady = false
    private var stereoPanelEntity: Entity? = null
    private var embeddedTestPanelEntity: Entity? = null
    private var stereoSurface: Surface? = null
    private var stereoPaletteAttached = false
    private var stereoPaletteRestorePose: Pose? = null
    private var stereoPaletteRestoreScale: Vector3? = null

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

                    // Exp2 isolates Android/Spatial alpha from the web content itself. The HTML and
                    // stereo-layout script are the stable v0.9.29 versions. We keep the GeoGebra
                    // panel fully visible for ten seconds, then make its entire Android content
                    // optically transparent without disabling the Spatial panel or its input.
                    rootView.setBackgroundColor(Color.TRANSPARENT)
                    webView.setBackgroundColor(Color.TRANSPARENT)
                    rootView.alpha = 1f
                    webView.alpha = 1f
                    rootView.postDelayed(
                        {
                            rootView.alpha = 0f
                            webView.alpha = 0f
                            Log.i(
                                TAG,
                                "embedded-exp2 alpha phase: GeoGebra root/WebView alpha=0; input panel remains active",
                            )
                        },
                        ALPHA_DIAGNOSTIC_DELAY_MS,
                    )
                },
            ),
            LayoutXMLPanelRegistration(
                R.id.embedded_stereo_test_panel,
                layoutIdCreator = { R.layout.spatial_embedded_stereo_test_panel },
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
                    Log.i(TAG, "embedded-exp2 1440x720 stereo VideoSurface attached")
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
                            zIndex = 20,
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
        LiveStereoFrameSink.setEnabled(true)
        systemManager.registerSystem(QuestControllerShortcutSystem(this))
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
            stereoPaletteRestorePose = getAbsoluteTransform(panel)
            stereoPaletteRestoreScale = panel.tryGetComponent<Scale>()?.scale ?: Vector3(1f, 1f, 1f)
            panel.setComponent(TransformParent(rightControllerEntity))
            panel.setComponent(Transform(CONTROLLER_PALETTE_POSE))
            panel.setComponent(Scale(CONTROLLER_PALETTE_SCALE))
            panel.setComponent(Grabbable(false))
            panel.setComponent(Hittable(MeshCollision.NoCollision))
            stereoPaletteAttached = true
            Log.i(TAG, "embedded-exp2 stable palette attached at 30% scale with ray pass-through")
            return
        }

        val restorePose = stereoPaletteRestorePose ?: INITIAL_STEREO_POSE
        val restoreScale = stereoPaletteRestoreScale ?: Vector3(1f, 1f, 1f)
        panel.setComponent(TransformParent())
        panel.setComponent(Transform(restorePose))
        panel.setComponent(Scale(restoreScale))
        panel.tryRemoveComponent<Hittable>()
        panel.setComponent(Grabbable())
        stereoPaletteRestorePose = null
        stereoPaletteRestoreScale = null
        stereoPaletteAttached = false
        Log.i(TAG, "embedded-exp2 stable palette restored")
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

        embeddedTestPanelEntity = Entity(R.id.embedded_stereo_test_panel).also { panel ->
            panel.setComponents(
                listOf(
                    Panel(R.id.embedded_stereo_test_panel),
                    TransformParent(geoPanel),
                    Transform(Pose(Vector3(0f, 0f, EMBEDDED_TEST_DEPTH_METERS))),
                    Scale(Vector3(1f, 1f, 1f)),
                    Hittable(MeshCollision.NoCollision),
                    Visible(true),
                ),
            )
        }

        stereoPanelEntity =
            Entity.create(
                Panel(R.id.geogebra_stereo_panel),
                Transform(INITIAL_STEREO_POSE),
                Scale(Vector3(1f, 1f, 1f)),
                Grabbable(),
            )

        Log.i(
            TAG,
            "embedded-exp2 ready: normal GeoGebra for 10s, then full Android alpha=0 over bright rear panel",
        )
    }

    override fun onDestroy() {
        GeoGebraLocalFilePicker.cancelPending()
        SpatialBridgeBus.clear()
        LiveStereoFrameSink.setEnabled(false)

        stereoSurface?.let { LiveStereoFrameSink.detachSurface(it) }
        stereoSurface = null

        embeddedTestPanelEntity = null

        stereoPanelEntity?.destroy()
        stereoPanelEntity = null
        stereoPaletteRestorePose = null
        stereoPaletteRestoreScale = null
        stereoPaletteAttached = false

        super.onDestroy()
    }
}
