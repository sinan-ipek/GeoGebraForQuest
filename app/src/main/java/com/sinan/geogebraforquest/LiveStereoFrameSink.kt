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
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * v0.9.17 GeoGebra WebGL quarter-pair diagnostic.
 *
 * v0.9.16 proved that a nominal half of the WebGL backing store still contains
 * two visible views on the headset. JavaScript therefore sends four equal
 * horizontal quarters. This sink can map quarter 1+2 or quarter 1+3 into the
 * exact same verified 800x400 L|R VideoSurface.
 */
object LiveStereoFrameSink {
    private const val TAG = "GeoGebraForQuest"
    private const val DATA_URL_PREFIX = "base64,"

    enum class PairMode {
        PAIR_12,
        PAIR_13,
    }

    private data class QuarterFrame(
        val q1DataUrl: String,
        val q2DataUrl: String,
        val q3DataUrl: String,
        val q4DataUrl: String,
    )

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-LiveStereoFrameSink").apply { isDaemon = true }
    }
    private val latestFrame = AtomicReference<QuarterFrame?>(null)
    private val draining = AtomicBoolean(false)
    private val renderedFrameCount = AtomicLong(0L)

    private val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
        isDither = false
    }

    @Volatile
    private var surface: Surface? = null

    @Volatile
    private var enabled = false

    @Volatile
    private var pairMode = PairMode.PAIR_12

    fun attachSurface(newSurface: Surface) {
        surface = newSurface
        Log.i(TAG, "v0.9.17 quarter sink attached")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surface = null
            latestFrame.set(null)
            Log.i(TAG, "v0.9.17 quarter sink detached")
        }
    }

    fun setEnabled(value: Boolean) {
        enabled = value
        if (!value) {
            latestFrame.set(null)
        }
        Log.i(TAG, "v0.9.17 quarter sink enabled=$value")
    }

    fun setPairMode(value: PairMode) {
        pairMode = value
        Log.i(TAG, "v0.9.17 quarter pair mode=$value")
    }

    fun submitQuarterDataUrls(
        q1DataUrl: String,
        q2DataUrl: String,
        q3DataUrl: String,
        q4DataUrl: String,
    ) {
        if (!enabled) return
        if (!q1DataUrl.startsWith("data:image/")) return
        if (!q2DataUrl.startsWith("data:image/")) return
        if (!q3DataUrl.startsWith("data:image/")) return
        if (!q4DataUrl.startsWith("data:image/")) return
        if (surface?.isValid != true) return

        latestFrame.set(
            QuarterFrame(
                q1DataUrl = q1DataUrl,
                q2DataUrl = q2DataUrl,
                q3DataUrl = q3DataUrl,
                q4DataUrl = q4DataUrl,
            ),
        )
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

    private fun decodeDataUrl(dataUrl: String): Bitmap? {
        val marker = dataUrl.indexOf(DATA_URL_PREFIX)
        if (marker < 0) return null

        val encoded = dataUrl.substring(marker + DATA_URL_PREFIX.length)
        val bytes = try {
            Base64.decode(encoded, Base64.DEFAULT)
        } catch (error: IllegalArgumentException) {
            Log.w(TAG, "v0.9.17 invalid quarter Base64", error)
            return null
        }

        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }

    private fun decodeAndRender(frame: QuarterFrame) {
        if (!enabled) return

        val mode = pairMode
        val leftDataUrl = frame.q1DataUrl
        val rightDataUrl = when (mode) {
            PairMode.PAIR_12 -> frame.q2DataUrl
            PairMode.PAIR_13 -> frame.q3DataUrl
        }

        val leftBitmap = decodeDataUrl(leftDataUrl) ?: return
        val rightBitmap = decodeDataUrl(rightDataUrl)
        if (rightBitmap == null) {
            leftBitmap.recycle()
            return
        }

        try {
            renderPair(leftBitmap, rightBitmap, mode)
        } finally {
            leftBitmap.recycle()
            rightBitmap.recycle()
        }
    }

    private fun renderPair(
        leftBitmap: Bitmap,
        rightBitmap: Bitmap,
        mode: PairMode,
    ) {
        if (!enabled) return

        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            canvas.drawColor(Color.BLACK)

            val halfWidth = canvas.width / 2
            if (halfWidth <= 0 || canvas.height <= 0) return

            val leftSource = Rect(0, 0, leftBitmap.width, leftBitmap.height)
            val rightSource = Rect(0, 0, rightBitmap.width, rightBitmap.height)
            val leftDestination = Rect(0, 0, halfWidth, canvas.height)
            val rightDestination = Rect(halfWidth, 0, canvas.width, canvas.height)

            canvas.drawBitmap(leftBitmap, leftSource, leftDestination, paint)
            canvas.drawBitmap(rightBitmap, rightSource, rightDestination, paint)

            val count = renderedFrameCount.incrementAndGet()
            if (count == 1L || count % 30L == 0L) {
                Log.i(
                    TAG,
                    "v0.9.17 quarter frame #$count mode=$mode " +
                        "left=${leftBitmap.width}x${leftBitmap.height} " +
                        "right=${rightBitmap.width}x${rightBitmap.height} " +
                        "surface=${canvas.width}x${canvas.height}",
                )
            }
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.17 quarter composition failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.17 stereo surface post failed", error)
                }
            }
        }
    }
}
