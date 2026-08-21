package com.sinan.geogebraforquest

import android.graphics.Color
import com.meta.spatial.core.Vector4
import com.meta.spatial.runtime.PanelSceneObject
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneMaterialAttribute
import com.meta.spatial.runtime.SceneMaterialDataType
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.runtime.SceneTexture
import com.meta.spatial.runtime.TriangleMesh
import com.meta.spatial.toolkit.AppSystemActivity
import org.json.JSONObject

/**
 * Eye-aware material installed directly on GeoGebra's real PanelSceneObject.
 *
 * There is no second panel, no front overlay and no second hit surface. The
 * LayoutXML panel remains the sole visual object and the sole input target.
 * Its live WebView texture is sampled normally for all 2D UI; only the source
 * rectangle occupied by the GeoGebra 3D canvas is interpreted as L|R SBS.
 */
class QuestStereoPanelRenderer(
    private val activity: AppSystemActivity,
    private val panelSceneObject: PanelSceneObject,
    panelTexture: SceneTexture,
    panelWidthMeters: Float,
    panelHeightMeters: Float,
) {
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

    init {
        // Replace only the render mesh of the *same* PanelSceneObject. The
        // PanelSceneObject itself, its Android surface and its input mapping are
        // unchanged, so controller/ray events still go to the GeoGebra WebView.
        panelSceneObject.mesh = createPanelQuad(material, panelWidthMeters, panelHeightMeters)
    }

    /**
     * Convert the measured DOM rectangle of the 3D canvas to panel-normalized
     * UVs. Popup/dialog overlaps stay mono so ordinary GeoGebra UI remains
     * readable in both eyes.
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
            // Layout can change while the DOM is being measured; the next event
            // will supply a fresh rectangle.
        }
    }

    fun release() {
        // The PanelSceneObject is owned by the panel registration/runtime.
        // Nothing separate was created, so there is no overlay entity to destroy.
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
                // Match Android/DOM orientation: top-left=(0,0).
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
