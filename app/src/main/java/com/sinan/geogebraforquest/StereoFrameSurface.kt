package com.sinan.geogebraforquest

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.opengl.GLES20
import android.opengl.GLUtils
import android.util.Base64
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.microedition.khronos.egl.EGL10
import javax.microedition.khronos.egl.EGL10.EGL_ALPHA_SIZE
import javax.microedition.khronos.egl.EGL10.EGL_BLUE_SIZE
import javax.microedition.khronos.egl.EGL10.EGL_DEFAULT_DISPLAY
import javax.microedition.khronos.egl.EGL10.EGL_DEPTH_SIZE
import javax.microedition.khronos.egl.EGL10.EGL_GREEN_SIZE
import javax.microedition.khronos.egl.EGL10.EGL_NONE
import javax.microedition.khronos.egl.EGL10.EGL_NO_CONTEXT
import javax.microedition.khronos.egl.EGL10.EGL_NO_DISPLAY
import javax.microedition.khronos.egl.EGL10.EGL_NO_SURFACE
import javax.microedition.khronos.egl.EGL10.EGL_RED_SIZE
import javax.microedition.khronos.egl.EGL10.EGL_RENDERABLE_TYPE
import javax.microedition.khronos.egl.EGL10.EGL_STENCIL_SIZE
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.egl.EGLContext
import javax.microedition.khronos.egl.EGLDisplay
import javax.microedition.khronos.egl.EGLSurface
import org.json.JSONObject

/**
 * v0.6.0 full-panel stereo compositor.
 *
 * JavaScript no longer sends an already-composited portal image. It sends only
 * the decoded SBS image of GeoGebra's 3D viewport. The Activity separately takes
 * one ordinary screenshot of the whole WebView panel. This class then builds:
 *
 *   LEFT EYE  = full GeoGebra UI + left 3D image
 *   RIGHT EYE = full GeoGebra UI + right 3D image
 *
 * and packs the two complete interface images side-by-side. Spatial SDK's
 * StereoMode.LeftRight performs the final eye selection.
 */
class StereoFrameSurface {

