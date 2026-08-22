package com.sinan.geogebraforquest

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.util.Base64
import android.util.Log
import android.view.Surface
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.atomic.AtomicLong

/**
 * v0.9.15 live GeoGebra SBS sink used by the controlled A/B stereo diagnostic.
 *
 * The same registered VideoSurface is shared with the v0.9.11 TEST probe. In
 * GEOGEBRA mode the complete L|R bitmap is stretched directly to the Surface's
 * full pixel bounds. There is deliberately no fit-center, letterboxing, crop,
 * panel resize or per-eye split here. Meta's StereoMode.LeftRight remains the
 * only operation that selects the left and right halves for the two eyes.
 */
object LiveStereoFrameSink {
    private const val TAG = "GeoGebraForQuest"
    private const val DATA_URL_PREFIX = "base64,"

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-LiveStereoFrameSink").apply { isDaemon = true }
    }
    private val latestFrame = AtomicReference<String?>(null)
    private val draining = AtomicBoolean(false)
    private val renderedFrameCount = AtomicLong(0L)

    private val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
        isDither = false
    }

    @Volatile
    private var surface: Surface? = null

    @Volatile
    private var enabled = false

    fun attachSurface(newSurface: Surface) {
        surface = newSurface
        Log.i(TAG, "v0.9.15 live stereo sink attached")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surface = null
            latestFrame.set(null)
            Log.i(TAG, "v0.9.15 live stereo sink detached")
        }
    }

    fun setEnabled(value: Boolean) {
        enabled = value
        if (!value) {
            latestFrame.set(null)
        }
        Log.i(TAG, "v0.9.15 live stereo sink enabled=$value")
    }

    fun submitDataUrl(dataUrl: String) {
        if (!enabled) return
        if (!dataUrl.startsWith("data:image/")) return
        if (surface?.isValid != true) return

        latestFrame.set(dataUrl)
        scheduleDrain()
    }

    private fun scheduleDrain() {
        if (!draining.compareAndSet(false, true)) return

        executor.execute {
            try {
                while (enabled) {
                    val frame = latestFrame.getAndSet(null) ?: break
                    decodeAndRender(frame)
                }
            } finally {
                draining.set(false)
                if (enabled && latestFrame.get() != null) {
                    scheduleDrain()
                }
            }
        }
    }

    private fun decodeAndRender(dataUrl: String) {
        if (!enabled) return

        val marker = dataUrl.indexOf(DATA_URL_PREFIX)
        if (marker < 0) return

        val encoded = dataUrl.substring(marker + DATA_URL_PREFIX.length)
        val bytes = try {
            Base64.decode(encoded, Base64.DEFAULT)
        } catch (error: IllegalArgumentException) {
            Log.w(TAG, "v0.9.15 invalid stereo frame Base64", error)
            return
        }

        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return
        try {
            renderBitmap(bitmap)
        } finally {
            bitmap.recycle()
        }
    }

    private fun renderBitmap(bitmap: Bitmap) {
        if (!enabled) return

        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            canvas.drawColor(Color.BLACK)

            val source = Rect(0, 0, bitmap.width, bitmap.height)
            val destination = Rect(0, 0, canvas.width, canvas.height)
            canvas.drawBitmap(bitmap, source, destination, paint)

            val count = renderedFrameCount.incrementAndGet()
            if (count == 1L || count % 30L == 0L) {
                Log.i(
                    TAG,
                    "v0.9.15 live SBS frame #$count source=${bitmap.width}x${bitmap.height} " +
                        "surface=${canvas.width}x${canvas.height}",
                )
            }
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.15 live stereo surface render failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.15 live stereo surface post failed", error)
                }
            }
        }
    }
}
