package com.sinan.geogebraforquest

import android.graphics.BitmapFactory
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

/**
 * Draws GeoGebra's compressed SBS stereo frames directly into the Surface
 * supplied by Spatial SDK's VideoSurfacePanelRegistration.
 *
 * The Spatial panel is configured with StereoMode.LeftRight. Therefore this
 * class does not decide which eye sees which pixels: it simply paints a normal
 * 1280x480 SBS image (640x480 left eye + 640x480 right eye). Meta's compositor
 * performs the per-eye selection.
 *
 * v0.5.1 reports presentation only after eglSwapBuffers() succeeds. The parent
 * Activity keeps the stereo portal hidden until that callback, so a missing
 * GeoGebra eye frame can never replace the working 3D view with a black panel.
 */
class StereoFrameSurface {

    companion object {
        const val EYE_WIDTH = 640
        const val EYE_HEIGHT = 480
        const val SURFACE_WIDTH = EYE_WIDTH * 2
        const val SURFACE_HEIGHT = EYE_HEIGHT

        private const val EGL_CONTEXT_CLIENT_VERSION = 0x3098
        private const val EGL_OPENGL_ES2_BIT = 4
    }

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "GGQ-StereoSurface").apply { isDaemon = true }
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
            // x, y, u, v. Android Bitmap rows are top-down, so V is flipped.
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

    fun submitDataUrl(
        dataUrl: String,
        onPresented: (() -> Unit)? = null,
    ) {
        if (!framePending.compareAndSet(false, true)) {
            // Real-time rule: keep latency low by dropping a frame rather than
            // queueing old frames behind the one currently being decoded.
            return
        }

        executor.execute {
            try {
                val comma = dataUrl.indexOf(',')
                if (comma < 0 || comma >= dataUrl.length - 1) return@execute
                val payload = dataUrl.substring(comma + 1)
                val bytes = Base64.decode(payload, Base64.DEFAULT)
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@execute
                try {
                    val surface = targetSurface ?: return@execute
                    if (!surface.isValid) return@execute
                    if (eglSurface == EGL_NO_SURFACE && !initEgl(surface)) return@execute
                    if (drawBitmap(bitmap)) {
                        onPresented?.invoke()
                    }
                } finally {
                    bitmap.recycle()
                }
            } catch (_: Throwable) {
                // A bad/transient frame is disposable. Never crash the Spatial
                // activity because one WebGL capture or JPEG decode failed.
            } finally {
                framePending.set(false)
            }
        }
    }

    fun release() {
        targetSurface = null
        executor.execute {
            releaseEglInternal()
        }
        executor.shutdown()
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

    private fun drawBitmap(bitmap: android.graphics.Bitmap): Boolean {
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
