package com.sinan.geogebraforquest

import com.meta.spatial.core.SystemBase

/**
 * Applies WebView-reported 3D-view geometry on the Spatial thread.
 * Kept separate from the stable controller system so the embedded experiment is isolated.
 */
class EmbeddedStereoTestSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {
    override fun execute() {
        activity.applyPendingEmbeddedLayout()
    }
}
