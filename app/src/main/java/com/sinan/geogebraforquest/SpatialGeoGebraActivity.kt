package com.sinan.geogebraforquest

import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.composePanel
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.LayerConfig
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.vr.VRFeature

/**
 * Stable immersive transition host.
 *
 * v0.2.2 intentionally returns to the proven v0.1.2 transition first.
 * The panel is opaque and contains ordinary GeoGebra. Stereo portal work will
 * be reintroduced only after the launcher is confirmed stable again on Quest.
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

        Entity.create(
            listOf(
                Panel(R.id.geogebra_panel),
                Transform(Pose(Vector3(0f, 1.30f, 0f))),
            ),
        )
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            PanelRegistration(R.id.geogebra_panel) {
                config {
                    themeResourceId = R.style.PanelAppTheme
                    layoutWidthInDp = 1080f
                    layoutHeightInDp = 720f
                    layerConfig = LayerConfig()
                    enableTransparent = false
                    includeGlass = false
                }
                composePanel {
                    setContent {
                        GeoGebraWebPanel(
                            spatialMode = true,
                            onPortalChanged = { /* stereo portal returns after startup stability is proven */ },
                        )
                    }
                }
            },
        )
    }
}
