package com.sinan.geogebraforquest

/**
 * Shared state for the Quest depth-pointer presentation.
 *
 * The actual GeoGebra interaction ray still hits the transparent A panel so input/picking is
 * unchanged. While the pointer is inside the live 3D hole, we hide Meta's flat panel laser and
 * rely on GeoGebra's own stereo 3D cursor/highlight, which is rendered at the picked depth.
 */
object DepthPointerState {
    @Volatile
    var active: Boolean = false
        private set

    fun setActive(value: Boolean) {
        active = value
    }

    fun reset() {
        active = false
    }
}
