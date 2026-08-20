package com.sinan.geogebraforquest

/**
 * In-process bridge between the GeoGebra WebView panel and the Spatial SDK host.
 *
 * v0.6.0 sends a decoded SBS image of only the 3D viewport plus its rectangle.
 * Android captures the ordinary full WebView once, composites the left 3D half
 * into one complete panel image and the right 3D half into another, then sends
 * the resulting full-panel SBS frame to a StereoMode.LeftRight media surface.
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
