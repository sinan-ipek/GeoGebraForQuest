package com.sinan.geogebraforquest

import android.graphics.Color
import android.util.Log
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
 * GeoGebraForQuest v0.9.9 late panel-mesh stereo renderer.
 *
 * Unlike v0.9.7.1/v0.9.8, this class does not create a child/overlay SceneObject.
 * It replaces the render mesh of the already-running real PanelSceneObject only
 * after the Spatial scene, VR panel, WebView texture and GeoGebra 3D layout are
 * all stable. The Android/WebView surface and the panel input target remain the
 * same object, so controller/ray interaction continues to hit GeoGebra.
 *
 * Ordinary GeoGebra UI is sampled mono. Only the measured 3D-canvas rectangle
 * is interpreted as a full-colour L|R SBS source. Eye selection is obtained in
 * the vertex shader and passed to the fragment shader.
 *
 * v0.9.9 intentionally ignores popup/settings occlusion masking. First we need
 * to prove that the real visible panel is definitely going through our stereo
 * material. A tiny diagnostic marker in the shader makes that unambiguous.
 */
class QuestStereoPanelRenderer(
    private val activity: AppSystemActivity,
    private val panelSceneObject: PanelSceneObject,
    panelTexture: SceneTexture,
    panelWidthMeters: Float,
    panelHeightMeters: Float,
) {
    companion object {
        private const val TAG = "GeoGebraForQuest"
    }

    private val material =
        SceneMaterial.custom(
            "questStereoPanel",
            arrayOf(
                SceneMaterialAttribute("stereoRect", SceneMaterialDataType.Vector4),
                SceneMaterialAttribute("albedoSampler", SceneMaterialDataType.Texture2D),
            ),
        ).apply {
            setAttribute("stereoRect", Vector4(0f, 0f, 0f, 0f))
            setTexture("albedoSampler", panelTexture)
            setUnlit(true)
        }

    @Volatile
    private var released = false

    init {
        // GGQ_PANEL_MESH_TAKEOVER
        // Important: SpatialGeoGebraActivity creates this renderer only after a
        // deliberate late-start delay. v0.9.7 changed the mesh during panel
        // setup and could crash the app before the panel was fully initialized.
        panelSceneObject.mesh =
            createPanelQuad(
                material = material,
                width = panelWidthMeters,
                height = panelHeightMeters,
            )
        Log.i(TAG, "v0.9.9 real PanelSceneObject mesh switched to stereo material")
    }

    /**
     * Convert the measured DOM rectangle of GeoGebra's 3D canvas to normalized
     * panel UVs. Occlusion data is deliberately ignored in this diagnostic build.
     */
    fun updateLayout(json: String) {
        if (released) return

        try {
            val data = JSONObject(json)
            val stereo = data.optJSONObject("stereo") ?: return
            val viewWidth = data.optDouble("viewWidth", Double.NaN)
            val viewHeight = data.optDouble("viewHeight", Double.NaN)

            if (
                !viewWidth.isFinite() ||
                !viewHeight.isFinite() ||
                viewWidth <= 0.0 ||
                viewHeight <= 0.0
            ) {
                return
            }

            val left = stereo.optDouble("left", Double.NaN)
            val top = stereo.optDouble("top", Double.NaN)
            val width = stereo.optDouble("width", Double.NaN)
            val height = stereo.optDouble("height", Double.NaN)

            if (
                !left.isFinite() ||
                !top.isFinite() ||
                !width.isFinite() ||
                !height.isFinite() ||
                width <= 0.0 ||
                height <= 0.0
            ) {
                return
            }

            val stereoRect =
                Vector4(
                    (left / viewWidth).toFloat(),
                    (top / viewHeight).toFloat(),
                    (width / viewWidth).toFloat(),
                    (height / viewHeight).toFloat(),
                )

            if (
                stereoRect.x < -0.01f ||
                stereoRect.y < -0.01f ||
                stereoRect.z <= 0f ||
                stereoRect.w <= 0f ||
                stereoRect.x + stereoRect.z > 1.01f ||
                stereoRect.y + stereoRect.w > 1.01f
            ) {
                Log.w(TAG, "Ignoring invalid stereoRect=$stereoRect")
                return
            }

            activity.runOnUiThread {
                if (!released) {
                    material.setAttribute("stereoRect", stereoRect)
                    Log.d(TAG, "v0.9.9 stereoRect=$stereoRect")
                }
            }
        } catch (error: Throwable) {
            Log.w(TAG, "Transient v0.9.9 stereo layout parse failure", error)
        }
    }

    fun release() {
        // The real PanelSceneObject is owned by Spatial's panel runtime. We do
        // not destroy it and we do not create any secondary input/render entity.
        released = true
    }

    private fun createPanelQuad(
        material: SceneMaterial,
        width: Float,
        height: Float,
    ): SceneMesh {
        val halfWidth = width / 2f
        val halfHeight = height / 2f

        // Both triangle windings are included. This removes back-face culling as
        // a variable while diagnosing the eye-routing path.
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
                // Keep the same orientation that the working panel renderers use.
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
