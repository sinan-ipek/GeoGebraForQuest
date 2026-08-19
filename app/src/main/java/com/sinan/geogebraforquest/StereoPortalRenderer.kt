package com.sinan.geogebraforquest

import android.net.Uri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.Visible
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Lightweight native stereo mirror of the supported GeoGebra 3D objects.
 *
 * The WebView stays as ordinary GeoGebra. When Stereo 3D is enabled, JavaScript makes only
 * GeoGebra's WebGL 3D canvas transparent. These native entities sit behind that transparent
 * rectangle, so Horizon/Spatial SDK gives them true binocular stereo while the rest of the
 * GeoGebra interface remains a normal 2D panel.
 *
 * v0.2 supports the common primitives needed to validate the architecture:
 * points, segments/lines/rays, sphere commands, polygon edges and 3-point planes.
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
        if (stereoEnabled == enabled) {
            return
        }
        stereoEnabled = enabled
        portalRoot.setComponent(Visible(enabled))
        if (!enabled) {
            clearObjects()
        } else {
            lastSceneJson?.let { rebuild(it) }
        }
    }

    fun updatePortalRect(json: String) {
        try {
            val data = JSONObject(json)
            portalRect = PortalRect(
                left = data.optDouble("left", 0.0).toFloat(),
                top = data.optDouble("top", 0.0).toFloat(),
                width = data.optDouble("width", 1.0).toFloat().coerceAtLeast(1f),
                height = data.optDouble("height", 1.0).toFloat().coerceAtLeast(1f),
                viewWidth = data.optDouble("viewWidth", 1080.0).toFloat().coerceAtLeast(1f),
                viewHeight = data.optDouble("viewHeight", 720.0).toFloat().coerceAtLeast(1f),
            )
            updatePortalTransform()
            if (stereoEnabled) {
                lastSceneJson?.let { rebuild(it) }
            }
        } catch (_: Throwable) {
            // Keep the previous rectangle. The WebView may send a transient zero-size rect
            // during a GeoGebra layout change.
        }
    }

    fun updateScene(json: String) {
        lastSceneJson = json
        if (!stereoEnabled) {
            return
        }
        rebuild(json)
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

        // GeoGebra's zAngle is rotation around its vertical Z axis. In our panel coordinates
        // GeoGebra Z maps to +Y, so zAngle maps naturally to a yaw around panel Y.
        val rotation = Quaternion(
            -camera.xAngle,
            -camera.zAngle,
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
            val cameraJson = data.optJSONObject("camera")
            if (cameraJson != null) {
                camera = CameraState(
                    xZero = cameraJson.optDouble("xZero", 0.0).toFloat(),
                    yZero = cameraJson.optDouble("yZero", 0.0).toFloat(),
                    zZero = cameraJson.optDouble("zZero", 0.0).toFloat(),
                    scale = cameraJson.optDouble("scale", 50.0).toFloat().coerceAtLeast(1f),
                    xAngle = cameraJson.optDouble("xAngle", 20.0).toFloat(),
                    zAngle = cameraJson.optDouble("zAngle", -60.0).toFloat(),
                )
                updatePortalTransform()
            }

            clearObjects()
            if (!stereoEnabled) {
                return
            }

            if (data.optBoolean("axes", true)) {
                createAxes()
            }

            val objects = data.optJSONArray("objects") ?: JSONArray()
            for (i in 0 until objects.length()) {
                val obj = objects.optJSONObject(i) ?: continue
                when (obj.optString("kind")) {
                    "point" -> createPoint(obj)
                    "segment" -> createSegmentLike(obj, SegmentMode.SEGMENT)
                    "line" -> createSegmentLike(obj, SegmentMode.LINE)
                    "ray" -> createSegmentLike(obj, SegmentMode.RAY)
                    "sphere" -> createSphere(obj)
                    "polygon" -> createPolygon(obj)
                    "plane" -> createPlane(obj)
                }
            }
        } catch (_: Throwable) {
            // A malformed single sync payload must not crash the VR activity.
        }
    }

    private fun createAxes() {
        val span = 4.5f
        createLine(
            Vec3(-span, 0f, 0f),
            Vec3(span, 0f, 0f),
            Color4(0.92f, 0.18f, 0.18f, 1f),
            0.006f,
        )
        createLine(
            Vec3(0f, -span, 0f),
            Vec3(0f, span, 0f),
            Color4(0.20f, 0.72f, 0.28f, 1f),
            0.006f,
        )
        createLine(
            Vec3(0f, 0f, -span),
            Vec3(0f, 0f, span),
            Color4(0.18f, 0.38f, 0.96f, 1f),
            0.006f,
        )
    }

    private fun createPoint(obj: JSONObject) {
        val p = readVec(obj.optJSONObject("p")) ?: return
        val position = mapPoint(p)
        val size = obj.optDouble("pointSize", 5.0).toFloat()
        val radius = (0.010f + size * 0.0013f).coerceIn(0.012f, 0.035f)
        val entity = Entity.create(
            listOf(
                Mesh(Uri.parse("mesh://sphere")),
                material(colorOf(obj, 1f)),
                Transform(Pose(position)),
                Scale(Vector3(radius * 2f, radius * 2f, radius * 2f)),
                TransformParent(portalRoot),
            ),
        )
        rendered += entity
    }

    private fun createSegmentLike(obj: JSONObject, mode: SegmentMode) {
        var a = readVec(obj.optJSONObject("a")) ?: return
        var b = readVec(obj.optJSONObject("b")) ?: return

        val dx = b.x - a.x
        val dy = b.y - a.y
        val dz = b.z - a.z
        val len = sqrt(dx * dx + dy * dy + dz * dz)
        if (len < 1e-5f) return

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

        val thicknessValue = obj.optDouble("thickness", 5.0).toFloat()
        val thickness = (0.0035f + thicknessValue * 0.00045f).coerceIn(0.004f, 0.014f)
        createLine(a, b, colorOf(obj, 1f), thickness)
    }

    private fun createSphere(obj: JSONObject) {
        val center = readVec(obj.optJSONObject("center")) ?: return
        val radius = obj.optDouble("radius", 0.0).toFloat()
        if (radius <= 0f) return

        val mapped = mapPoint(center)
        val diameter = max(0.012f, radius * unitScale * 2f)
        val alpha = obj.optDouble("alpha", 0.28).toFloat().coerceIn(0.12f, 1f)

        val entity = Entity.create(
            listOf(
                Mesh(Uri.parse("mesh://sphere")),
                material(colorOf(obj, alpha)),
                Transform(Pose(mapped)),
                Scale(Vector3(diameter, diameter, diameter)),
                TransformParent(portalRoot),
            ),
        )
        rendered += entity
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
        val thicknessValue = obj.optDouble("thickness", 5.0).toFloat()
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
        val alpha = obj.optDouble("alpha", 0.18).toFloat().coerceIn(0.08f, 0.42f)
        val q = Quaternion.lookRotation(Vector3(normal.x, normal.y, normal.z))

        val entity = Entity.create(
            listOf(
                Mesh(Uri.parse("mesh://box")),
                material(colorOf(obj, alpha)),
                Transform(Pose(center, q)),
                Scale(Vector3(size, size, 0.006f)),
                TransformParent(portalRoot),
            ),
        )
        rendered += entity
    }

    private fun createLine(a: Vec3, b: Vec3, color: Color4, thickness: Float) {
        createLineMapped(mapPoint(a), mapPoint(b), color, thickness)
    }

    private fun createLineMapped(a: Vector3, b: Vector3, color: Color4, thickness: Float) {
        val dx = b.x - a.x
        val dy = b.y - a.y
        val dz = b.z - a.z
        val length = sqrt(dx * dx + dy * dy + dz * dz)
        if (length < 1e-5f) return

        val midpoint = Vector3(
            (a.x + b.x) * 0.5f,
            (a.y + b.y) * 0.5f,
            (a.z + b.z) * 0.5f,
        )
        val direction = Vector3(dx / length, dy / length, dz / length)
        val rotation = Quaternion.lookRotation(direction)

        val entity = Entity.create(
            listOf(
                Mesh(Uri.parse("mesh://box")),
                material(color),
                Transform(Pose(midpoint, rotation)),
                Scale(Vector3(thickness, thickness, length)),
                TransformParent(portalRoot),
            ),
        )
        rendered += entity
    }

    private fun mapPoint(p: Vec3): Vector3 {
        // GeoGebra coordinates: X right, Y depth, Z up.
        // Portal-local Spatial coordinates: X right, Y up, Z deeper into the window.
        val x = (p.x - camera.xZero) * unitScale
        val y = (p.z - camera.zZero) * unitScale
        val z = (p.y - camera.yZero) * unitScale
        return Vector3(x, y, z)
    }

    private fun colorOf(obj: JSONObject, alpha: Float): Color4 {
        val hex = obj.optString("color", "#4F46E5")
        val clean = hex.removePrefix("#")
        val value = clean.toLongOrNull(16) ?: 0x4F46E5
        val r = ((value shr 16) and 0xFF).toFloat() / 255f
        val g = ((value shr 8) and 0xFF).toFloat() / 255f
        val b = (value and 0xFF).toFloat() / 255f
        return Color4(r, g, b, alpha.coerceIn(0f, 1f))
    }

    private fun material(color: Color4): Material {
        return Material().apply {
            baseColor = color
            unlit = true
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
            if (len < 1e-6f) return null
            return Vec3(x / len, y / len, z / len)
        }
    }

    private enum class SegmentMode {
        SEGMENT,
        LINE,
        RAY,
    }
}
