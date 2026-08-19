package com.sinan.geogebraforquest

/**
 * In-process bridge between the GeoGebra WebView panel and the Spatial SDK host.
 *
 * v0.5.0 no longer mirrors GeoGebra objects as native meshes. GeoGebra renders
 * both stereo eye passes itself; JavaScript packs those two eye images into one
 * side-by-side frame and sends it through this bridge to a StereoMode.LeftRight
 * media surface.
 */
object SpatialBridgeBus {
    @Volatile
    var onStereoChanged: ((Boolean) -> Unit)? = null

    @Volatile
    var onPortalRect: ((String) -> Unit)? = null

    @Volatile
    var onStereoFrame: ((String, Int, Int) -> Unit)? = null

    @Volatile
    var onPanelReady: (() -> Unit)? = null

    fun stereoChanged(enabled: Boolean) {
        onStereoChanged?.invoke(enabled)
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
        onPortalRect = null
        onStereoFrame = null
        onPanelReady = null
    }
}
