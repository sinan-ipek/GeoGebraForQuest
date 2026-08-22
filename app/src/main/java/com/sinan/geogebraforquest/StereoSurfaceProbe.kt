package com.sinan.geogebraforquest

import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.util.Log
import android.view.Surface

/**
 * GeoGebraForQuest v0.9.20 TEST source.
 *
 * Draws the bundled user-provided SBS stereo photo directly into the same
 * registered VideoSurfacePanelRegistration surface used by live GeoGebra.
 * The bitmap is already L|R: its left half is mapped to the Surface left half
 * and its right half is mapped to the Surface right half. Meta
 * StereoMode.LeftRight performs the final physical eye routing.
 */
object StereoSurfaceProbe {
    private const val TAG = "GeoGebraForQuest"

    fun draw(context: Context, surface: Surface) {
        if (!surface.isValid) {
            Log.w(TAG, "v0.9.20 stereo TEST received invalid surface")
            return
        }

        val bitmap = BitmapFactory.decodeResource(
            context.resources,
            R.drawable.stereo_test_photo,
        ) ?: run {
            Log.e(TAG, "v0.9.20 stereo TEST photo could not be decoded")
            return
        }

        var canvas: android.graphics.Canvas? = null
        try {
            canvas = surface.lockCanvas(null)
            canvas.drawColor(Color.BLACK)

            val sourceHalf = bitmap.width / 2
            val targetHalf = canvas.width / 2
            if (
                sourceHalf <= 0 ||
                bitmap.height <= 0 ||
                targetHalf <= 0 ||
                canvas.height <= 0
            ) {
                return
            }

            val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
                isDither = false
            }

            val leftSource = Rect(0, 0, sourceHalf, bitmap.height)
            val rightSource = Rect(sourceHalf, 0, bitmap.width, bitmap.height)
            val leftDestination = Rect(0, 0, targetHalf, canvas.height)
            val rightDestination = Rect(targetHalf, 0, canvas.width, canvas.height)

            canvas.drawBitmap(bitmap, leftSource, leftDestination, paint)
            canvas.drawBitmap(bitmap, rightSource, rightDestination, paint)

            Log.i(
                TAG,
                "v0.9.20 stereo photo TEST drawn: " +
                    "source=${bitmap.width}x${bitmap.height}, " +
                    "surface=${canvas.width}x${canvas.height}",
            )
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.20 stereo photo TEST draw failed", error)
        } finally {
            bitmap.recycle()
            if (canvas != null) {
                try {
                    surface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.20 stereo photo TEST post failed", error)
                }
            }
        }
    }
}
