package com.sinan.geogebraforquest

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.util.Base64
import android.util.Log
import android.view.Surface
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.min

/**
 * Receives compressed SBS frames from the GeoGebra WebView and paints the newest
 * available frame directly into the registered Quest VideoSurface panel.
 *
 * The JavaScript side sends the complete 2x-wide L|R canvas. This class never
 * splits the image itself; Meta's MediaPanelRenderOptions(StereoMode.LeftRight)
 * performs the final per-eye selection in the Quest compositor.
 *
 * Back-pressure is intentional: if decoding/rendering is slower than capture,
 * old frames are discarded and only the newest frame is retained. That keeps
 * interaction latency bounded instead of building a queue of stale frames.
 */
object LiveStereoFrameSink {
    private const val TAG = "GeoGebraForQuest"
    private const val DATA_URL_PREFIX = "base64,"

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-LiveStereoFrameSink").apply { isDaemon = true }
    }
    private val latestFrame = AtomicReference<String?>(null)
    private val draining = AtomicBoolean(false)

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
        isDither = true
    }

    @Volatile
    private var surface: Surface? = null

    fun attachSurface(newSurface: Surface) {
        surface = newSurface
        Log.i(TAG, "v0.9.13 live stereo VideoSurface attached")
    }

    fun detachSurface(expectedSurface: Surface? = null) {
        val current = surface
        if (expectedSurface == null || current === expectedSurface) {
            surface = null
            latestFrame.set(null)
            Log.i(TAG, "v0.9.13 live stereo VideoSurface detached")
        }
    }

    fun submitDataUrl(dataUrl: String) {
        if (!dataUrl.startsWith("data:image/")) return
        if (surface?.isValid != true) return

        latestFrame.set(dataUrl)
        scheduleDrain()
    }

    private fun scheduleDrain() {
        if (!draining.compareAndSet(false, true)) return

        executor.execute {
            try {
                while (true) {
                    val frame = latestFrame.getAndSet(null) ?: break
                    decodeAndRender(frame)
                }
            } finally {
                draining.set(false)
                if (latestFrame.get() != null) {
                    scheduleDrain()
                }
            }
        }
    }

    private fun decodeAndRender(dataUrl: String) {
        val marker = dataUrl.indexOf(DATA_URL_PREFIX)
        if (marker < 0) return

        val encoded = dataUrl.substring(marker + DATA_URL_PREFIX.length)
        val bytes = try {
            Base64.decode(encoded, Base64.DEFAULT)
        } catch (error: IllegalArgumentException) {
            Log.w(TAG, "v0.9.13 invalid stereo frame Base64", error)
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
        val targetSurface = surface ?: return
        if (!targetSurface.isValid) return

        var canvas: Canvas? = null
        try {
            canvas = targetSurface.lockCanvas(null)
            canvas.drawColor(Color.BLACK)

            val source = Rect(0, 0, bitmap.width, bitmap.height)
            val destination = fitCenter(
                sourceWidth = bitmap.width.toFloat(),
                sourceHeight = bitmap.height.toFloat(),
                targetWidth = canvas.width.toFloat(),
                targetHeight = canvas.height.toFloat(),
            )
            canvas.drawBitmap(bitmap, source, destination, paint)
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.13 live stereo surface render failed", error)
        } finally {
            if (canvas != null) {
                try {
                    targetSurface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.13 live stereo surface post failed", error)
                }
            }
        }
    }

    private fun fitCenter(
        sourceWidth: Float,
        sourceHeight: Float,
        targetWidth: Float,
        targetHeight: Float,
    ): RectF {
        if (sourceWidth <= 0f || sourceHeight <= 0f || targetWidth <= 0f || targetHeight <= 0f) {
            return RectF(0f, 0f, targetWidth, targetHeight)
        }

        val scale = min(targetWidth / sourceWidth, targetHeight / sourceHeight)
        val width = sourceWidth * scale
        val height = sourceHeight * scale
        val left = (targetWidth - width) * 0.5f
        val top = (targetHeight - height) * 0.5f
        return RectF(left, top, left + width, top + height)
    }
}
