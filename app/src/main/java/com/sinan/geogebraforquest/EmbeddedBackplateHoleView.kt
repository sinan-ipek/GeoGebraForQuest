package com.sinan.geogebraforquest

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.max
import kotlin.math.min
import org.json.JSONObject

/**
 * White rear backing surface with a dynamic transparent rectangular hole.
 *
 * The GeoGebra WebView stays alpha-capable. Shared GeoGebra background layers may therefore
 * become transparent outside the 3D view as a side effect of the selective-hole experiment.
 * This rear view restores white everywhere except exactly behind the live 3D rectangle.
 * Transparent pixels in the hole allow the closer magenta/stereo proof panel to remain visible.
 */
class EmbeddedBackplateHoleView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    private val whitePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.FILL
    }

    private var holeRect: RectF? = null

    private val layoutListener: (String) -> Unit = { json ->
        post { applyStereoLayout(json) }
    }

    init {
        setBackgroundColor(Color.TRANSPARENT)
        setWillNotDraw(false)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        SpatialBridgeBus.onBackplateLayout = layoutListener
    }

    override fun onDetachedFromWindow() {
        if (SpatialBridgeBus.onBackplateLayout === layoutListener) {
            SpatialBridgeBus.onBackplateLayout = null
        }
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val hole = holeRect
        if (hole == null || hole.width() <= 0f || hole.height() <= 0f) {
            canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), whitePaint)
            return
        }

        val left = hole.left.coerceIn(0f, width.toFloat())
        val top = hole.top.coerceIn(0f, height.toFloat())
        val right = hole.right.coerceIn(0f, width.toFloat())
        val bottom = hole.bottom.coerceIn(0f, height.toFloat())

        // Four non-overlapping white strips. Nothing is drawn inside the 3D rectangle, so that
        // region remains genuinely transparent all the way through this Spatial panel texture.
        if (top > 0f) {
            canvas.drawRect(0f, 0f, width.toFloat(), top, whitePaint)
        }
        if (bottom < height) {
            canvas.drawRect(0f, bottom, width.toFloat(), height.toFloat(), whitePaint)
        }
        if (left > 0f && bottom > top) {
            canvas.drawRect(0f, top, left, bottom, whitePaint)
        }
        if (right < width && bottom > top) {
            canvas.drawRect(right, top, width.toFloat(), bottom, whitePaint)
        }
    }

    private fun applyStereoLayout(json: String) {
        try {
            val root = JSONObject(json)
            if (!root.optBoolean("active", true)) {
                holeRect = null
                invalidate()
                return
            }

            val stereo = root.optJSONObject("stereo") ?: run {
                holeRect = null
                invalidate()
                return
            }

            val viewWidth = root.optDouble("viewWidth", 0.0)
            val viewHeight = root.optDouble("viewHeight", 0.0)
            if (viewWidth <= 1.0 || viewHeight <= 1.0 || width <= 0 || height <= 0) {
                return
            }

            val sx = width.toDouble() / viewWidth
            val sy = height.toDouble() / viewHeight

            // A half-pixel outward bias avoids a white antialiasing seam at the hole boundary.
            val bias = 0.5f
            val left = max(0f, (stereo.optDouble("left", 0.0) * sx).toFloat() - bias)
            val top = max(0f, (stereo.optDouble("top", 0.0) * sy).toFloat() - bias)
            val right = min(
                width.toFloat(),
                ((stereo.optDouble("left", 0.0) + stereo.optDouble("width", 0.0)) * sx)
                    .toFloat() + bias,
            )
            val bottom = min(
                height.toFloat(),
                ((stereo.optDouble("top", 0.0) + stereo.optDouble("height", 0.0)) * sy)
                    .toFloat() + bias,
            )

            if (right <= left || bottom <= top) {
                holeRect = null
            } else {
                holeRect = RectF(left, top, right, bottom)
            }
            invalidate()
        } catch (_: Throwable) {
            // Keep the last valid geometry rather than flashing the rear surface.
        }
    }
}
