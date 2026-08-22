package com.sinan.geogebraforquest

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.AlphaMode
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.runtime.SceneObject
import com.meta.spatial.runtime.SceneTexture
import com.meta.spatial.runtime.StereoMode
import com.meta.spatial.runtime.TriangleMesh
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.SceneObjectSystem
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import java.util.concurrent.CompletableFuture

/**
 * v0.9.10 diagnostic surface that uses Meta Spatial SDK's official stereo path.
 *
 * The source texture is intentionally synthetic and completely independent of
 * GeoGebra/WebView: the left half is red and says L, the right half is blue and
 * says R. SceneMaterial.setStereoMode(StereoMode.LeftRight) must therefore make
 * the left Quest eye see only L and the right Quest eye see only R.
 *
 * This isolates the Quest/Spatial stereo compositor from every GeoGebra,
 * WebView, DOM-layout, popup and custom-shader variable.
 */
class OfficialStereoProbeRenderer(
    private val activity: AppSystemActivity,
) {
    companion object {
        private const val TEXTURE_WIDTH = 1024
        private const val TEXTURE_HEIGHT = 512
        private const val PROBE_WIDTH_METERS = 0.58f
        private const val PROBE_HEIGHT_METERS = 0.34f
    }

    private val entity =
        Entity.create(
            Transform(Pose(Vector3(0.95f, 1.18f, 1.05f))),
            Visible(true),
        )

    private val sceneObject: SceneObject

    @Volatile
    private var released = false

    init {
        val bitmap = createProbeBitmap()
        val drawable = BitmapDrawable(activity.resources, bitmap)
        val texture = SceneTexture(drawable)

        val material =
            SceneMaterial(
                texture,
                AlphaMode.OPAQUE,
                SceneMaterial.UNLIT_SHADER,
            ).apply {
                setStereoMode(StereoMode.LeftRight)
                setUnlit(true)
            }

        val mesh = createQuad(material)
        sceneObject = SceneObject(activity.scene, mesh, "ggq-official-stereo-probe", entity)

        activity.systemManager
            .findSystem<SceneObjectSystem>()
            .addSceneObject(
                entity,
                CompletableFuture<SceneObject>().apply { complete(sceneObject) },
            )
    }

    fun release() {
        if (released) return
        released = true
        activity.runOnUiThread {
            try {
                entity.setComponent(Visible(false))
                entity.destroy()
            } catch (_: Throwable) {
                // Spatial runtime owns final SceneObject teardown.
            }
        }
    }

    private fun createProbeBitmap(): Bitmap {
        val bitmap = Bitmap.createBitmap(TEXTURE_WIDTH, TEXTURE_HEIGHT, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)

        val fill = Paint(Paint.ANTI_ALIAS_FLAG)
        fill.color = Color.rgb(190, 35, 35)
        canvas.drawRect(0f, 0f, TEXTURE_WIDTH / 2f, TEXTURE_HEIGHT.toFloat(), fill)

        fill.color = Color.rgb(35, 80, 200)
        canvas.drawRect(TEXTURE_WIDTH / 2f, 0f, TEXTURE_WIDTH.toFloat(), TEXTURE_HEIGHT.toFloat(), fill)

        val separator = Paint(Paint.ANTI_ALIAS_FLAG)
        separator.color = Color.WHITE
        separator.strokeWidth = 8f
        canvas.drawLine(
            TEXTURE_WIDTH / 2f,
            0f,
            TEXTURE_WIDTH / 2f,
            TEXTURE_HEIGHT.toFloat(),
            separator,
        )

        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textAlign = Paint.Align.CENTER
            textSize = 260f
            typeface = Typeface.DEFAULT_BOLD
        }
        val baseline = TEXTURE_HEIGHT / 2f - (text.ascent() + text.descent()) / 2f
        canvas.drawText("L", TEXTURE_WIDTH * 0.25f, baseline, text)
        canvas.drawText("R", TEXTURE_WIDTH * 0.75f, baseline, text)

        val caption = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textAlign = Paint.Align.CENTER
            textSize = 44f
            typeface = Typeface.DEFAULT_BOLD
        }
        canvas.drawText("LEFT", TEXTURE_WIDTH * 0.25f, TEXTURE_HEIGHT - 45f, caption)
        canvas.drawText("RIGHT", TEXTURE_WIDTH * 0.75f, TEXTURE_HEIGHT - 45f, caption)

        return bitmap
    }

    private fun createQuad(material: SceneMaterial): SceneMesh {
        val halfWidth = PROBE_WIDTH_METERS / 2f
        val halfHeight = PROBE_HEIGHT_METERS / 2f

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

        // Both windings: the diagnostic must not disappear due to culling.
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
