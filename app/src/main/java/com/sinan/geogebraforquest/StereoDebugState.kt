package com.sinan.geogebraforquest

import android.os.SystemClock
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

/** Compact diagnostics for the Quest stereo transport and portal composition. */
object StereoDebugState {
    private val portalRectCount = AtomicInteger(0)
    private val frameReceivedCount = AtomicInteger(0)
    private val frameAcceptedCount = AtomicInteger(0)
    private val framePresentedCount = AtomicInteger(0)
    private val frameFinishedCount = AtomicInteger(0)
    private val frameDroppedBusyCount = AtomicInteger(0)
    private val frameRejectedCount = AtomicInteger(0)

    @Volatile private var stereoEnabled = false
    @Volatile private var surfaceAttached = false
    @Volatile private var portalEntityReady = false
    @Volatile private var portalVisible = false
    @Volatile private var portalPresentationAllowed = true
    @Volatile private var portalNonHittable = false
    @Volatile private var lastEyeWidth = 0
    @Volatile private var lastEyeHeight = 0
    @Volatile private var lastPresentedAtMs = 0L

    fun reset() {
        portalRectCount.set(0)
        frameReceivedCount.set(0)
        frameAcceptedCount.set(0)
        framePresentedCount.set(0)
        frameFinishedCount.set(0)
        frameDroppedBusyCount.set(0)
        frameRejectedCount.set(0)
        stereoEnabled = false
        surfaceAttached = false
        portalEntityReady = false
        portalVisible = false
        portalPresentationAllowed = true
        portalNonHittable = false
        lastEyeWidth = 0
        lastEyeHeight = 0
        lastPresentedAtMs = 0L
    }

    fun onStereoChanged(enabled: Boolean) {
        stereoEnabled = enabled
        if (!enabled) portalVisible = false
    }

    fun onSurfaceAttached() {
        surfaceAttached = true
    }

    fun onPortalEntityReady() {
        portalEntityReady = true
    }

    fun onPortalPresentationAllowed(allowed: Boolean) {
        portalPresentationAllowed = allowed
        if (!allowed) portalVisible = false
    }

    fun onPortalNonHittable() {
        portalNonHittable = true
    }

    fun onPortalRect() {
        portalRectCount.incrementAndGet()
    }

    fun onFrameReceived(eyeWidth: Int, eyeHeight: Int) {
        frameReceivedCount.incrementAndGet()
        lastEyeWidth = eyeWidth
        lastEyeHeight = eyeHeight
    }

    fun onFrameAccepted() {
        frameAcceptedCount.incrementAndGet()
    }

    fun onFramePresented() {
        framePresentedCount.incrementAndGet()
        lastPresentedAtMs = SystemClock.elapsedRealtime()
    }

    fun onFrameFinished() {
        frameFinishedCount.incrementAndGet()
    }

    fun onFrameDroppedBusy() {
        frameDroppedBusyCount.incrementAndGet()
    }

    fun onFrameRejected() {
        frameRejectedCount.incrementAndGet()
    }

    fun onPortalVisible() {
        portalVisible = true
    }

    fun toJson(): String {
        return JSONObject()
            .put("stereoEnabled", stereoEnabled)
            .put("surfaceAttached", surfaceAttached)
            .put("portalEntityReady", portalEntityReady)
            .put("portalVisible", portalVisible)
            .put("portalPresentationAllowed", portalPresentationAllowed)
            .put("portalNonHittable", portalNonHittable)
            .put("portalRects", portalRectCount.get())
            .put("framesReceived", frameReceivedCount.get())
            .put("framesAccepted", frameAcceptedCount.get())
            .put("framesPresented", framePresentedCount.get())
            .put("framesFinished", frameFinishedCount.get())
            .put("framesDroppedBusy", frameDroppedBusyCount.get())
            .put("framesRejected", frameRejectedCount.get())
            .put("lastEyeWidth", lastEyeWidth)
            .put("lastEyeHeight", lastEyeHeight)
            .put("lastPresentedAtMs", lastPresentedAtMs)
            .toString()
    }
}
