package com.sinan.geogebraforquest

/**
 * Lightweight in-process event bridge between the Activity-backed GeoGebra panel
 * and the Spatial SDK host.
 *
 * The GeoGebra WebView lives in PancakeActivity because that exact Android Activity
 * path is already proven to render correctly on Quest. SpatialGeoGebraActivity embeds
 * that Activity as a Spatial SDK panel and listens here for stereo/scene updates.
 */
object SpatialBridgeBus {
    @Volatile
    var onStereoChanged: ((Boolean) -> Unit)? = null

    @Volatile
    var onPortalRect: ((String) -> Unit)? = null

    @Volatile
    var onSceneChanged: ((String) -> Unit)? = null

    @Volatile
    var onPanelReady: (() -> Unit)? = null

    fun stereoChanged(enabled: Boolean) {
        onStereoChanged?.invoke(enabled)
    }

    fun portalRect(json: String) {
        onPortalRect?.invoke(json)
    }

    fun sceneChanged(json: String) {
        onSceneChanged?.invoke(json)
    }

    fun panelReady() {
        onPanelReady?.invoke()
    }

    fun clear() {
        onStereoChanged = null
        onPortalRect = null
        onSceneChanged = null
        onPanelReady = null
    }
}
