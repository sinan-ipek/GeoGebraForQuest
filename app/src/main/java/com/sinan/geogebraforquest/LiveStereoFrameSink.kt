package com.sinan.geogebraforquest

import android.content.res.Resources
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.Rect
import android.util.Base64
import android.util.Log
import android.view.Surface
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * v0.9.23 live stereo sink.
 *
 * The proven v0.9.22 live eye routing and transparent idle clear are preserved.
 * Only the startup splash eye assignment is swapped: the previous right-eye
 * splash is routed to the left half and the previous left-eye splash to the
 * right half. Live GeoGebra eye routing remains unchanged.
 */
object LiveStereoFrameSink {
    private const val TAG = "GeoGebraForQuest"
    private const val DATA_URL_PREFIX = "base64,"
    private const val STREAM_IDLE_TIMEOUT_MS = 350L

    private data class EyeFrame(
        val leftDataUrl: String,
        val rightDataUrl: String,
    )

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-LiveStereoFrameSink").apply { isDaemon = true }
    }

    private val watchdog = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "GGQ-StereoIdleWatchdog").apply { isDaemon = true }
    }

    private val latestFrame = AtomicReference<EyeFrame?>(null)
    private val draining = AtomicBoolean(false)
    private val renderedFrameCount = AtomicLong(0L)
    private val frameSerial = AtomicLong(0L)
    private val surfaceGeneration = AtomicLong(0L)

    private val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
        isDither = false
    }

    @Volatile
    private var surface: Surface? = null

    @Volatile
    private var enabled = true

    @Volatile
    private var hasRenderedLiveFrame = false

    fun attachSurface(newSurface: Surface, resources: Resources) {
        surface = newSurface
        latestFrame.set(null)
        frameSerial.set(0L)
        hasRenderedLiveFrame = false
        val generation = surfaceGeneration.incrementAndGet()

        executor.execute {
            if (surfaceGeneration.get() == generation && surface === newSurface) {
                renderStartupSplash(resources, newSurface)
            }
        }

        Log.i(TAG, "v0.9.23 renderer-eye sink attached with swapped stereo startup splash")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surfaceGeneration.incrementAndGet()
            surface = null
            latestFrame.set(null)
            frameSerial.set(0L)
            hasRenderedLiveFrame = false
            Log.i(TAG, "v0.9.23 renderer-eye sink detached")
        }
    }

    fun setEnabled(value: Boolean) {
        enabled = value
        if (!value) {
            latestFrame.set(null)
            val generation = surfaceGeneration.get()
            executor.execute {
                if (surfaceGeneration.get() == generation) {
                    clearSurfaceToTransparent()
                    hasRenderedLiveFrame = false
                }
            }
        }
        Log.i(TAG, "v0.9.23 renderer-eye sink enabled=$value")
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

        val generation = surfaceGeneration.get()
        val serial = frameSerial.incrementAndGet()
        scheduleIdleClear(generation, serial)
        scheduleDrain()
    }

    private fun scheduleIdleClear(generation: Long, serial: Long) {
        watchdog.schedule(
            {
                if (
                    enabled &&
                    surfaceGeneration.get() == generation &&
                    frameSerial.get() == serial &&
                    hasRenderedLiveFrame
                ) {
                    latestFrame.set(null)
                    executor.execute {
                        if (
                            enabled &&
                            surfaceGeneration.get() == generation &&
                            frameSerial.get() == serial &&
                            hasRenderedLiveFrame
                        ) {
                            clearSurfaceToTransparent()
                            hasRenderedLiveFrame = false
                            Log.i(TAG, "v0.9.23 stereo stream idle; panel cleared to transparent")
                        }
                    }
                }
            },
            STREAM_IDLE_TIMEOUT_MS,
            TimeUnit.MILLISECONDS,
        )
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
            Log.w(TAG, "v0.9.23 invalid eye-frame Base64", error)
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

    private fun fitCenter(bitmap: Bitmap, bounds: Rect): Rect {
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

    private fun renderStartupSplash(resources: Resources, expectedSurface: Surface) {
        if (surface !== expectedSurface || !expectedSurface.isValid) return

        val leftBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_right) ?: return
        val rightBitmap = BitmapFactory.decodeResource(resources, R.drawable.stereo_splash_left)
        if (rightBitmap == null) {
            leftBitmap.recycle()
            return
        }

        try {
            renderPair(
                leftBitmap = leftBitmap,
                rightBitmap = rightBitmap,
                clearColor = null,
                markAsLive = false,
            )
            Log.i(TAG, "v0.9.23 stereo startup splash rendered with swapped eyes")
        } finally {
            leftBitmap.recycle()
            rightBitmap.recycle()
        }
    }

    private fun renderEyes(leftBitmap: Bitmap, rightBitmap: Bitmap) {
        renderPair(
            leftBitmap = leftBitmap,
            rightBitmap = rightBitmap,
            clearColor = Color.BLACK,
            markAsLive = true,
        )
    }

    private fun renderPair(
        leftBitmap: Bitmap,
        rightBitmap: Bitmap,
        clearColor: Int?,
        markAsLive: Boolean,
    ) {
        if (!enabled && markAsLive) return

        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            if (clearColor == null) {
                canvas.drawColor(Color.TRANSPARENT, PorterDuff.Mode.CLEAR)
            } else {
                canvas.drawColor(clearColor)
            }

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

            if (markAsLive) {
                hasRenderedLiveFrame = true
                val count = renderedFrameCount.incrementAndGet()
                if (count == 1L || count % 60L == 0L) {
                    Log.i(
                        TAG,
                        "v0.9.23 explicit-eye frame #$count " +
                            "left=${leftBitmap.width}x${leftBitmap.height}->$leftDestination " +
                            "right=${rightBitmap.width}x${rightBitmap.height}->$rightDestination " +
                            "surface=${canvas.width}x${canvas.height}",
                    )
                }
            }
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.23 eye composition failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.23 stereo surface post failed", error)
                }
            }
        }
    }

    private fun clearSurfaceToTransparent() {
        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            canvas.drawColor(Color.TRANSPARENT, PorterDuff.Mode.CLEAR)
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.23 transparent clear failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.23 transparent surface post failed", error)
                }
            }
        }
    }
}
