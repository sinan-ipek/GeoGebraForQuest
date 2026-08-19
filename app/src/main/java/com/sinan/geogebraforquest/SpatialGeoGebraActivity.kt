package com.sinan.geogebraforquest

import androidx.compose.ui.platform.ComposeView
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.vr.VRFeature

/**
 * Safe immersive vertical slice.
 *
 * v0.1.1 intentionally starts with only the GeoGebra panel in immersive mode.
 * The previous runtime-created sphere/axis meshes have been removed temporarily
 * so the first thing we verify on Quest is a stable 2D -> immersive transition.
 * Once this works reliably, native stereoscopic geometry will be added back.
 */
class SpatialGeoGebraActivity : AppSystemActivity() {

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(
            VRFeature(this),
            ComposeFeature(),
        )
    }

    override fun onSceneReady() {
        super.onSceneReady()

        scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
        scene.setViewOrigin(0f, 0f, 2.0f, 180f)

        // One known-safe spatial panel in front of the user.
        Entity.create(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.35f, 0f))),
            ),
        )
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
                                onPortalChanged = { /* v0.1.1 safe mode: no portal yet */ },
                            )
                        }
                    }
                },
                settingsCreator = {
                    UIPanelSettings(
                        shape = QuadShapeOptions(width = 1.28f, height = 0.80f),
                        style = PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                        display = DpPerMeterDisplayOptions(),
                    )
                },
            ),
        )
    }
}
