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
 * v0.9.8 changes two important details:
 * - eye selection is done in the vertex shader, matching Meta's own stereo
 *   shader pattern, instead of querying the stereo pass from the fragment stage;
 * - popup/settings rectangles punch holes only where they overlap the 3D view.
 *   The complete portal is never hidden, so raw L|R SBS can no longer suddenly
 *   become visible across the whole 3D canvas when a GeoGebra popup is opened.
 *
 * The ordinary LayoutXML/WebView panel remains untouched and receives all input.
 */
class QuestStereoPortalRenderer(
    private val activity: AppSystemActivity,
    parent: Entity,
    panelTexture: SceneTexture,
) {

    companion object {
        // The panel entity is in front of the viewer at positive world Z. A
        // small negative local Z offset moves this child toward the viewer.
        private const val PORTAL_Z = -0.006f
        private const val MAX_OCCLUSIONS = 4
    }

    private val noOcclusion = Vector4(-2f, -2f, 0f, 0f)

    private val material =
        SceneMaterial.custom(
            "questStereoPortal",
            arrayOf(
                SceneMaterialAttribute("sourceRect", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion0", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion1", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion2", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("occlusion3", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("albedoSampler", SceneMaterialDataType.Texture2D),
            ),
        ).apply {
            setAttribute("sourceRect", Vector4(0f, 0f, 1f, 1f))
            setAttribute("occlusion0", noOcclusion)
            setAttribute("occlusion1", noOcclusion)
            setAttribute("occlusion2", noOcclusion)
            setAttribute("occlusion3", noOcclusion)
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
     * Updates portal position/size, source UV crop and up to four popup holes.
     * The portal remains visible while a popup is open; only the overlapped
     * pixels are discarded so the ordinary interactive WebView can show through.
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

            val popupRects = Array(MAX_OCCLUSIONS) { noOcclusion }
            val occlusions = data.optJSONArray("occlusions")
            if (occlusions != null) {
                val count = minOf(MAX_OCCLUSIONS, occlusions.length())
                for (i in 0 until count) {
                    val rect = occlusions.optJSONObject(i) ?: continue
                    val rectLeft = rect.optDouble("left", Double.NaN)
                    val rectTop = rect.optDouble("top", Double.NaN)
                    val rectWidth = rect.optDouble("width", Double.NaN)
                    val rectHeight = rect.optDouble("height", Double.NaN)

                    if (
                        !rectLeft.isFinite() || !rectTop.isFinite() ||
                        !rectWidth.isFinite() || !rectHeight.isFinite() ||
                        rectWidth <= 0.0 || rectHeight <= 0.0
                    ) continue

                    // Convert from WebView pixels into portal-local UV space.
                    // quest-stereo-layout.js already clips each rectangle to the
                    // 3D canvas, so these values normally lie within 0..1.
                    popupRects[i] =
                        Vector4(
                            ((rectLeft - left) / width).toFloat(),
                            ((rectTop - top) / height).toFloat(),
                            (rectWidth / width).toFloat(),
                            (rectHeight / height).toFloat(),
                        )
                }
            }

            activity.runOnUiThread {
                if (released) return@runOnUiThread

                material.setAttribute("sourceRect", sourceRect)
                material.setAttribute("occlusion0", popupRects[0])
                material.setAttribute("occlusion1", popupRects[1])
                material.setAttribute("occlusion2", popupRects[2])
                material.setAttribute("occlusion3", popupRects[3])

                entity.setComponent(
                    Transform(Pose(Vector3(centerX, centerY, PORTAL_Z))),
                )
                entity.setComponent(
                    Scale(Vector3(widthMeters, heightMeters, 1f)),
                )
                entity.setComponent(Visible(true))
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
        // Both windings are supplied, exactly as Meta's own SpatialVideoSample
        // does for its front video quad. This avoids the portal disappearing due
        // to back-face culling when attached to a panel-facing coordinate system.
        val triMesh =
            TriangleMesh(
                4,
                12,
                intArrayOf(12),
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
                // DOM convention: v=0 is the top of the WebView.
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

        triMesh.updatePrimitives(
            0,
            intArrayOf(
                0, 1, 2,
                0, 2, 3,
                0, 2, 1,
                0, 3, 2,
            ),
        )
        return SceneMesh.fromTriangleMesh(triMesh, false)
    }
}
