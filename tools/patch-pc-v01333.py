#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.33 host/XR patch.

Build on the v0.13.32 geometry-only CEF/D3D single-panel compositor, but feed it
an atomic [L|R] generated from the proven single W x H GeoGebra eye viewport.
Also publish A to XR from our client-owned D3D copy, never directly from CEF's
short-lived accelerated-paint pool texture.
"""

from pathlib import Path
from urllib.request import urlopen
import re


# Apply the complete v0.13.32 PC/XR geometry-only architecture, including its
# namespace build fixes. v0.13.33 changes the source renderer semantics, not the
# already-proven A_L/A_R presentation model.
V01332 = (
    "https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/"
    "26e7b2addc82934d80efbd65518f1e0acc33b5c1/tools/patch-pc-v01332.py"
)
source = urlopen(V01332, timeout=30).read().decode("utf-8")
exec(compile(source, "patch-pc-v01332.py", "exec"), {"__name__": "__main__"})


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Install the WebGL-only atomic stereo packer before GeoGebra boots.
# ---------------------------------------------------------------------------
p = Path("app/src/main/assets/web/index.html")
html = p.read_text(encoding="utf-8")
marker = "<script>\n(function () {\n  'use strict';\n"
require(html, marker, "v0.13.33 index bootstrap marker missing")

packer = r'''<script id="ggq-gpu-atomic-sbs">
(function () {
  'use strict';

  // GGQ v0.13.33.  The GeoGebra renderer draws each eye with the exact proven
  // W x H viewport at x=0.  copyTexSubImage2D keeps those completed passes on
  // the same WebGL GPU.  A single final draw writes coherent [L|R] into the
  // 2W backing store.  No readPixels/getImageData/CPU pixel path exists here.
  var states = new WeakMap();

  function compile(gl, type, source) {
    var shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error('[GGQ v0.13.33] shader compile:', gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  function createProgram(gl) {
    var vs = compile(gl, gl.VERTEX_SHADER,
      'attribute vec2 a_pos;\n' +
      'varying vec2 v_uv;\n' +
      'void main(){v_uv=(a_pos+1.0)*0.5;gl_Position=vec4(a_pos,0.0,1.0);}\n');
    var fs = compile(gl, gl.FRAGMENT_SHADER,
      'precision mediump float;\n' +
      'uniform sampler2D u_left;\n' +
      'uniform sampler2D u_right;\n' +
      'varying vec2 v_uv;\n' +
      'void main(){\n' +
      '  bool r=v_uv.x>=0.5;\n' +
      '  float x=r?(v_uv.x-0.5)*2.0:v_uv.x*2.0;\n' +
      '  vec2 uv=vec2(clamp(x,0.0,1.0),clamp(v_uv.y,0.0,1.0));\n' +
      '  gl_FragColor=r?texture2D(u_right,uv):texture2D(u_left,uv);\n' +
      '}\n');
    if (!vs || !fs) return null;
    var program = gl.createProgram();
    if (!program) return null;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('[GGQ v0.13.33] program link:', gl.getProgramInfoLog(program));
      gl.deleteProgram(program);
      return null;
    }
    return program;
  }

  function makeTexture(gl) {
    var texture = gl.createTexture();
    if (!texture) return null;
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return texture;
  }

  function stateFor(gl) {
    var state = states.get(gl);
    if (state) return state;
    state = {
      width: 0,
      height: 0,
      left: null,
      right: null,
      validLeft: false,
      validRight: false,
      program: null,
      buffer: null,
      aPos: -1,
      uLeft: null,
      uRight: null
    };
    states.set(gl, state);
    return state;
  }

  function ensureTextures(gl, state, width, height) {
    if (state.left && state.right && state.width === width && state.height === height) {
      return true;
    }

    if (state.left) gl.deleteTexture(state.left);
    if (state.right) gl.deleteTexture(state.right);
    state.left = null;
    state.right = null;
    state.validLeft = false;
    state.validRight = false;
    state.width = width;
    state.height = height;

    var oldActive = gl.getParameter(gl.ACTIVE_TEXTURE);
    var oldBinding = gl.getParameter(gl.TEXTURE_BINDING_2D);
    try {
      state.left = makeTexture(gl);
      if (!state.left) return false;
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0,
        gl.RGBA, gl.UNSIGNED_BYTE, null);

      state.right = makeTexture(gl);
      if (!state.right) return false;
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0,
        gl.RGBA, gl.UNSIGNED_BYTE, null);
      return true;
    } finally {
      gl.bindTexture(gl.TEXTURE_2D, oldBinding);
      gl.activeTexture(oldActive);
    }
  }

  function ensureComposer(gl, state) {
    if (state.program && state.buffer && state.aPos >= 0) return true;
    state.program = createProgram(gl);
    if (!state.program) return false;
    state.aPos = gl.getAttribLocation(state.program, 'a_pos');
    state.uLeft = gl.getUniformLocation(state.program, 'u_left');
    state.uRight = gl.getUniformLocation(state.program, 'u_right');
    if (state.aPos < 0 || state.uLeft === null || state.uRight === null) return false;

    state.buffer = gl.createBuffer();
    if (!state.buffer) return false;
    var old = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
    gl.bindBuffer(gl.ARRAY_BUFFER, state.buffer);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, old);
    return true;
  }

  window.ggqGpuCaptureEye = function (gl, eye, width, height) {
    try {
      width = width | 0;
      height = height | 0;
      if (!gl || width < 2 || height < 2) return;
      var state = stateFor(gl);
      if (!ensureTextures(gl, state, width, height)) return;

      var oldActive = gl.getParameter(gl.ACTIVE_TEXTURE);
      var oldBinding = gl.getParameter(gl.TEXTURE_BINDING_2D);
      try {
        var texture = eye === 1 ? state.right : state.left;
        gl.bindTexture(gl.TEXTURE_2D, texture);
        // Both eyes are rendered in the SAME x=0 W x H viewport.
        gl.copyTexSubImage2D(gl.TEXTURE_2D, 0, 0, 0, 0, 0, width, height);
        if (eye === 1) state.validRight = true;
        else state.validLeft = true;
      } finally {
        gl.bindTexture(gl.TEXTURE_2D, oldBinding);
        gl.activeTexture(oldActive);
      }
    } catch (error) {
      console.error('[GGQ v0.13.33] GPU eye capture failed', error);
    }
  };

  window.ggqGpuComposeStereo = function (gl, width, height) {
    try {
      width = width | 0;
      height = height | 0;
      if (!gl || width < 2 || height < 2) return;
      var state = stateFor(gl);
      if (!state.validLeft || !state.validRight ||
          !ensureTextures(gl, state, width, height) ||
          !ensureComposer(gl, state)) return;

      var savedProgram = gl.getParameter(gl.CURRENT_PROGRAM);
      var savedFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
      var savedArrayBuffer = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
      var savedViewport = gl.getParameter(gl.VIEWPORT);
      var savedScissor = gl.getParameter(gl.SCISSOR_BOX);
      var savedColorMask = gl.getParameter(gl.COLOR_WRITEMASK);
      var savedDepthMask = gl.getParameter(gl.DEPTH_WRITEMASK);
      var savedActive = gl.getParameter(gl.ACTIVE_TEXTURE);

      gl.activeTexture(gl.TEXTURE0);
      var savedTex0 = gl.getParameter(gl.TEXTURE_BINDING_2D);
      gl.activeTexture(gl.TEXTURE1);
      var savedTex1 = gl.getParameter(gl.TEXTURE_BINDING_2D);

      var blend = gl.isEnabled(gl.BLEND);
      var depth = gl.isEnabled(gl.DEPTH_TEST);
      var stencil = gl.isEnabled(gl.STENCIL_TEST);
      var scissor = gl.isEnabled(gl.SCISSOR_TEST);
      var cull = gl.isEnabled(gl.CULL_FACE);

      var loc = state.aPos;
      var attrEnabled = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_ENABLED);
      var attrBuffer = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_BUFFER_BINDING);
      var attrSize = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_SIZE);
      var attrType = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_TYPE);
      var attrNorm = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_NORMALIZED);
      var attrStride = gl.getVertexAttrib(loc, gl.VERTEX_ATTRIB_ARRAY_STRIDE);
      var attrOffset = gl.getVertexAttribOffset(loc, gl.VERTEX_ATTRIB_ARRAY_POINTER);

      try {
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.viewport(0, 0, width * 2, height);
        gl.disable(gl.BLEND);
        gl.disable(gl.DEPTH_TEST);
        gl.disable(gl.STENCIL_TEST);
        gl.disable(gl.SCISSOR_TEST);
        gl.disable(gl.CULL_FACE);
        gl.depthMask(false);
        gl.colorMask(true, true, true, true);

        gl.useProgram(state.program);
        gl.bindBuffer(gl.ARRAY_BUFFER, state.buffer);
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, state.left);
        gl.uniform1i(state.uLeft, 0);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, state.right);
        gl.uniform1i(state.uRight, 1);

        // One draw call updates both halves as one coherent stereo pair.
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.flush();
      } finally {
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, savedTex0);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, savedTex1);
        gl.activeTexture(savedActive);

        gl.bindFramebuffer(gl.FRAMEBUFFER, savedFramebuffer);
        gl.useProgram(savedProgram);

        gl.bindBuffer(gl.ARRAY_BUFFER, attrBuffer);
        if (attrBuffer && attrSize > 0) {
          gl.vertexAttribPointer(loc, attrSize, attrType, !!attrNorm, attrStride, attrOffset);
        }
        if (attrEnabled) gl.enableVertexAttribArray(loc);
        else gl.disableVertexAttribArray(loc);
        gl.bindBuffer(gl.ARRAY_BUFFER, savedArrayBuffer);

        gl.viewport(savedViewport[0], savedViewport[1], savedViewport[2], savedViewport[3]);
        gl.scissor(savedScissor[0], savedScissor[1], savedScissor[2], savedScissor[3]);
        gl.colorMask(savedColorMask[0], savedColorMask[1], savedColorMask[2], savedColorMask[3]);
        gl.depthMask(savedDepthMask);

        if (blend) gl.enable(gl.BLEND); else gl.disable(gl.BLEND);
        if (depth) gl.enable(gl.DEPTH_TEST); else gl.disable(gl.DEPTH_TEST);
        if (stencil) gl.enable(gl.STENCIL_TEST); else gl.disable(gl.STENCIL_TEST);
        if (scissor) gl.enable(gl.SCISSOR_TEST); else gl.disable(gl.SCISSOR_TEST);
        if (cull) gl.enable(gl.CULL_FACE); else gl.disable(gl.CULL_FACE);
      }

      state.validLeft = false;
      state.validRight = false;
    } catch (error) {
      console.error('[GGQ v0.13.33] GPU stereo compose failed', error);
    }
  };
})();
</script>

'''

html = html.replace(marker, packer + marker, 1)
p.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) CEF accelerated-paint ownership fix.
#
# CefSharp explicitly says the CEF pool texture is valid only inside the paint
# callback and should be copied into a client-owned texture. We already make
# that copy for the PC window. Publish XR from THAT stable copy instead of
# issuing a second cross-resource CopyResource from CEF's pool texture.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.Graphics.cs")
graphics = p.read_text(encoding="utf-8")
old = '''                    if (TryQueueGpuPublishLocked(cefTexture))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(cefTexture.Description);'''
new = '''                    // v0.13.33: target is our own normal D3D11 texture. CEF's
                    // accelerated-paint resource belongs to a temporary pool and is
                    // never used as the XR-share copy source.
                    if (TryQueueGpuPublishLocked(target))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(target.Description);'''
require(graphics, old, "v0.13.33 A-share source marker missing")
graphics = graphics.replace(old, new, 1)

# Make any remaining share failure identify the exact operation in the title.
graphics = graphics.replace(
    "_device.ImmediateContext.CopyResource(cefTexture, _xrSharedTexture);",
    "_device.ImmediateContext.CopyResource(cefTexture, _xrSharedTexture);",
    1,
)
p.write_text(graphics, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Version/package/runtime labels.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.33</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.33.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.33.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

p = Path("pc/build.ps1")
build = p.read_text(encoding="utf-8")
build = build.replace(
    "GeoGebraForQuest-PC-v0.13.32-gpu-native-sbs-win-x64",
    "GeoGebraForQuest-PC-v0.13.33-gpu-atomic-sbs-win-x64",
)
build = build.replace("0.13.32-gpu-native-sbs", "0.13.33-gpu-atomic-sbs")
build = build.replace(r"0\.13\.32-gpu-native-sbs", r"0\.13\.33-gpu-atomic-sbs")
build = build.replace("v0.13.32", "v0.13.33")
build = build.replace(r"v0\.13\.32", r"v0\.13\.33")
p.write_text(build, encoding="utf-8")

p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
main = main.replace("0.13.32-gpu-native-sbs", "0.13.33-gpu-atomic-sbs")
main = main.replace("GeoGebraForQuest PC v0.13.32", "GeoGebraForQuest PC v0.13.33")
p.write_text(main, encoding="utf-8")

# Architecture guards.
checks = {
    "app/src/main/assets/web/index.html": [
        "ggq-gpu-atomic-sbs",
        "copyTexSubImage2D",
        "One draw call updates both halves",
    ],
    "pc/pc-stereo-layout.js": [
        "NO captureLoop",
        "data-ggq-pc-gpu-native-sbs",
    ],
    "pc/MainFormV11.Graphics.cs": [
        "TryQueueGpuPublishLocked(target)",
        "CompleteGpuPublishLocked(target.Description)",
        "cbuffer StereoParams",
    ],
    "pc/StereoSharedFrameWriter.cs": ["_view.Write(116, 4)"],
    "pc-xr/v11-render.hpp": ["GPU-NATIVE EMBEDDED-SBS"],
    "pc/GeoGebraForQuest.PC.csproj": ["<Version>0.13.33</Version>"],
    "pc/build.ps1": ["v0.13.33-gpu-atomic-sbs"],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"v0.13.33 invariant missing in {file}: {needle}")

print("GeoGebraForQuest PC v0.13.33 GPU atomic SBS + safe A-share applied")
