#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.34 host/XR patch.

Starts from the v0.13.32 geometry-only single-panel GPU compositor, but replaces
its source-side stereo implementation with v0.13.34 FBO rendering. It also
replaces the fragile D3D CopyResource A->XR publication with a shader blit into
a client-owned BGRA8 keyed-mutex shared texture, so CEF texture descriptor
quirks cannot trigger DXGI_ERROR_INVALID_CALL.
"""

from pathlib import Path
from urllib.request import urlopen
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# Apply the complete v0.13.32 host/XR embedded-SBS compositor. Its source-side
# renderer is NOT used here; only the geometry metadata + PC/XR split shaders.
V01332 = (
    "https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/"
    "26e7b2addc82934d80efbd65518f1e0acc33b5c1/tools/patch-pc-v01332.py"
)
source = urlopen(V01332, timeout=30).read().decode("utf-8")
exec(compile(source, "patch-pc-v01332.py", "exec"), {"__name__": "__main__"})


# ---------------------------------------------------------------------------
# 1) WebGL FBO stereo compositor. The two eye textures are actual render
#    targets, not framebuffer readbacks/copies.
# ---------------------------------------------------------------------------
p = Path("app/src/main/assets/web/index.html")
html = p.read_text(encoding="utf-8")
marker = "<script>\n(function () {\n  'use strict';\n"
require(html, marker, "v0.13.34 index bootstrap marker missing")

packer = r'''<script id="ggq-gpu-fbo-sbs">
(function () {
  'use strict';

  var states = new WeakMap();
  var lastError = '';

  function report(message) {
    message = String(message || 'unknown GPU FBO error');
    if (message === lastError) return;
    lastError = message;
    console.error('[GGQ v0.13.34]', message);
    try {
      if (window.QuestBridge && typeof window.QuestBridge.runtimeError === 'function') {
        window.QuestBridge.runtimeError('GPU FBO: ' + message);
      }
    } catch (_) {}
  }

  function compile(gl, type, source) {
    var shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      report('shader compile: ' + gl.getShaderInfoLog(shader));
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
      report('program link: ' + gl.getProgramInfoLog(program));
      gl.deleteProgram(program);
      return null;
    }
    return program;
  }

  function deleteEye(gl, eye) {
    if (!eye) return;
    try { if (eye.framebuffer) gl.deleteFramebuffer(eye.framebuffer); } catch (_) {}
    try { if (eye.depth) gl.deleteRenderbuffer(eye.depth); } catch (_) {}
    try { if (eye.texture) gl.deleteTexture(eye.texture); } catch (_) {}
  }

  function createEye(gl, width, height) {
    var texture = gl.createTexture();
    var framebuffer = gl.createFramebuffer();
    var depth = gl.createRenderbuffer();
    if (!texture || !framebuffer || !depth) {
      report('resource allocation failed');
      return null;
    }

    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0,
      gl.RGBA, gl.UNSIGNED_BYTE, null);

    gl.bindRenderbuffer(gl.RENDERBUFFER, depth);
    gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, width, height);

    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0,
      gl.TEXTURE_2D, texture, 0);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT,
      gl.RENDERBUFFER, depth);

    var status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
    if (status !== gl.FRAMEBUFFER_COMPLETE) {
      report('framebuffer incomplete: 0x' + Number(status).toString(16));
      deleteEye(gl, { texture:texture, framebuffer:framebuffer, depth:depth });
      return null;
    }

    return { texture:texture, framebuffer:framebuffer, depth:depth };
  }

  function stateFor(gl) {
    var state = states.get(gl);
    if (state) return state;
    state = {
      width:0,
      height:0,
      left:null,
      right:null,
      program:null,
      buffer:null,
      aPos:-1,
      uLeft:null,
      uRight:null
    };
    states.set(gl, state);
    return state;
  }

  function ensureEyes(gl, state, width, height) {
    if (state.left && state.right && state.width === width && state.height === height) {
      return true;
    }

    var savedFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    var savedRenderbuffer = gl.getParameter(gl.RENDERBUFFER_BINDING);
    var savedActive = gl.getParameter(gl.ACTIVE_TEXTURE);
    var savedTexture = gl.getParameter(gl.TEXTURE_BINDING_2D);

    try {
      deleteEye(gl, state.left);
      deleteEye(gl, state.right);
      state.left = null;
      state.right = null;
      state.width = width;
      state.height = height;

      state.left = createEye(gl, width, height);
      state.right = createEye(gl, width, height);
      return !!(state.left && state.right);
    } finally {
      gl.bindFramebuffer(gl.FRAMEBUFFER, savedFramebuffer);
      gl.bindRenderbuffer(gl.RENDERBUFFER, savedRenderbuffer);
      gl.bindTexture(gl.TEXTURE_2D, savedTexture);
      gl.activeTexture(savedActive);
    }
  }

  function ensureComposer(gl, state) {
    if (state.program && state.buffer && state.aPos >= 0) return true;
    state.program = createProgram(gl);
    if (!state.program) return false;
    state.aPos = gl.getAttribLocation(state.program, 'a_pos');
    state.uLeft = gl.getUniformLocation(state.program, 'u_left');
    state.uRight = gl.getUniformLocation(state.program, 'u_right');
    if (state.aPos < 0 || state.uLeft === null || state.uRight === null) {
      report('composer locations missing');
      return false;
    }
    state.buffer = gl.createBuffer();
    if (!state.buffer) return false;
    var saved = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
    gl.bindBuffer(gl.ARRAY_BUFFER, state.buffer);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, saved);
    return true;
  }

  window.ggqGpuBindEyeFramebuffer = function (gl, eye, width, height) {
    try {
      width = width | 0;
      height = height | 0;
      if (!gl || width < 2 || height < 2) return;
      var state = stateFor(gl);
      if (!ensureEyes(gl, state, width, height)) return;
      var target = eye === 1 ? state.right : state.left;
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.framebuffer);
      gl.viewport(0, 0, width, height);
      var err = gl.getError();
      if (err !== gl.NO_ERROR) report('bind eye GL error 0x' + err.toString(16));
    } catch (error) {
      report('bind eye exception: ' + error);
    }
  };

  window.ggqGpuComposeStereoFbo = function (gl, width, height) {
    try {
      width = width | 0;
      height = height | 0;
      if (!gl || width < 2 || height < 2) return;
      var state = stateFor(gl);
      if (!ensureEyes(gl, state, width, height) || !ensureComposer(gl, state)) return;

      var savedProgram = gl.getParameter(gl.CURRENT_PROGRAM);
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
        gl.bindTexture(gl.TEXTURE_2D, state.left.texture);
        gl.uniform1i(state.uLeft, 0);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, state.right.texture);
        gl.uniform1i(state.uRight, 1);

        gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.flush();
        var err = gl.getError();
        if (err !== gl.NO_ERROR) report('compose GL error 0x' + err.toString(16));
      } finally {
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, savedTex0);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, savedTex1);
        gl.activeTexture(savedActive);

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

        // Deliberately leave the default framebuffer bound. GeoGebra's next
        // beginQuestEyeRender call will bind the correct eye FBO explicitly.
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      }
    } catch (error) {
      report('compose exception: ' + error);
    }
  };
})();
</script>

'''

html = html.replace(marker, packer + marker, 1)
p.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Robust A -> XR publication.
#    Never CopyResource into the shared texture. Always render a fullscreen
#    pass-through draw into a BGRA8 keyed-mutex RenderTarget.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
field_marker = "    private PixelShader? _pixelShader;\n"
require(main, field_marker, "v0.13.34 pixel shader field marker missing")
main = main.replace(
    field_marker,
    field_marker + "    private PixelShader? _sharePixelShader;\n",
    1,
)
rt_marker = "    private Texture2D? _xrSharedTexture;\n"
require(main, rt_marker, "v0.13.34 shared texture field marker missing")
main = main.replace(rt_marker, rt_marker + "    private RenderTargetView? _xrSharedRtv;\n", 1)

shutdown_marker = "            _xrSharedMutex?.Dispose();\n            _xrSharedTexture?.Dispose();\n"
require(main, shutdown_marker, "v0.13.34 shutdown shared resource marker missing")
main = main.replace(
    shutdown_marker,
    "            _xrSharedRtv?.Dispose();\n" + shutdown_marker,
    1,
)
shader_dispose = "            _pixelShader?.Dispose();\n            _vertexShader?.Dispose();\n"
require(main, shader_dispose, "v0.13.34 shader dispose marker missing")
main = main.replace(
    shader_dispose,
    "            _sharePixelShader?.Dispose();\n" + shader_dispose,
    1,
)
p.write_text(main, encoding="utf-8")

p = Path("pc/MainFormV11.Graphics.cs")
graphics = p.read_text(encoding="utf-8")

# Create a dedicated pass-through sharing pixel shader; the normal PC pixel
# shader now decodes the embedded SBS and therefore cannot be reused here.
compile_marker = '''        using var psBytecode = ShaderBytecode.Compile(shader, "PSMain", "ps_4_0_level_9_1");
        _vertexShader = new VertexShader(_device, vsBytecode);
        _pixelShader = new PixelShader(_device, psBytecode);'''
require(graphics, compile_marker, "v0.13.34 shader compile marker missing")
share_shader = '''        using var psBytecode = ShaderBytecode.Compile(shader, "PSMain", "ps_4_0_level_9_1");
        _vertexShader = new VertexShader(_device, vsBytecode);
        _pixelShader = new PixelShader(_device, psBytecode);

        const string shareShader = """
            Texture2D tex0 : register(t0);
            SamplerState samp0 : register(s0);
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            float4 PSShare(PSIn input) : SV_Target {
                float4 c = tex0.Sample(samp0, input.uv);
                return float4(c.rgb, 1.0);
            }
            """;
        using var shareBytecode = ShaderBytecode.Compile(
            shareShader, "PSShare", "ps_4_0_level_9_1");
        _sharePixelShader = new PixelShader(_device, shareBytecode);'''
graphics = graphics.replace(compile_marker, share_shader, 1)

# Publish the just-copied client-owned target/SRV, not CEF's pool texture.
old_call = '''                    if (TryQueueGpuPublishLocked(cefTexture))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(cefTexture.Description);'''
new_call = '''                    if (TryQueueGpuPublishLocked(target, _pcSrvs[next]))
                    {
                        _device.ImmediateContext.Flush();
                        CompleteGpuPublishLocked(_xrSharedTexture!.Description);'''
require(graphics, old_call, "v0.13.34 A-share call marker missing")
graphics = graphics.replace(old_call, new_call, 1)

start = graphics.find("    private bool TryQueueGpuPublishLocked(Texture2D cefTexture)\n")
end = graphics.find("\n    private void CompleteGpuPublishLocked", start)
if start < 0 or end < 0:
    raise SystemExit("v0.13.34 TryQueue method bounds missing")

new_method = r'''    private bool TryQueueGpuPublishLocked(
        Texture2D sourceTexture,
        ShaderResourceView? sourceSrv)
    {
        if (_device is null || sourceSrv is null || _sharePixelShader is null ||
            _vertexShader is null || _sampler is null || _rasterizer is null ||
            _inputLayout is null || _vertexBuffer is null)
        {
            return false;
        }

        var source = sourceTexture.Description;
        const Format sharedFormat = Format.B8G8R8A8_UNorm;

        if (_xrSharedTexture is null ||
            _xrSharedTexture.Description.Width != source.Width ||
            _xrSharedTexture.Description.Height != source.Height ||
            _xrSharedTexture.Description.Format != sharedFormat)
        {
            if (_xrSharedRtv is not null) _retiredSharedResources.Add(_xrSharedRtv);
            if (_xrSharedMutex is not null) _retiredSharedResources.Add(_xrSharedMutex);
            if (_xrSharedTexture is not null) _retiredSharedResources.Add(_xrSharedTexture);

            _xrSharedTexture = new Texture2D(
                _device,
                new Texture2DDescription
                {
                    Width = source.Width,
                    Height = source.Height,
                    MipLevels = 1,
                    ArraySize = 1,
                    Format = sharedFormat,
                    SampleDescription = new SampleDescription(1, 0),
                    Usage = ResourceUsage.Default,
                    BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
                    CpuAccessFlags = CpuAccessFlags.None,
                    OptionFlags = ResourceOptionFlags.SharedKeyedmutex
                });
            _xrSharedRtv = new RenderTargetView(_device, _xrSharedTexture);
            _xrSharedMutex = _xrSharedTexture.QueryInterface<KeyedMutex>();
            using var dxgiResource =
                _xrSharedTexture.QueryInterface<SharpDX.DXGI.Resource>();
            _xrSharedHandle = dxgiResource.SharedHandle;
        }

        if (_xrSharedTexture is null || _xrSharedRtv is null ||
            _xrSharedMutex is null || _xrSharedHandle == IntPtr.Zero)
        {
            return false;
        }

        try
        {
            _xrSharedMutex.Acquire(0, 0);
        }
        catch
        {
            return false;
        }

        try
        {
            var context = _device.ImmediateContext;
            context.OutputMerger.SetRenderTargets(_xrSharedRtv);
            context.Rasterizer.SetViewport(new Viewport(
                0, 0, source.Width, source.Height, 0, 1));
            context.Rasterizer.State = _rasterizer;
            context.InputAssembler.PrimitiveTopology = PrimitiveTopology.TriangleList;
            context.InputAssembler.InputLayout = _inputLayout;
            context.InputAssembler.SetVertexBuffers(
                0,
                new VertexBufferBinding(
                    _vertexBuffer,
                    Marshal.SizeOf<VertexDx11>(),
                    0));
            context.VertexShader.Set(_vertexShader);
            context.PixelShader.Set(_sharePixelShader);
            context.PixelShader.SetSampler(0, _sampler);
            context.PixelShader.SetShaderResource(0, sourceSrv);
            context.Draw(FullScreenTriangle.Length, 0);
            context.PixelShader.SetShaderResource(0, null);
            return true;
        }
        catch
        {
            try { _xrSharedMutex.Release(0); } catch { }
            throw;
        }
    }
'''

graphics = graphics[:start] + new_method + graphics[end:]
p.write_text(graphics, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Version/package/runtime labels.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.34</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.34.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.34.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

p = Path("pc/build.ps1")
build = p.read_text(encoding="utf-8")
build = re.sub(
    r"GeoGebraForQuest-PC-v0\.13\.\d+[^'\"]*-win-x64",
    "GeoGebraForQuest-PC-v0.13.34-gpu-fbo-sbs-win-x64",
    build,
)
build = build.replace("0.13.32", "0.13.34")
build = build.replace("0.13.31", "0.13.34")
p.write_text(build, encoding="utf-8")

p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
main = main.replace("GeoGebraForQuest PC v0.13.32", "GeoGebraForQuest PC v0.13.34")
main = re.sub(
    r"(pc-stereo-layout\.js\?v=)[^\"']+",
    r"\g<1>0.13.34-gpu-fbo-sbs",
    main,
    count=1,
)
p.write_text(main, encoding="utf-8")

# Architecture invariants.
checks = {
    "app/src/main/assets/web/index.html": [
        "ggq-gpu-fbo-sbs",
        "ggqGpuBindEyeFramebuffer",
        "framebufferTexture2D",
        "ggqGpuComposeStereoFbo",
    ],
    "pc/MainFormV11.Graphics.cs": [
        "TryQueueGpuPublishLocked(target, _pcSrvs[next])",
        "PSShare",
        "BindFlags.ShaderResource | BindFlags.RenderTarget",
        "ResourceOptionFlags.SharedKeyedmutex",
        "context.OutputMerger.SetRenderTargets(_xrSharedRtv)",
    ],
    "pc/StereoSharedFrameWriter.cs": ["_view.Write(116, 4)"],
    "pc-xr/v11-render.hpp": ["GPU-NATIVE EMBEDDED-SBS"],
    "pc/GeoGebraForQuest.PC.csproj": ["<Version>0.13.34</Version>"],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"v0.13.34 invariant missing in {file}: {needle}")

print("GeoGebraForQuest PC v0.13.34 GPU FBO SBS + shader A-share applied")
