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
 * Visual-only eye-aware portal for the source-rendered GeoGebra SBS canvas.
 *
 * The ordinary LayoutXML/WebView panel remains untouched and receives all input.
 * This child SceneObject has no Panel/Hittable/Grabbable component; it only
 * samples the already-existing WebView texture over the measured 3D rectangle.
 *
 * The current layout payload is produced by quest-stereo-layout.js:
 * {
 *   "stereo": { left, top, width, height },
 *   "viewWidth": ...,
 *   "viewHeight": ...,
 *   "occlusions": [...]
 * }
 *
 * If a popup/settings sheet overlaps the 3D rectangle, the portal is hidden so
 * the normal mono UI underneath remains readable and interactive.
 */
class QuestStereoPortalRenderer(
    private val activity: AppSystemActivity,
    parent: Entity,
    panelTexture: SceneTexture,
) {

    companion object {
        // Same small offset used by the earlier portal implementation. The
        // object is visually separated from the WebView while remaining a child
        // of the real panel entity.
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
            setUnlit(true)
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
    private var released = false

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
     * Update portal position/size and the source UV crop from the current DOM
     * measurement. Ordinary popups/settings hide the portal until they close.
     */
    fun updateLayout(
        json: String,
        panelWidthMeters: Float,
        panelHeightMeters: Float,
    ) {
        if (released) return

        try {
            val data = JSONObject(json)
            val stereo = data.optJSONObject("stereo") ?: return

            val left = stereo.optDouble("left", Double.NaN)
            val top = stereo.optDouble("top", Double.NaN)
            val width = stereo.optDouble("width", Double.NaN)
            val height = stereo.optDouble("height", Double.NaN)
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

            val sourceRect =
                Vector4(
                    (left / viewWidth).toFloat(),
                    (top / viewHeight).toFloat(),
                    (width / viewWidth).toFloat(),
                    (height / viewHeight).toFloat(),
                )

            val occlusions = data.optJSONArray("occlusions")
            val blocked = occlusions != null && occlusions.length() > 0

            activity.runOnUiThread {
                if (released) return@runOnUiThread

                material.setAttribute("sourceRect", sourceRect)
                entity.setComponent(
                    Transform(Pose(Vector3(centerX, centerY, PORTAL_Z))),
                )
                entity.setComponent(
                    Scale(Vector3(widthMeters, heightMeters, 1f)),
                )
                entity.setComponent(Visible(!blocked))
            }
        } catch (_: Throwable) {
            // DOM measurements can be transient while GeoGebra is relaying out.
            // The next layout event replaces this one.
        }
    }

    fun setVisible(visible: Boolean) {
        if (released) return
        activity.runOnUiThread {
            if (!released) entity.setComponent(Visible(visible))
        }
    }

    fun release() {
        if (released) return
        released = true

        activity.runOnUiThread {
            try {
                entity.setComponent(Visible(false))
                entity.destroy()
            } catch (_: Throwable) {
                // Runtime owns SceneObject shutdown; nothing else to release.
            }
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
                // Match the DOM convention used for sourceRect.
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
