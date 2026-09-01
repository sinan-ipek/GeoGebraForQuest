package com.sinan.geogebraforquest

/**
 * Small in-process bridge for data that belongs to the single GeoGebra panel.
 *
 * The activity consumes the live 3D rectangle to position the rear proof/stereo panel. Exp3d also
 * lets the white rear backplate consume the same rectangle so it can draw white only outside the
 * 3D hole, without covering the proof panel itself.
 */
object SpatialBridgeBus {
    @Volatile
    var onStereoLayout: ((String) -> Unit)? = null

    @Volatile
    var onBackplateLayout: ((String) -> Unit)? = null

    @Volatile
    var onPanelReady: (() -> Unit)? = null

    fun stereoLayout(json: String) {
        onStereoLayout?.invoke(json)
        onBackplateLayout?.invoke(json)
    }

    fun panelReady() {
        onPanelReady?.invoke()
    }

    fun clear() {
        onStereoLayout = null
        onBackplateLayout = null
        onPanelReady = null
    }
}
