package com.sinan.geogebraforquest

import android.net.Uri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.AlphaMode
import com.meta.spatial.toolkit.Box
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.Visible
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Native stereo mirror shown only inside GeoGebra's existing 3D Graphics rectangle.
 *
 * v0.4.3 uses the same procedural primitive descriptions as Meta's official samples:
 * Mesh("mesh://sphere") is paired with Sphere(radius), and Mesh("mesh://box") with
 * Box(min,max). Earlier versions created those meshes with Scale only. That left the
 * native procedural primitive incompletely described precisely when the headset button
 * exposed the portal, which is a likely source of the click-time native crash on Quest.
 *
 * There is no Activity launch and no mode transition here. The app is already spatial
 * from startup only so Horizon can render different pixels to the two eyes. GeoGebra's
 * interface remains a flat panel; the 3D canvas alone becomes the stereo depth window.
 */
class StereoPortalRenderer(
    private val panelEntity: Entity,
    private val panelWidthMeters: Float,
    private val panelHeightMeters: Float,
) {
    private val portalRoot = Entity.create(
        listOf(
            Transform(Pose(Vector3(0f, 0f, 0.12f))),
            TransformParent(panelEntity),
            Visible(false),
        ),
    )

    private val rendered = mutableListOf<Entity>()

    private var stereoEnabled = false
    private var lastSceneJson: String? = null
    private var portalRect = PortalRect()
    private var camera = CameraState()
    private var unitScale = 0.04f

    fun setStereoEnabled(enabled: Boolean) {
        if (stereoEnabled == enabled) return
        stereoEnabled = enabled

        if (!enabled) {
            portalRoot.setComponent(Visible(false))
            clearObjects()
            return
        }

        // Build the complete native scene while the portal is still hidden, then expose it.
        lastSceneJson?.let(::rebuild)
        portalRoot.setComponent(Visible(true))
    }

    fun updatePortalRect(json: String) {
        try {
            val data = JSONObject(json)
            portalRect = PortalRect(
                left = finiteFloat(data.optDouble("left", 0.0), 0f),
                top = finiteFloat(data.optDouble("top", 0.0), 0f),
                width = finiteFloat(data.optDouble("width", 1.0), 1f).coerceAtLeast(1f),
                height = finiteFloat(data.optDouble("height", 1.0), 1f).coerceAtLeast(1f),
                viewWidth = finiteFloat(data.optDouble("viewWidth", 1080.0), 1080f).coerceAtLeast(1f),
                viewHeight = finiteFloat(data.optDouble("viewHeight", 720.0), 720f).coerceAtLeast(1f),
            )
            updatePortalTransform()
            if (stereoEnabled) lastSceneJson?.let(::rebuild)
        } catch (_: Throwable) {
            // Keep the previous rectangle during transient GeoGebra relayouts.
        }
    }

    fun updateScene(json: String) {
        lastSceneJson = json
        if (stereoEnabled) rebuild(json)
    }

    fun destroy() {
        clearObjects()
        portalRoot.destroy()
    }

    private fun updatePortalTransform() {
        val centerXRatio = (portalRect.left + portalRect.width * 0.5f) / portalRect.viewWidth
        val centerYRatio = (portalRect.top + portalRect.height * 0.5f) / portalRect.viewHeight

        val centerX = (centerXRatio - 0.5f) * panelWidthMeters
        val centerY = (0.5f - centerYRatio) * panelHeightMeters

        val portalWidthMeters = panelWidthMeters * portalRect.width / portalRect.viewWidth
        val meterPerCssPixel = portalWidthMeters / portalRect.width
        unitScale = (camera.scale * meterPerCssPixel).coerceIn(0.012f, 0.085f)

        val rotation = Quaternion.fromEuler(
            finiteFloat(-camera.xAngle.toDouble(), 0f),
            finiteFloat(-camera.zAngle.toDouble(), 0f),
            0f,
        )

        portalRoot.setComponent(
            Transform(
                Pose(
                    Vector3(centerX, centerY, 0.12f),
                    rotation,
                ),
            ),
        )
    }

    private fun rebuild(json: String) {
        try {
            val data = JSONObject(json)
            data.optJSONObject("camera")?.let { cameraJson ->
                camera = CameraState(
                    xZero = finiteFloat(cameraJson.optDouble("xZero", 0.0), 0f),
                    yZero = finiteFloat(cameraJson.optDouble("yZero", 0.0), 0f),
                    zZero = finiteFloat(cameraJson.optDouble("zZero", 0.0), 0f),
                    scale = finiteFloat(cameraJson.optDouble("scale", 50.0), 50f).coerceAtLeast(1f),
                    xAngle = finiteFloat(cameraJson.optDouble("xAngle", 20.0), 20f),
                    zAngle = finiteFloat(cameraJson.optDouble("zAngle", -60.0), -60f),
                )
                updatePortalTransform()
            }

            clearObjects()
            if (!stereoEnabled) return

            if (data.optBoolean("axes", true)) createAxes()

            val objects = data.optJSONArray("objects") ?: JSONArray()
            for (i in 0 until objects.length()) {
                val obj = objects.optJSONObject(i) ?: continue
                when (obj.optString("kind")) {
                    "point" -> createPoint(obj)
                    "segment" -> createSegmentLike(obj, SegmentMode.SEGMENT)
                    "line" -> createSegmentLike(obj, SegmentMode.LINE)
                    "ray" -> createSegmentLike(obj, SegmentMode.RAY)
                    "polyline" -> createPolyline(obj)
                    "sphere" -> createSphere(obj)
                    "polygon" -> createPolygon(obj)
                    "plane" -> createPlane(obj)
                }
            }
        } catch (_: Throwable) {
            // Keep malformed/transient scene payloads from affecting the host activity.
        }
    }

    private fun createAxes() {
        val span = 4.5f
        createLine(
            Vec3(-span, 0f, 0f), Vec3(span, 0f, 0f),
            Color4(0.92f, 0.18f, 0.18f, 1f), 0.006f,
        )
        createLine(
            Vec3(0f, -span, 0f), Vec3(0f, span, 0f),
            Color4(0.20f, 0.72f, 0.28f, 1f), 0.006f,
        )
        createLine(
            Vec3(0f, 0f, -span), Vec3(0f, 0f, span),
            Color4(0.18f, 0.38f, 0.96f, 1f), 0.006f,
        )
    }

    private fun createPoint(obj: JSONObject) {
        val p = readVec(obj.optJSONObject("p")) ?: return
        val position = mapPoint(p)
        if (!position.isFiniteVector()) return

        val pointSize = finiteFloat(obj.optDouble("pointSize", 5.0), 5f)
        val radius = (0.010f + pointSize * 0.0013f).coerceIn(0.012f, 0.035f)

        rendered += Entity.create(
            listOf(
                Sphere(radius),
                Mesh(Uri.parse("mesh://sphere")),
                material(colorOf(obj, 1f)),
                Transform(Pose(position)),
                TransformParent(portalRoot),
            ),
        )
    }

    private fun createSegmentLike(obj: JSONObject, mode: SegmentMode) {
        var a = readVec(obj.optJSONObject("a")) ?: return
        var b = readVec(obj.optJSONObject("b")) ?: return

        val dx = b.x - a.x
        val dy = b.y - a.y
        val dz = b.z - a.z
        val len = sqrt(dx * dx + dy * dy + dz * dz)
        if (!len.isFinite() || len < 1e-5f) return

        val ux = dx / len
        val uy = dy / len
        val uz = dz / len
        val span = 9f

        when (mode) {
            SegmentMode.LINE -> {
                a = Vec3(a.x - ux * span, a.y - uy * span, a.z - uz * span)
                b = Vec3(b.x + ux * span, b.y + uy * span, b.z + uz * span)
            }
            SegmentMode.RAY -> {
                b = Vec3(a.x + ux * span, a.y + uy * span, a.z + uz * span)
            }
            SegmentMode.SEGMENT -> Unit
        }

        val thicknessValue = finiteFloat(obj.optDouble("thickness", 5.0), 5f)
        val thickness = (0.0035f + thicknessValue * 0.00045f).coerceIn(0.004f, 0.014f)
        createLine(a, b, colorOf(obj, 1f), thickness)
    }

    private fun createPolyline(obj: JSONObject) {
        val pointsJson = obj.optJSONArray("points") ?: return
        if (pointsJson.length() < 2) return

        val points = mutableListOf<Vec3>()
        for (i in 0 until pointsJson.length()) {
            readVec(pointsJson.optJSONObject(i))?.let(points::add)
        }
        if (points.size < 2) return

        val color = colorOf(obj, 1f)
        val thicknessValue = finiteFloat(obj.optDouble("thickness", 5.0), 5f)
        val thickness = (0.0035f + thicknessValue * 0.00045f).coerceIn(0.004f, 0.014f)

        for (i in 1 until points.size) {
            createLine(points[i - 1], points[i], color, thickness)
        }
    }

    private fun createSphere(obj: JSONObject) {
        val center = readVec(obj.optJSONObject("center")) ?: return
        val radiusGeo = finiteFloat(obj.optDouble("radius", 0.0), 0f)
        if (radiusGeo <= 0f) return

        val mapped = mapPoint(center)
        if (!mapped.isFiniteVector()) return

        val radiusMeters = max(0.006f, radiusGeo * unitScale)
        val alpha = finiteFloat(obj.optDouble("alpha", 0.28), 0.28f).coerceIn(0.12f, 1f)

        rendered += Entity.create(
            listOf(
                Sphere(radiusMeters),
                Mesh(Uri.parse("mesh://sphere")),
                material(colorOf(obj, alpha)),
                Transform(Pose(mapped)),
                TransformParent(portalRoot),
            ),
        )
    }

    private fun createPolygon(obj: JSONObject) {
        val pointsJson = obj.optJSONArray("points") ?: return
        if (pointsJson.length() < 3) return

        val points = mutableListOf<Vec3>()
        for (i in 0 until pointsJson.length()) {
            readVec(pointsJson.optJSONObject(i))?.let(points::add)
        }
        if (points.size < 3) return

        val color = colorOf(obj, 1f)
        val thicknessValue = finiteFloat(obj.optDouble("thickness", 5.0), 5f)
        val thickness = (0.0035f + thicknessValue * 0.00045f).coerceIn(0.004f, 0.014f)

        for (i in points.indices) {
            createLine(points[i], points[(i + 1) % points.size], color, thickness)
        }
    }

    private fun createPlane(obj: JSONObject) {
        val pointsJson = obj.optJSONArray("points") ?: return
        if (pointsJson.length() < 3) return

        val a = readVec(pointsJson.optJSONObject(0)) ?: return
        val b = readVec(pointsJson.optJSONObject(1)) ?: return
        val c = readVec(pointsJson.optJSONObject(2)) ?: return

        val pa = mapPoint(a)
        val pb = mapPoint(b)
        val pc = mapPoint(c)
        if (!pa.isFiniteVector() || !pb.isFiniteVector() || !pc.isFiniteVector()) return

        val ab = Vec3(pb.x - pa.x, pb.y - pa.y, pb.z - pa.z)
        val ac = Vec3(pc.x - pa.x, pc.y - pa.y, pc.z - pa.z)
        val normal = cross(ab, ac).normalizedOrNull() ?: return

        val center = Vector3(
            (pa.x + pb.x + pc.x) / 3f,
            (pa.y + pb.y + pc.y) / 3f,
            (pa.z + pb.z + pc.z) / 3f,
        )

        val portalPhysicalWidth = panelWidthMeters * portalRect.width / portalRect.viewWidth
        val portalPhysicalHeight = panelHeightMeters * portalRect.height / portalRect.viewHeight
        val size = max(portalPhysicalWidth, portalPhysicalHeight) * 1.35f
        if (!size.isFinite() || size <= 0f) return

        val alpha = finiteFloat(obj.optDouble("alpha", 0.18), 0.18f).coerceIn(0.08f, 0.42f)
        val q = Quaternion.lookRotation(Vector3(normal.x, normal.y, normal.z))
        val half = size * 0.5f
        val halfDepth = 0.003f

        rendered += Entity.create(
            listOf(
                Box(
                    Vector3(-half, -half, -halfDepth),
                    Vector3(half, half, halfDepth),
                ),
                Mesh(Uri.parse("mesh://box")),
                material(colorOf(obj, alpha)),
                Transform(Pose(center, q)),
                TransformParent(portalRoot),
            ),
        )
    }

    private fun createLine(a: Vec3, b: Vec3, color: Color4, thickness: Float) {
        createLineMapped(mapPoint(a), mapPoint(b), color, thickness)
    }

    private fun createLineMapped(a: Vector3, b: Vector3, color: Color4, thickness: Float) {
        if (!a.isFiniteVector() || !b.isFiniteVector()) return

        val dx = b.x - a.x
        val dy = b.y - a.y
        val dz = b.z - a.z
        val length = sqrt(dx * dx + dy * dy + dz * dz)
        if (!length.isFinite() || length < 1e-5f) return

        val direction = Vector3(dx / length, dy / length, dz / length)
        if (!direction.isFiniteVector()) return

        val rotation = Quaternion.lookRotation(direction)
        val halfThickness = thickness * 0.5f

        // Same box definition used by Meta's BodyTracking sample: z=0 -> z=length,
        // with the entity transform placed at the segment start.
        rendered += Entity.create(
            listOf(
                Box(
                    Vector3(-halfThickness, -halfThickness, 0f),
                    Vector3(halfThickness, halfThickness, length),
                ),
                Mesh(Uri.parse("mesh://box")),
                material(color),
                Transform(Pose(a, rotation)),
                TransformParent(portalRoot),
            ),
        )
    }

    private fun mapPoint(p: Vec3): Vector3 {
        return Vector3(
            (p.x - camera.xZero) * unitScale,
            (p.z - camera.zZero) * unitScale,
            (p.y - camera.yZero) * unitScale,
        )
    }

    private fun colorOf(obj: JSONObject, alpha: Float): Color4 {
        val clean = obj.optString("color", "#4F46E5").removePrefix("#")
        val value = clean.toLongOrNull(16) ?: 0x4F46E5
        return Color4(
            ((value shr 16) and 0xFF).toFloat() / 255f,
            ((value shr 8) and 0xFF).toFloat() / 255f,
            (value and 0xFF).toFloat() / 255f,
            alpha.coerceIn(0f, 1f),
        )
    }

    private fun material(color: Color4): Material {
        return Material().apply {
            baseColor = color
            unlit = true
            if (color.alpha < 0.999f) {
                alphaMode = AlphaMode.TRANSLUCENT.ordinal
            }
        }
    }

    private fun readVec(obj: JSONObject?): Vec3? {
        if (obj == null) return null
        val x = obj.optDouble("x", Double.NaN)
        val y = obj.optDouble("y", Double.NaN)
        val z = obj.optDouble("z", Double.NaN)
        if (!x.isFinite() || !y.isFinite() || !z.isFinite()) return null
        return Vec3(x.toFloat(), y.toFloat(), z.toFloat())
    }

    private fun finiteFloat(value: Double, fallback: Float): Float {
        return if (value.isFinite() && value in -1.0e6..1.0e6) value.toFloat() else fallback
    }

    private fun Vector3.isFiniteVector(): Boolean {
        return x.isFinite() && y.isFinite() && z.isFinite()
    }

    private fun cross(a: Vec3, b: Vec3): Vec3 {
        return Vec3(
            a.y * b.z - a.z * b.y,
            a.z * b.x - a.x * b.z,
            a.x * b.y - a.y * b.x,
        )
    }

    private fun clearObjects() {
        rendered.forEach { entity ->
            try {
                entity.destroy()
            } catch (_: Throwable) {
            }
        }
        rendered.clear()
    }

    private data class PortalRect(
        val left: Float = 0f,
        val top: Float = 0f,
        val width: Float = 720f,
        val height: Float = 620f,
        val viewWidth: Float = 1080f,
        val viewHeight: Float = 720f,
    )

    private data class CameraState(
        val xZero: Float = 0f,
        val yZero: Float = 0f,
        val zZero: Float = 0f,
        val scale: Float = 50f,
        val xAngle: Float = 20f,
        val zAngle: Float = -60f,
    )

    private data class Vec3(val x: Float, val y: Float, val z: Float) {
        fun normalizedOrNull(): Vec3? {
            val len = sqrt(x * x + y * y + z * z)
            if (!len.isFinite() || len < 1e-6f) return null
            return Vec3(x / len, y / len, z / len)
        }
    }

    private enum class SegmentMode {
        SEGMENT,
        LINE,
        RAY,
    }
}
