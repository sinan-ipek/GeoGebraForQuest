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
import com.meta.spatial.toolkit.SceneObjectSystem
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.Visible
import java.util.concurrent.CompletableFuture
import org.json.JSONObject

/**
 * Visual renderer for the one and only GeoGebra panel.
 *
 * The real LayoutXML panel remains the input surface. Its live SceneTexture is
 * sampled here without copying. Outside the 3D view the same mono UI pixels are
 * shown to both eyes. Inside the 3D view, the source-built GeoGebra canvas is an
 * SBS image and the shader selects the correct half for the current Quest eye.
 *
 * This entity deliberately has no Panel, Hittable or Grabbable component, so it
 * is not a second UI surface and cannot steal controller input from GeoGebra.
 */
class QuestStereoPanelRenderer(
    private val activity: AppSystemActivity,
    parent: Entity,
    panelTexture: SceneTexture,
    panelWidthMeters: Float,
    panelHeightMeters: Float,
) {
    companion object {
        private const val VISUAL_Z = -0.0015f
    }

    private val material =
        SceneMaterial.custom(
            "questStereoPanel",
            arrayOf(
                SceneMaterialAttribute("stereoRect", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion0", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion1", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion2", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion3", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("layoutInfo", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("albedoSampler", SceneMaterialDataType.Texture2D),
            ),
        ).apply {
            setAttribute("stereoRect", Vector4(0f, 0f, 0f, 0f))
            setAttribute("occlusion0", Vector4(0f))
            setAttribute("occlusion1", Vector4(0f))
            setAttribute("occlusion2", Vector4(0f))
            setAttribute("occlusion3", Vector4(0f))
            setAttribute("layoutInfo", Vector4(0f, 0f, 0f, 0f))
            setTexture("albedoSampler", panelTexture)
            setUnlit(true)
        }

    private val entity =
        Entity.create(
            TransformParent(parent),
            Transform(Pose(Vector3(0f, 0f, VISUAL_Z))),
            Visible(true),
        )

    private val sceneObject: SceneObject

    init {
        val mesh = createPanelQuad(material, panelWidthMeters, panelHeightMeters)
        sceneObject = SceneObject(activity.scene, mesh, "ggq-stereo-panel-visual", entity)
        activity.systemManager
            .findSystem<SceneObjectSystem>()
            .addSceneObject(
                entity,
                CompletableFuture<SceneObject>().apply { complete(sceneObject) },
            )
    }

    /**
     * Accept DOM coordinates in CSS pixels and convert them to panel-normalized
     * texture coordinates. Up to four intersecting popups/dialogs are forced to
     * mono so GeoGebra UI can safely cover the 3D view.
     */
    fun updateLayout(json: String) {
        try {
            val data = JSONObject(json)
            val stereo = data.optJSONObject("stereo") ?: return
            val viewWidth = data.optDouble("viewWidth", Double.NaN)
            val viewHeight = data.optDouble("viewHeight", Double.NaN)
            if (!viewWidth.isFinite() || !viewHeight.isFinite() || viewWidth <= 0.0 || viewHeight <= 0.0) {
                return
            }

            fun normalizedRect(rect: JSONObject?): Vector4 {
                if (rect == null) return Vector4(0f)
                val left = rect.optDouble("left", Double.NaN)
                val top = rect.optDouble("top", Double.NaN)
                val width = rect.optDouble("width", Double.NaN)
                val height = rect.optDouble("height", Double.NaN)
                if (!left.isFinite() || !top.isFinite() || !width.isFinite() || !height.isFinite()) {
                    return Vector4(0f)
                }
                return Vector4(
                    (left / viewWidth).toFloat(),
                    (top / viewHeight).toFloat(),
                    (width / viewWidth).toFloat(),
                    (height / viewHeight).toFloat(),
                )
            }

            val stereoRect = normalizedRect(stereo)
            if (stereoRect.z <= 0f || stereoRect.w <= 0f) return

            val occlusionArray = data.optJSONArray("occlusions")
            val occlusions = Array(4) { Vector4(0f) }
            val count = minOf(4, occlusionArray?.length() ?: 0)
            for (i in 0 until count) {
                occlusions[i] = normalizedRect(occlusionArray?.optJSONObject(i))
            }

            activity.runOnUiThread {
                material.setAttribute("stereoRect", stereoRect)
                material.setAttribute("occlusion0", occlusions[0])
                material.setAttribute("occlusion1", occlusions[1])
                material.setAttribute("occlusion2", occlusions[2])
                material.setAttribute("occlusion3", occlusions[3])
                material.setAttribute("layoutInfo", Vector4(count.toFloat(), 1f, 0f, 0f))
            }
        } catch (_: Throwable) {
            // A layout measurement can become stale while GeoGebra rearranges.
        }
    }

    fun release() {
        activity.runOnUiThread {
            entity.setComponent(Visible(false))
            entity.destroy()
        }
    }

    private fun createPanelQuad(
        material: SceneMaterial,
        width: Float,
        height: Float,
    ): SceneMesh {
        val halfWidth = width / 2f
        val halfHeight = height / 2f
        val triMesh = TriangleMesh(4, 6, intArrayOf(6), arrayOf(material))
        triMesh.updateGeometry(
            0,
            floatArrayOf(
                -halfWidth, -halfHeight, 0f,
                halfWidth, -halfHeight, 0f,
                halfWidth, halfHeight, 0f,
                -halfWidth, halfHeight, 0f,
            ),
            floatArrayOf(
                0f, 0f, 1f,
                0f, 0f, 1f,
                0f, 0f, 1f,
                0f, 0f, 1f,
            ),
            floatArrayOf(
                // v=0 is visual top, matching DOM getBoundingClientRect().
                0f, 1f,
                1f, 1f,
                1f, 0f,
                0f, 0f,
            ),
            intArrayOf(Color.WHITE, Color.WHITE, Color.WHITE, Color.WHITE),
        )
        triMesh.updatePrimitives(0, intArrayOf(0, 1, 2, 0, 2, 3))
        return SceneMesh.fromTriangleMesh(triMesh, false)
    }
}
