package com.sinan.geogebraforquest

/**
 * Small in-process bridge for data that belongs to the single GeoGebra panel.
 *
 * v0.9.0 deliberately has no stereo-frame transport. GeoGebra renders the SBS
 * pair directly on the GPU; JavaScript reports only the layout rectangle of the
 * 3D view and temporary UI occlusions so the Spatial material can sample it.
 */
object SpatialBridgeBus {
    @Volatile
    var onStereoLayout: ((String) -> Unit)? = null

    @Volatile
    var onPanelReady: (() -> Unit)? = null

    fun stereoLayout(json: String) {
        onStereoLayout?.invoke(json)
    }

    fun panelReady() {
        onPanelReady?.invoke()
    }

    fun clear() {
        onStereoLayout = null
        onPanelReady = null
    }
}
