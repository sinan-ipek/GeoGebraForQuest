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
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * v0.9.18 live stereo sink.
 *
 * GeoGebra's QuestStereoRenderer now snapshots the completed LEFT_EYE and
 * RIGHT_EYE render passes into two dedicated browser canvases. JavaScript sends
 * those two explicit eye images here; no SBS canvas splitting or quarter
 * guessing exists in this path.
 *
 * The two eye images are drawn into the left/right halves of the registered
 * VideoSurface. Each image is fit-centred inside its own eye rectangle so its
 * original aspect ratio is preserved. Meta StereoMode.LeftRight then performs
 * the final physical routing to the headset eyes.
 */
object LiveStereoFrameSink {
    private const val TAG = "GeoGebraForQuest"
    private const val DATA_URL_PREFIX = "base64,"

    private data class EyeFrame(
        val leftDataUrl: String,
        val rightDataUrl: String,
    )

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-LiveStereoFrameSink").apply { isDaemon = true }
    }
    private val latestFrame = AtomicReference<EyeFrame?>(null)
    private val draining = AtomicBoolean(false)
    private val renderedFrameCount = AtomicLong(0L)

    private val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
        isDither = false
    }

    @Volatile
    private var surface: Surface? = null

    @Volatile
    private var enabled = true

    fun attachSurface(newSurface: Surface) {
        surface = newSurface
        Log.i(TAG, "v0.9.18 renderer-eye sink attached")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surface = null
            latestFrame.set(null)
            Log.i(TAG, "v0.9.18 renderer-eye sink detached")
        }
    }

    fun setEnabled(value: Boolean) {
        enabled = value
        if (!value) {
            latestFrame.set(null)
        }
        Log.i(TAG, "v0.9.18 renderer-eye sink enabled=$value")
    }

    fun submitEyeDataUrls(leftDataUrl: String, rightDataUrl: String) {
        if (!enabled) return
        if (!leftDataUrl.startsWith("data:image/")) return
        if (!rightDataUrl.startsWith("data:image/")) return
        if (surface?.isValid != true) return

        latestFrame.set(
            EyeFrame(
                leftDataUrl = leftDataUrl,
                rightDataUrl = rightDataUrl,
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
            Log.w(TAG, "v0.9.18 invalid eye-frame Base64", error)
            return null
        }

        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }

    private fun decodeAndRender(frame: EyeFrame) {
        if (!enabled) return

        val leftBitmap = decodeDataUrl(frame.leftDataUrl) ?: return
        val rightBitmap = decodeDataUrl(frame.rightDataUrl)
        if (rightBitmap == null) {
            leftBitmap.recycle()
            return
        }

        try {
            renderEyes(leftBitmap, rightBitmap)
        } finally {
            leftBitmap.recycle()
            rightBitmap.recycle()
        }
    }

    private fun fitCenter(
        bitmap: Bitmap,
        bounds: Rect,
    ): Rect {
        if (bitmap.width <= 0 || bitmap.height <= 0 || bounds.width() <= 0 || bounds.height() <= 0) {
            return Rect(bounds)
        }

        val scale = min(
            bounds.width().toFloat() / bitmap.width.toFloat(),
            bounds.height().toFloat() / bitmap.height.toFloat(),
        )
        val width = (bitmap.width * scale).roundToInt().coerceAtLeast(1)
        val height = (bitmap.height * scale).roundToInt().coerceAtLeast(1)
        val left = bounds.left + (bounds.width() - width) / 2
        val top = bounds.top + (bounds.height() - height) / 2
        return Rect(left, top, left + width, top + height)
    }

    private fun renderEyes(leftBitmap: Bitmap, rightBitmap: Bitmap) {
        if (!enabled) return

        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            canvas.drawColor(Color.BLACK)

            val halfWidth = canvas.width / 2
            if (halfWidth <= 0 || canvas.height <= 0) return

            val leftBounds = Rect(0, 0, halfWidth, canvas.height)
            val rightBounds = Rect(halfWidth, 0, canvas.width, canvas.height)
            val leftDestination = fitCenter(leftBitmap, leftBounds)
            val rightDestination = fitCenter(rightBitmap, rightBounds)

            canvas.drawBitmap(
                leftBitmap,
                Rect(0, 0, leftBitmap.width, leftBitmap.height),
                leftDestination,
                paint,
            )
            canvas.drawBitmap(
                rightBitmap,
                Rect(0, 0, rightBitmap.width, rightBitmap.height),
                rightDestination,
                paint,
            )

            val count = renderedFrameCount.incrementAndGet()
            if (count == 1L || count % 30L == 0L) {
                Log.i(
                    TAG,
                    "v0.9.18 explicit-eye frame #$count " +
                        "left=${leftBitmap.width}x${leftBitmap.height}->$leftDestination " +
                        "right=${rightBitmap.width}x${rightBitmap.height}->$rightDestination " +
                        "surface=${canvas.width}x${canvas.height}",
                )
            }
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.18 explicit-eye composition failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.18 stereo surface post failed", error)
                }
            }
        }
    }
}
