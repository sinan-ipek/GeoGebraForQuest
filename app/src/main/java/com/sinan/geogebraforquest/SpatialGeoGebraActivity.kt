package com.sinan.geogebraforquest

import androidx.compose.ui.platform.ComposeView
import androidx.core.net.toUri
import com.meta.spatial.castinputforward.CastInputForwardFeature
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Box
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.vr.VRFeature

/**
 * First native vertical slice of the "3D window inside GeoGebra" idea.
 *
 * v0.1 deliberately renders a demo sphere/axes behind the transparent part
 * of the GeoGebra panel. The next version will replace these demo entities
 * with geometry synchronized from the actual GeoGebra 3D construction.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    private val portalEntities = mutableListOf<Entity>()
    private val portalScales = mutableMapOf<Long, Vector3>()

    override fun registerFeatures(): List<SpatialFeature> {
        val features = mutableListOf<SpatialFeature>(VRFeature(this), ComposeFeature())
        if (BuildConfig.DEBUG) {
            features.add(CastInputForwardFeature(this))
        }
        return features
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
        scene.setLightingEnvironment(
            ambientColor = Vector3(0.35f),
            sunColor = Vector3(4.5f, 4.5f, 4.5f),
            sunDirection = -Vector3(1.0f, 3.0f, -2.0f),
            environmentIntensity = 0.35f,
        )

        // Transparent pixels in the Android panel reveal spatial geometry behind it.
        scene.enableHolePunching(true)
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)

        // GeoGebra panel: roughly a 16:10 desktop window in front of the user.
        Entity.create(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.35f, 0f))),
            ),
        )

        createPortalDemo()
        setPortalVisible(true)
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            ComposeViewPanelRegistration(
                R.id.geogebra_panel,
                composeViewCreator = { _, context ->
                    ComposeView(context).apply {
                        setContent {
                            GeoGebraWebPanel(
                                spatialMode = true,
                                onPortalChanged = { enabled ->
                                    runOnUiThread { setPortalVisible(enabled) }
                                },
                            )
                        }
                    }
                },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(width = 1.28f, height = 0.80f),
                        style = PanelStyleOptions(themeResourceId = R.style.PanelAppThemeTransparent),
                        display = DpPerMeterDisplayOptions(),
                    )
                },
            ),
        )
    }

    private fun createPortalDemo() {
        // The portal sits just behind the right-hand graphics area of the panel.
        val portalCenter = Vector3(0.22f, 1.34f, -0.18f)

        val sphere = Entity.create(
            listOf(
                Mesh("mesh://sphere".toUri()),
                Material().apply { baseColor = Color4(0.18f, 0.48f, 0.96f, 1.0f) },
                Transform(Pose(portalCenter + Vector3(0.06f, 0.02f, -0.22f))),
                Scale(Vector3(0.20f)),
            ),
        )
        portalEntities += sphere
        portalScales[sphere.id] = Vector3(0.20f)

        // Three thin axis boxes. They are spatial, so each eye gets a distinct view.
        portalEntities += axisBox(
            center = portalCenter + Vector3(0.02f, -0.17f, 0f),
            halfExtents = Vector3(0.30f, 0.006f, 0.006f),
            color = Color4(0.95f, 0.18f, 0.18f, 1f),
        )
        portalEntities += axisBox(
            center = portalCenter + Vector3(-0.26f, 0.10f, 0f),
            halfExtents = Vector3(0.006f, 0.28f, 0.006f),
            color = Color4(0.20f, 0.78f, 0.28f, 1f),
        )
        portalEntities += axisBox(
            center = portalCenter + Vector3(-0.26f, -0.17f, -0.20f),
            halfExtents = Vector3(0.006f, 0.006f, 0.20f),
            color = Color4(0.18f, 0.38f, 1.0f, 1f),
        )
    }

    private fun axisBox(center: Vector3, halfExtents: Vector3, color: Color4): Entity {
        val entity = Entity.create(
            listOf(
                Box(-halfExtents, halfExtents),
                Mesh("mesh://box".toUri()),
                Material().apply { baseColor = color },
                Transform(Pose(center)),
                Scale(Vector3(1f)),
            ),
        )
        portalScales[entity.id] = Vector3(1f)
        return entity
    }

    private fun setPortalVisible(visible: Boolean) {
        portalEntities.forEach { entity ->
            val original = portalScales[entity.id] ?: Vector3(1f)
            entity.setComponent(Scale(if (visible) original else Vector3(0f)))
        }
    }
}
