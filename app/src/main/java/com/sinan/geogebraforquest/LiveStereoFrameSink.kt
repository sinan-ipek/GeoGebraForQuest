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
 * v0.9.16 live GeoGebra stereo sink.
 *
 * The JavaScript side no longer sends one complete SBS JPEG. It extracts the
 * WebGL renderer's left and right horizontal eye viewports independently and
 * sends two JPEGs. Native code decodes those independent eye frames and paints
 * exactly one L|R pair into the same VideoSurface that already passed the
 * v0.9.11/v0.9.15 TEST probe.
 *
 * This removes the ambiguous whole-SBS copy step that produced a nested SBS
 * image in v0.9.15. Meta StereoMode.LeftRight remains the final per-eye router.
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
    private var enabled = false

    fun attachSurface(newSurface: Surface) {
        surface = newSurface
        Log.i(TAG, "v0.9.16 live stereo sink attached")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surface = null
            latestFrame.set(null)
            Log.i(TAG, "v0.9.16 live stereo sink detached")
        }
    }

    fun setEnabled(value: Boolean) {
        enabled = value
        if (!value) {
            latestFrame.set(null)
        }
        Log.i(TAG, "v0.9.16 live stereo sink enabled=$value")
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
            Log.w(TAG, "v0.9.16 invalid eye-frame Base64", error)
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
                    "v0.9.16 eye frame #$count " +
                        "left=${leftBitmap.width}x${leftBitmap.height} " +
                        "right=${rightBitmap.width}x${rightBitmap.height} " +
                        "surface=${canvas.width}x${canvas.height} half=$halfWidth",
                )
            }
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.16 live eye composition failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.16 live stereo surface post failed", error)
                }
            }
        }
    }
}
