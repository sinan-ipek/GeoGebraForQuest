package com.sinan.geogebraforquest

import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.util.Log
import android.view.Surface

/**
 * Draws a deterministic full-colour L|R SBS test image directly into a
 * VideoSurfacePanelRegistration surface.
 *
 * The registered media panel itself performs StereoMode.LeftRight eye routing.
 * No GeoGebra, WebView texture, custom shader or SceneObject overlay is involved.
 */
object StereoSurfaceProbe {
    private const val TAG = "GeoGebraForQuest"

    fun draw(surface: Surface) {
        if (!surface.isValid) {
            Log.w(TAG, "v0.9.11 stereo surface probe received invalid surface")
            return
        }

        var canvas: android.graphics.Canvas? = null
        try {
            canvas = surface.lockCanvas(null)
            val width = canvas.width.toFloat()
            val height = canvas.height.toFloat()
            val half = width / 2f

            val leftPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.rgb(180, 24, 24)
                style = Paint.Style.FILL
            }
            val rightPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.rgb(20, 70, 190)
                style = Paint.Style.FILL
            }
            val dividerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE
                strokeWidth = 6f
            }
            val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE
                textAlign = Paint.Align.CENTER
                typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
                textSize = height * 0.52f
            }
            val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE
                textAlign = Paint.Align.CENTER
                typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
                textSize = height * 0.095f
            }

            canvas.drawColor(Color.BLACK)
            canvas.drawRect(0f, 0f, half, height, leftPaint)
            canvas.drawRect(half, 0f, width, height, rightPaint)
            canvas.drawLine(half, 0f, half, height, dividerPaint)

            val baseline = height * 0.63f
            canvas.drawText("L", half * 0.5f, baseline, textPaint)
            canvas.drawText("R", half + half * 0.5f, baseline, textPaint)
            canvas.drawText("LEFT", half * 0.5f, height * 0.88f, labelPaint)
            canvas.drawText("RIGHT", half + half * 0.5f, height * 0.88f, labelPaint)

            Log.i(TAG, "v0.9.11 stereo surface probe frame drawn: ${canvas.width}x${canvas.height}")
        } catch (error: Throwable) {
            Log.e(TAG, "v0.9.11 stereo surface probe draw failed", error)
        } finally {
            if (canvas != null) {
                try {
                    surface.unlockCanvasAndPost(canvas)
                } catch (error: Throwable) {
                    Log.e(TAG, "v0.9.11 stereo surface probe post failed", error)
                }
            }
        }
    }
}
