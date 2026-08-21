package com.sinan.geogebraforquest

import android.graphics.Color
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Vector3
import com.meta.spatial.core.Vector4
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneMaterialAttribute
import com.meta.spatial.runtime.SceneMaterialDataType
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.runtime.SceneObject
import com.meta.spatial.runtime.SceneTexture
import com.meta.spatial.runtime.TriangleMesh
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.SceneObjectSystem
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.Visible
import java.util.concurrent.CompletableFuture
import org.json.JSONObject

/**
 * Zero-copy Quest stereo display for GeoGebra's source-rendered SBS canvas.
 *
 * The source texture is the *existing LayoutXML/WebView panel texture* supplied
 * by Spatial SDK. The custom shader samples the left or right half of the 3D
 * canvas rectangle according to the current Quest eye. There is therefore no
 * GPU -> CPU -> GPU frame transport at all.
 *
 * This entity intentionally has no Panel/Hittable/Grabbable component. The ray
 * continues to hit the real GeoGebra WebView underneath it.
 */
class QuestStereoPortalRenderer(
    private val activity: AppSystemActivity,
    parent: Entity,
    panelTexture: SceneTexture,
) {

    companion object {
        private const val PORTAL_Z = -0.006f
    }

    private val material =
        SceneMaterial.custom(
            "questStereoPortal",
            arrayOf(
                SceneMaterialAttribute("sourceRect", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("albedoSampler", SceneMaterialDataType.Texture2D),
            ),
        ).apply {
            setAttribute("sourceRect", Vector4(0f, 0f, 1f, 1f))
            setTexture("albedoSampler", panelTexture)
        }

    private val entity =
        Entity.create(
            TransformParent(parent),
            Transform(Pose(Vector3(0f, 0f, PORTAL_Z))),
            Scale(Vector3(0.01f, 0.01f, 1f)),
            Visible(false),
        )

    private val sceneObject: SceneObject

    @Volatile
    private var requestedVisible = false

    init {
        val mesh = createUnitQuad(material)
        sceneObject = SceneObject(activity.scene, mesh, "ggq-quest-stereo-portal", entity)

        activity.systemManager
            .findSystem<SceneObjectSystem>()
            .addSceneObject(
                entity,
                CompletableFuture<SceneObject>().apply { complete(sceneObject) },
            )
    }

    /**
     * Update both the physical portal rectangle and the source crop in the
     * underlying WebView panel texture.
     */
    fun updateRect(
        json: String,
        panelWidthMeters: Float,
        panelHeightMeters: Float,
    ) {
        try {
            val data = JSONObject(json)
            val left = data.optDouble("left", Double.NaN)
            val top = data.optDouble("top", Double.NaN)
            val width = data.optDouble("width", Double.NaN)
            val height = data.optDouble("height", Double.NaN)
            val viewWidth = data.optDouble("viewWidth", Double.NaN)
            val viewHeight = data.optDouble("viewHeight", Double.NaN)

            if (
                !left.isFinite() || !top.isFinite() ||
                !width.isFinite() || !height.isFinite() ||
                !viewWidth.isFinite() || !viewHeight.isFinite() ||
                width <= 0.0 || height <= 0.0 ||
                viewWidth <= 0.0 || viewHeight <= 0.0
            ) return

            val centerXPixels = left + width / 2.0
            val centerYPixels = top + height / 2.0
            val centerX =
                (centerXPixels / viewWidth - 0.5).toFloat() * panelWidthMeters
            val centerY =
                (0.5 - centerYPixels / viewHeight).toFloat() * panelHeightMeters
            val widthMeters = (width / viewWidth).toFloat() * panelWidthMeters
            val heightMeters = (height / viewHeight).toFloat() * panelHeightMeters

            // The quad UV convention below has v=0 at its visual top, matching
            // DOM getBoundingClientRect() coordinates.
            val sourceRect =
                Vector4(
                    (left / viewWidth).toFloat(),
                    (top / viewHeight).toFloat(),
                    (width / viewWidth).toFloat(),
                    (height / viewHeight).toFloat(),
                )

            activity.runOnUiThread {
                material.setAttribute("sourceRect", sourceRect)
                entity.setComponent(
                    Transform(Pose(Vector3(centerX, centerY, PORTAL_Z))),
                )
                entity.setComponent(
                    Scale(Vector3(widthMeters, heightMeters, 1f)),
                )
                entity.setComponent(Visible(requestedVisible))
            }
        } catch (_: Throwable) {
            // A transient DOM layout rectangle is disposable.
        }
    }

    fun setVisible(visible: Boolean) {
        requestedVisible = visible
        activity.runOnUiThread {
            entity.setComponent(Visible(visible))
        }
    }

    fun release() {
        requestedVisible = false
        activity.runOnUiThread {
            entity.setComponent(Visible(false))
            entity.destroy()
        }
    }

    private fun createUnitQuad(material: SceneMaterial): SceneMesh {
        val triMesh =
            TriangleMesh(
                4,
                6,
                intArrayOf(6),
                arrayOf(material),
            )

        triMesh.updateGeometry(
            0,
            floatArrayOf(
                -0.5f, -0.5f, 0f,
                0.5f, -0.5f, 0f,
                0.5f, 0.5f, 0f,
                -0.5f, 0.5f, 0f,
            ),
            floatArrayOf(
                0f, 0f, 1f,
                0f, 0f, 1f,
                0f, 0f, 1f,
                0f, 0f, 1f,
            ),
            floatArrayOf(
                // v=0 is the visual top so sourceRect can use DOM top directly.
                0f, 1f,
                1f, 1f,
                1f, 0f,
                0f, 0f,
            ),
            intArrayOf(
                Color.WHITE,
                Color.WHITE,
                Color.WHITE,
                Color.WHITE,
            ),
        )
        triMesh.updatePrimitives(0, intArrayOf(0, 1, 2, 0, 2, 3))
        return SceneMesh.fromTriangleMesh(triMesh, false)
    }
}
