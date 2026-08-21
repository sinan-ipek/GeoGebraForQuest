package com.sinan.geogebraforquest

/**
 * In-process bridge between the GeoGebra WebView and the Spatial SDK host.
 *
 * Stereo capture state and portal presentation state are intentionally separate:
 * the eye-pair renderer may keep running while the visual portal is hidden under
 * a GeoGebra dialog/menu, so reopening the workspace does not have to restart the
 * Glasses renderer or lose the already-working stereo pipeline.
 */
object SpatialBridgeBus {
    @Volatile
    var onStereoChanged: ((Boolean) -> Unit)? = null

    @Volatile
    var onPortalVisibilityChanged: ((Boolean) -> Unit)? = null

    @Volatile
    var onPortalRect: ((String) -> Unit)? = null

    @Volatile
    var onStereoFrame: ((String, Int, Int) -> Unit)? = null

    @Volatile
    var onPanelReady: (() -> Unit)? = null

    fun stereoChanged(enabled: Boolean) {
        onStereoChanged?.invoke(enabled)
    }

    fun portalVisibilityChanged(visible: Boolean) {
        onPortalVisibilityChanged?.invoke(visible)
    }

    fun portalRect(json: String) {
        onPortalRect?.invoke(json)
    }

    fun stereoFrame(dataUrl: String, eyeWidth: Int, eyeHeight: Int) {
        onStereoFrame?.invoke(dataUrl, eyeWidth, eyeHeight)
    }

    fun panelReady() {
        onPanelReady?.invoke()
    }

    fun clear() {
        onStereoChanged = null
        onPortalVisibilityChanged = null
        onPortalRect = null
        onStereoFrame = null
        onPanelReady = null
    }
}
