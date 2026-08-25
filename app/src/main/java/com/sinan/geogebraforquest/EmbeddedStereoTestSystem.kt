package com.sinan.geogebraforquest

import com.meta.spatial.core.SystemBase

/**
 * Applies WebView-reported 3D-view geometry on the Spatial thread.
 * This exists only on the experimental embedded-stereo branch.
 */
class EmbeddedStereoTestSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {
    override fun execute() {
        activity.applyPendingEmbeddedLayout()
    }
}