    companion object {
        const val EYE_WIDTH = 1080
        const val EYE_HEIGHT = 720
        const val SURFACE_WIDTH = EYE_WIDTH * 2
        const val SURFACE_HEIGHT = EYE_HEIGHT

        private const val EGL_CONTEXT_CLIENT_VERSION = 0x3098
        private const val EGL_OPENGL_ES2_BIT = 4
    }

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-FullPanelStereoSurface").apply { isDaemon = true }
    }
    private val framePending = AtomicBoolean(false)

    @Volatile
    private var targetSurface: Surface? = null

    private var egl: EGL10? = null
    private var eglDisplay: EGLDisplay = EGL_NO_DISPLAY
    private var eglContext: EGLContext = EGL_NO_CONTEXT
    private var eglSurface: EGLSurface = EGL_NO_SURFACE

    private var program = 0
    private var texture = 0
    private var positionLocation = -1
    private var uvLocation = -1
    private var textureLocation = -1

    private val vertexBuffer: FloatBuffer = ByteBuffer
        .allocateDirect(4 * 4 * java.lang.Float.BYTES)
        .order(ByteOrder.nativeOrder())
        .asFloatBuffer()
        .apply {
            put(
                floatArrayOf(
                    -1f, -1f, 0f, 1f,
                    1f, -1f, 1f, 1f,
                    -1f, 1f, 0f, 0f,
                    1f, 1f, 1f, 0f,
                ),
            )
            position(0)
        }

    fun attach(surface: Surface) {
        targetSurface = surface
        executor.execute {
            releaseEglInternal()
            if (surface.isValid && initEgl(surface)) {
                clearToBlack()
            }
        }
    }

    fun canAcceptFrame(): Boolean = !framePending.get()

    /**
     * Composes one complete left-eye GeoGebra panel and one complete right-eye
     * panel. [basePanel] is always recycled by this method once ownership is
     * accepted, even when decoding or EGL presentation fails.
     *
     * @return true if the frame was accepted for processing; false if another
     * frame is already in flight. When false, the caller still owns basePanel.
     */
    fun submitCompositeDataUrl(
        dataUrl: String,
        basePanel: Bitmap,
        portalRectJson: String?,
        onPresented: (() -> Unit)? = null,
        onFinished: (() -> Unit)? = null,
    ): Boolean {
        if (!framePending.compareAndSet(false, true)) {
            return false
        }

        executor.execute {
            var stereo3D: Bitmap? = null
            var fullSbs: Bitmap? = null
            try {
                stereo3D = decodeDataUrl(dataUrl) ?: return@execute
                fullSbs = composeFullPanel(basePanel, stereo3D, portalRectJson)

                val surface = targetSurface ?: return@execute
                if (!surface.isValid) return@execute
                if (eglSurface == EGL_NO_SURFACE && !initEgl(surface)) return@execute

                if (drawBitmap(fullSbs)) {
                    onPresented?.invoke()
                }
            } catch (_: Throwable) {
                // A transient WebView snapshot, JPEG, or EGL frame is disposable.
                // Never allow one bad frame to crash the Spatial activity.
            } finally {
                if (!basePanel.isRecycled) basePanel.recycle()
                stereo3D?.let { if (!it.isRecycled) it.recycle() }
                fullSbs?.let { if (!it.isRecycled) it.recycle() }
                framePending.set(false)
                onFinished?.invoke()
            }
        }

        return true
    }

    fun release() {
        targetSurface = null
        executor.execute {
            releaseEglInternal()
        }
        executor.shutdown()
    }

    private fun decodeDataUrl(dataUrl: String): Bitmap? {
        val comma = dataUrl.indexOf(',')
        if (comma < 0 || comma >= dataUrl.length - 1) return null
        val payload = dataUrl.substring(comma + 1)
        val bytes = Base64.decode(payload, Base64.DEFAULT)
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }

    private fun composeFullPanel(
        basePanel: Bitmap,
        stereo3D: Bitmap,
        portalRectJson: String?,
    ): Bitmap {
        val output = Bitmap.createBitmap(
            SURFACE_WIDTH,
            SURFACE_HEIGHT,
            Bitmap.Config.ARGB_8888,
        )
        val canvas = Canvas(output)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)

        val baseSource = Rect(0, 0, basePanel.width, basePanel.height)
        val leftEyePanel = Rect(0, 0, EYE_WIDTH, EYE_HEIGHT)
        val rightEyePanel = Rect(EYE_WIDTH, 0, SURFACE_WIDTH, EYE_HEIGHT)

        // The same ordinary GeoGebra UI is the base of both eye images.
        canvas.drawBitmap(basePanel, baseSource, leftEyePanel, paint)
        canvas.drawBitmap(basePanel, baseSource, rightEyePanel, paint)

        val destination = portalDestination(portalRectJson)
        if (destination != null && stereo3D.width >= 2 && stereo3D.height >= 1) {
            val half = stereo3D.width / 2
            if (half >= 1) {
                val leftSource = Rect(0, 0, half, stereo3D.height)
                val rightSource = Rect(half, 0, stereo3D.width, stereo3D.height)

                canvas.drawBitmap(
                    stereo3D,
                    leftSource,
                    destination,
                    paint,
                )

                val rightDestination = Rect(
                    destination.left + EYE_WIDTH,
                    destination.top,
                    destination.right + EYE_WIDTH,
                    destination.bottom,
                )
                canvas.drawBitmap(
                    stereo3D,
                    rightSource,
                    rightDestination,
                    paint,
                )
            }
        }

        return output
    }

    private fun portalDestination(json: String?): Rect? {
        if (json.isNullOrBlank()) return null

        return try {
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
            ) {
                return null
            }

            val x0 = (left / viewWidth * EYE_WIDTH).toInt()
            val y0 = (top / viewHeight * EYE_HEIGHT).toInt()
            val x1 = ((left + width) / viewWidth * EYE_WIDTH).toInt()
            val y1 = ((top + height) / viewHeight * EYE_HEIGHT).toInt()

            Rect(
                x0.coerceIn(0, EYE_WIDTH - 1),
                y0.coerceIn(0, EYE_HEIGHT - 1),
                x1.coerceIn(1, EYE_WIDTH),
                y1.coerceIn(1, EYE_HEIGHT),
            ).takeIf { it.width() > 0 && it.height() > 0 }
        } catch (_: Throwable) {
            null
        }
    }

    private fun initEgl(surface: Surface): Boolean {
        return try {
            val localEgl = EGLContext.getEGL() as EGL10
            val display = localEgl.eglGetDisplay(EGL_DEFAULT_DISPLAY)
            if (display == EGL_NO_DISPLAY) return false
            if (!localEgl.eglInitialize(display, IntArray(2))) return false

            val configs = arrayOfNulls<EGLConfig>(1)
            val count = IntArray(1)
            val configSpec = intArrayOf(
                EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                EGL_RED_SIZE, 8,
                EGL_GREEN_SIZE, 8,
                EGL_BLUE_SIZE, 8,
                EGL_ALPHA_SIZE, 8,
                EGL_DEPTH_SIZE, 0,
                EGL_STENCIL_SIZE, 0,
                EGL_NONE,
            )
            if (!localEgl.eglChooseConfig(display, configSpec, configs, 1, count)) return false
            val config = configs[0] ?: return false

            val context = localEgl.eglCreateContext(
                display,
                config,
                EGL_NO_CONTEXT,
                intArrayOf(EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE),
            )
            if (context == EGL_NO_CONTEXT) return false

            val windowSurface = localEgl.eglCreateWindowSurface(display, config, surface, null)
            if (windowSurface == EGL_NO_SURFACE) {
                localEgl.eglDestroyContext(display, context)
                return false
            }

            if (!localEgl.eglMakeCurrent(display, windowSurface, windowSurface, context)) {
                localEgl.eglDestroySurface(display, windowSurface)
                localEgl.eglDestroyContext(display, context)
                return false
            }

            egl = localEgl
            eglDisplay = display
            eglContext = context
            eglSurface = windowSurface
            createGlResources()
            true
        } catch (_: Throwable) {
            false
        }
    }

    private fun createGlResources() {
        val vertexShader = compileShader(
            GLES20.GL_VERTEX_SHADER,
            """
            attribute vec2 aPosition;
            attribute vec2 aUv;
            varying vec2 vUv;
            void main() {
                vUv = aUv;
                gl_Position = vec4(aPosition, 0.0, 1.0);
            }
            """.trimIndent(),
        )
        val fragmentShader = compileShader(
            GLES20.GL_FRAGMENT_SHADER,
            """
            precision mediump float;
            varying vec2 vUv;
            uniform sampler2D uTexture;
            void main() {
                gl_FragColor = texture2D(uTexture, vUv);
            }
            """.trimIndent(),
        )

        program = GLES20.glCreateProgram()
        GLES20.glAttachShader(program, vertexShader)
        GLES20.glAttachShader(program, fragmentShader)
        GLES20.glLinkProgram(program)
        GLES20.glDeleteShader(vertexShader)
        GLES20.glDeleteShader(fragmentShader)

        positionLocation = GLES20.glGetAttribLocation(program, "aPosition")
        uvLocation = GLES20.glGetAttribLocation(program, "aUv")
        textureLocation = GLES20.glGetUniformLocation(program, "uTexture")

        val textures = IntArray(1)
        GLES20.glGenTextures(1, textures, 0)
        texture = textures[0]
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texture)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, 0)
    }

    private fun compileShader(type: Int, source: String): Int {
        val shader = GLES20.glCreateShader(type)
        GLES20.glShaderSource(shader, source)
        GLES20.glCompileShader(shader)
        return shader
    }

    private fun clearToBlack() {
        val localEgl = egl ?: return
        if (eglSurface == EGL_NO_SURFACE) return
        GLES20.glViewport(0, 0, SURFACE_WIDTH, SURFACE_HEIGHT)
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        localEgl.eglSwapBuffers(eglDisplay, eglSurface)
    }

    private fun drawBitmap(bitmap: Bitmap): Boolean {
        val localEgl = egl ?: return false
        if (eglSurface == EGL_NO_SURFACE || program == 0 || texture == 0) return false

        GLES20.glViewport(0, 0, SURFACE_WIDTH, SURFACE_HEIGHT)
        GLES20.glDisable(GLES20.GL_DEPTH_TEST)
        GLES20.glDisable(GLES20.GL_BLEND)
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)

        GLES20.glUseProgram(program)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texture)
        GLUtils.texImage2D(GLES20.GL_TEXTURE_2D, 0, bitmap, 0)
        GLES20.glUniform1i(textureLocation, 0)

        vertexBuffer.position(0)
        GLES20.glEnableVertexAttribArray(positionLocation)
        GLES20.glVertexAttribPointer(
            positionLocation,
            2,
            GLES20.GL_FLOAT,
            false,
            4 * java.lang.Float.BYTES,
            vertexBuffer,
        )

        vertexBuffer.position(2)
        GLES20.glEnableVertexAttribArray(uvLocation)
        GLES20.glVertexAttribPointer(
            uvLocation,
            2,
            GLES20.GL_FLOAT,
            false,
            4 * java.lang.Float.BYTES,
            vertexBuffer,
        )

        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
        GLES20.glDisableVertexAttribArray(positionLocation)
        GLES20.glDisableVertexAttribArray(uvLocation)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, 0)

        return try {
            localEgl.eglSwapBuffers(eglDisplay, eglSurface)
        } catch (_: Throwable) {
            false
        }
    }

    private fun releaseEglInternal() {
        val localEgl = egl
        if (localEgl != null && eglDisplay != EGL_NO_DISPLAY) {
            try {
                localEgl.eglMakeCurrent(
                    eglDisplay,
                    EGL_NO_SURFACE,
                    EGL_NO_SURFACE,
                    EGL_NO_CONTEXT,
                )
            } catch (_: Throwable) {}

            try {
                if (eglSurface != EGL_NO_SURFACE) {
                    localEgl.eglDestroySurface(eglDisplay, eglSurface)
                }
            } catch (_: Throwable) {}

            try {
                if (eglContext != EGL_NO_CONTEXT) {
                    localEgl.eglDestroyContext(eglDisplay, eglContext)
                }
            } catch (_: Throwable) {}

            try {
                localEgl.eglTerminate(eglDisplay)
            } catch (_: Throwable) {}
        }

        egl = null
        eglDisplay = EGL_NO_DISPLAY
        eglContext = EGL_NO_CONTEXT
        eglSurface = EGL_NO_SURFACE
        program = 0
        texture = 0
        positionLocation = -1
        uvLocation = -1
        textureLocation = -1
    }
}
