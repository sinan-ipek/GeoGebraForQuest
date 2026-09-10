#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.13.39 — GPU-only full-window A_L/A_R path.

Architecture implemented by this patch:

  one GeoGebra scene state
      -> LEFT W x H eye FBO (x=0)
      -> RIGHT W x H eye FBO (x=0)
      -> browser compositor exports a COMPLETE A_L frame
      -> browser compositor exports a COMPLETE A_R frame
      -> host GPU composes [A_L | A_R] into one shared D3D11 texture
      -> OpenXR samples the matching half per physical eye

The PC swapchain is never updated with the temporary LEFT phase. Menus/dialogs
remain native Chromium/GeoGebra compositor content, so no rectangular 3D patch
can cover them. No framebuffer pixels use getImageData/readPixels/JPEG/Base64 or
raw pixel MMF transport.
"""

from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) Page GPU bridge: two independent W x H FBOs and a frozen export pair.
# ---------------------------------------------------------------------------
p = Path("app/src/main/assets/web/index.html")
html = p.read_text(encoding="utf-8")
marker = "<script>\n(function () {\n  'use strict';\n"
require(html, marker, "v0.13.39 index bootstrap marker missing")

bridge = r'''<script id="ggq-gpu-fullframe-sbs-v01339">
(function () {
  'use strict';

  var states = new WeakMap();
  var lastState = null;
  var lastError = '';

  function send(name, payload) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge[name] === 'function') {
        window.QuestBridge[name](JSON.stringify(payload || {}));
      }
    } catch (_) {}
  }

  function diag(kind, state, extra) {
    var payload = {
      kind: kind,
      serial: state ? state.serial : -1,
      width: state ? state.width : 0,
      height: state ? state.height : 0,
      frozen: !!(state && state.frozen),
      deferred: !!(state && state.deferred),
      timeMs: performance.now()
    };
    if (extra) {
      Object.keys(extra).forEach(function (key) { payload[key] = extra[key]; });
    }
    send('gpuStereoDiag', payload);
  }

  function report(message, state) {
    message = String(message || 'unknown GPU stereo error');
    if (message !== lastError) {
      lastError = message;
      console.error('[GGQ v0.13.39]', message);
      try {
        if (window.QuestBridge && typeof window.QuestBridge.runtimeError === 'function') {
          window.QuestBridge.runtimeError('GPU stereo: ' + message);
        }
      } catch (_) {}
    }
    diag('error', state || lastState, { message: message });
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
      'uniform sampler2D u_tex;\n' +
      'varying vec2 v_uv;\n' +
      'void main(){gl_FragColor=texture2D(u_tex,clamp(v_uv,0.0,1.0));}\n');
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
    if (!texture || !framebuffer || !depth) return null;

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

    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
      deleteEye(gl, { texture: texture, framebuffer: framebuffer, depth: depth });
      return null;
    }
    return { texture: texture, framebuffer: framebuffer, depth: depth };
  }

  function stateFor(gl) {
    var state = states.get(gl);
    if (state) {
      lastState = state;
      return state;
    }
    state = {
      gl: gl,
      width: 0,
      height: 0,
      left: null,
      right: null,
      program: null,
      buffer: null,
      aPos: -1,
      uTex: null,
      serial: 0,
      frozen: false,
      deferred: false,
      presentToken: 0,
      eyeStart: [0, 0],
      eyeMs: [0, 0],
      pairStartedAt: 0
    };
    states.set(gl, state);
    lastState = state;
    return state;
  }

  function ensureResources(gl, state, width, height) {
    if (width < 2 || height < 2) return false;
    if (!state.left || !state.right || state.width !== width || state.height !== height) {
      var savedFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
      var savedRenderbuffer = gl.getParameter(gl.RENDERBUFFER_BINDING);
      var savedActive = gl.getParameter(gl.ACTIVE_TEXTURE);
      var savedTexture = gl.getParameter(gl.TEXTURE_BINDING_2D);
      try {
        deleteEye(gl, state.left);
        deleteEye(gl, state.right);
        state.left = createEye(gl, width, height);
        state.right = createEye(gl, width, height);
        state.width = width;
        state.height = height;
      } finally {
        gl.bindFramebuffer(gl.FRAMEBUFFER, savedFramebuffer);
        gl.bindRenderbuffer(gl.RENDERBUFFER, savedRenderbuffer);
        gl.bindTexture(gl.TEXTURE_2D, savedTexture);
        gl.activeTexture(savedActive);
      }
      if (!state.left || !state.right) {
        report('eye FBO allocation failed ' + width + 'x' + height, state);
        return false;
      }
      diag('fbo-allocated', state, {});
    }

    if (!state.program) {
      state.program = createProgram(gl);
      if (!state.program) return false;
      state.aPos = gl.getAttribLocation(state.program, 'a_pos');
      state.uTex = gl.getUniformLocation(state.program, 'u_tex');
      state.buffer = gl.createBuffer();
      if (state.aPos < 0 || state.uTex === null || !state.buffer) {
        report('present shader resources missing', state);
        return false;
      }
      var saved = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
      gl.bindBuffer(gl.ARRAY_BUFFER, state.buffer);
      gl.bufferData(gl.ARRAY_BUFFER,
        new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, saved);
    }
    return true;
  }

  function presentTexture(gl, state, texture) {
    var savedProgram = gl.getParameter(gl.CURRENT_PROGRAM);
    var savedArrayBuffer = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
    var savedViewport = gl.getParameter(gl.VIEWPORT);
    var savedScissor = gl.getParameter(gl.SCISSOR_BOX);
    var savedColorMask = gl.getParameter(gl.COLOR_WRITEMASK);
    var savedDepthMask = gl.getParameter(gl.DEPTH_WRITEMASK);
    var savedActive = gl.getParameter(gl.ACTIVE_TEXTURE);

    gl.activeTexture(gl.TEXTURE0);
    var savedTex0 = gl.getParameter(gl.TEXTURE_BINDING_2D);

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
      gl.viewport(0, 0, state.width, state.height);
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
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.uniform1i(state.uTex, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.flush();
      var err = gl.getError();
      if (err !== gl.NO_ERROR) report('present GL error 0x' + err.toString(16), state);
    } finally {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, savedTex0);
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
      // The browser compositor must see the selected eye on the ordinary W x H
      // canvas. The next GeoGebra pair explicitly binds its own FBO again.
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    }
  }

  window.ggqGpuCanBeginStereoPair = function (gl, width, height) {
    try {
      var state = stateFor(gl);
      if (!ensureResources(gl, state, width | 0, height | 0)) return false;
      if (state.frozen) {
        state.deferred = true;
        diag('scene-deferred-while-export-frozen', state, {});
        return false;
      }
      state.pairStartedAt = performance.now();
      return true;
    } catch (error) {
      report('canBegin exception: ' + error, lastState);
      return false;
    }
  };

  window.ggqGpuBindEyeFramebuffer = function (gl, eye, width, height) {
    try {
      var state = stateFor(gl);
      if (!ensureResources(gl, state, width | 0, height | 0)) return;
      var index = eye === 1 ? 1 : 0;
      var target = index ? state.right : state.left;
      state.eyeStart[index] = performance.now();
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.framebuffer);
      gl.viewport(0, 0, state.width, state.height);
    } catch (error) {
      report('bindEye exception: ' + error, lastState);
    }
  };

  window.ggqGpuEndEyeFramebuffer = function (gl, eye) {
    try {
      var state = stateFor(gl);
      var index = eye === 1 ? 1 : 0;
      gl.flush();
      state.eyeMs[index] = Math.max(0, performance.now() - state.eyeStart[index]);
    } catch (error) {
      report('endEye exception: ' + error, lastState);
    }
  };

  window.ggqGpuFinishStereoPair = function (gl, width, height, serial) {
    try {
      var state = stateFor(gl);
      if (!ensureResources(gl, state, width | 0, height | 0)) return;
      state.serial = serial | 0;
      state.frozen = true;
      state.deferred = false;

      var presentStarted = performance.now();
      presentTexture(gl, state, state.right.texture);
      var presentMs = Math.max(0, performance.now() - presentStarted);
      var pairMs = Math.max(0, performance.now() - state.pairStartedAt);

      send('gpuStereoPairReady', {
        serial: state.serial,
        reason: 'scene',
        width: state.width,
        height: state.height,
        leftEyeMs: state.eyeMs[0],
        rightEyeMs: state.eyeMs[1],
        pairMs: pairMs,
        rightPresentMs: presentMs
      });
      diag('pair-ready', state, { pairMs: pairMs });
    } catch (error) {
      report('finishPair exception: ' + error, lastState);
    }
  };

  window.ggqGpuBeginStereoExportCurrent = function () {
    var state = lastState;
    if (!state || state.serial <= 0 || state.frozen) return false;
    state.frozen = true;
    state.deferred = false;
    send('gpuStereoPairReady', {
      serial: state.serial,
      reason: 'ui',
      width: state.width,
      height: state.height,
      leftEyeMs: 0,
      rightEyeMs: 0,
      pairMs: 0,
      rightPresentMs: 0
    });
    diag('ui-export-begin', state, {});
    return true;
  };

  window.ggqGpuPresentStereoEye = function (eye, serial) {
    var state = lastState;
    eye = eye === 1 ? 1 : 0;
    serial = serial | 0;
    if (!state || !state.frozen || state.serial !== serial) {
      if (state) diag('present-rejected', state, { requestedSerial: serial, eye: eye });
      return false;
    }

    var token = ++state.presentToken;
    var started = performance.now();
    presentTexture(state.gl, state, eye ? state.right.texture : state.left.texture);
    var drawMs = Math.max(0, performance.now() - started);
    var done = false;

    function acknowledge(source) {
      if (done || !state.frozen || state.serial !== serial || token !== state.presentToken) return;
      done = true;
      var waitMs = Math.max(0, performance.now() - started);
      send('gpuStereoEyePresented', {
        serial: serial,
        eye: eye,
        width: state.width,
        height: state.height,
        drawMs: drawMs,
        compositorWaitMs: waitMs,
        ackSource: source
      });
      diag('eye-presented', state, {
        eye: eye,
        drawMs: drawMs,
        compositorWaitMs: waitMs,
        ackSource: source
      });
    }

    // Keep the selected eye stable while Chromium gets two compositor turns.
    // A timer fallback protects headless/off-screen RAF throttling.
    try {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { acknowledge('raf2'); });
      });
    } catch (_) {}
    setTimeout(function () { acknowledge('timeout'); }, 40);
    return true;
  };

  window.ggqGpuReleaseStereoPair = function (serial) {
    var state = lastState;
    serial = serial | 0;
    if (!state || state.serial !== serial) return false;
    var deferred = state.deferred;
    state.frozen = false;
    state.deferred = false;
    state.presentToken++;
    diag('pair-released', state, { deferred: deferred });

    // Only a renderer draw attempted while frozen causes a catch-up repaint.
    // Static scenes therefore do not create a self-sustaining stereo loop.
    if (deferred && typeof window.ggqRequestStereoFrame === 'function') {
      setTimeout(function () {
        try { window.ggqRequestStereoFrame(); } catch (_) {}
      }, 0);
    }
    return true;
  };
})();
</script>

'''
html = html.replace(marker, bridge + marker, 1)
p.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Replace old pixel-capture runtime with geometry-only runtime.
# ---------------------------------------------------------------------------
p = Path("pc/pc-stereo-layout.js")
runtime = r'''(function () {
  'use strict';
  if (window.__ggqPcGpuFullFrameSbsV01339) return;
  window.__ggqPcGpuFullFrameSbsV01339 = true;

  var lastPayload = '';
  var scheduled = false;

  function bridge(name, value) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge[name] === 'function') {
        window.QuestBridge[name](value);
      }
    } catch (_) {}
  }

  function visibleRect(canvas) {
    if (!canvas || !canvas.isConnected) return null;
    var style;
    try { style = getComputedStyle(canvas); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden' ||
        Number(style.opacity) <= 0.001) return null;
    var r = canvas.getBoundingClientRect();
    var l = Math.max(0, r.left);
    var t = Math.max(0, r.top);
    var rr = Math.min(innerWidth, r.right);
    var bb = Math.min(innerHeight, r.bottom);
    if (rr - l < 2 || bb - t < 2) return null;
    return { left:l, top:t, width:rr-l, height:bb-t };
  }

  function isWebGlCanvas(canvas) {
    try {
      return !!(canvas.getContext('webgl2') || canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl'));
    } catch (_) {
      return false;
    }
  }

  function find3DCanvas() {
    var all = document.querySelectorAll('canvas');
    var best = null;
    var bestArea = 0;
    for (var i = 0; i < all.length; i++) {
      var canvas = all[i];
      var rect = visibleRect(canvas);
      if (!rect || rect.width < 120 || rect.height < 120) continue;
      if (!isWebGlCanvas(canvas)) continue;
      var area = rect.width * rect.height;
      if (area > bestArea) {
        bestArea = area;
        best = { canvas:canvas, rect:rect };
      }
    }
    return best;
  }

  function refresh() {
    scheduled = false;
    var found = find3DCanvas();
    var payload;
    if (found) {
      payload = JSON.stringify({
        active:true,
        viewWidth:innerWidth,
        viewHeight:innerHeight,
        stereo:found.rect,
        mode:'gpu-fullframe-sbs-v01339'
      });
    } else {
      payload = JSON.stringify({
        active:false,
        viewWidth:innerWidth,
        viewHeight:innerHeight,
        mode:'gpu-fullframe-sbs-v01339'
      });
    }
    if (payload !== lastPayload) {
      lastPayload = payload;
      bridge('updateStereoLayout', payload);
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(refresh);
  }

  addEventListener('resize', schedule, { passive:true });
  addEventListener('load', schedule, { passive:true });
  try {
    new MutationObserver(schedule).observe(document.documentElement, {
      childList:true, subtree:true, attributes:true,
      attributeFilter:['style','class','hidden']
    });
  } catch (_) {}
  setInterval(refresh, 500);
  setTimeout(refresh, 50);
  setTimeout(refresh, 500);
  setTimeout(function () { bridge('panelReady'); }, 600);
})();
'''
p.write_text(runtime, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Host diagnostics writer. log.zip already collects GeoGebraForQuestPC.*.
# ---------------------------------------------------------------------------
telemetry = r'''using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace GeoGebraForQuest.PC;

internal sealed class GpuStereoTelemetry : IDisposable
{
    private readonly object _sync = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly StreamWriter _csv;
    private readonly StreamWriter _js;
    private bool _disposed;

    public GpuStereoTelemetry()
    {
        var baseDir = AppContext.BaseDirectory;
        _csv = new StreamWriter(
            Path.Combine(baseDir, "GeoGebraForQuestPC.Performance.GPU.csv"),
            append: false,
            new UTF8Encoding(false));
        _js = new StreamWriter(
            Path.Combine(baseDir, "GeoGebraForQuestPC.Performance.GPUJS.jsonl"),
            append: false,
            new UTF8Encoding(false));
        _csv.AutoFlush = true;
        _js.AutoFlush = true;
        _csv.WriteLine(
            "utc,elapsed_ms,event,serial,eye,phase,width,height,copy_ms,compose_ms,publish_ms,detail");
    }

    public void Event(
        string name,
        long serial = -1,
        int eye = -1,
        string phase = "",
        int width = 0,
        int height = 0,
        double copyMs = 0,
        double composeMs = 0,
        double publishMs = 0,
        string detail = "")
    {
        if (_disposed) return;
        lock (_sync)
        {
            if (_disposed) return;
            _csv.WriteLine(string.Join(",", new[]
            {
                Csv(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)),
                _clock.Elapsed.TotalMilliseconds.ToString("F3", CultureInfo.InvariantCulture),
                Csv(name), serial.ToString(CultureInfo.InvariantCulture),
                eye.ToString(CultureInfo.InvariantCulture), Csv(phase),
                width.ToString(CultureInfo.InvariantCulture),
                height.ToString(CultureInfo.InvariantCulture),
                copyMs.ToString("F3", CultureInfo.InvariantCulture),
                composeMs.ToString("F3", CultureInfo.InvariantCulture),
                publishMs.ToString("F3", CultureInfo.InvariantCulture),
                Csv(detail)
            }));
        }
    }

    public void Js(string json)
    {
        if (_disposed || string.IsNullOrWhiteSpace(json)) return;
        lock (_sync)
        {
            if (_disposed) return;
            _js.WriteLine(json);
        }
    }

    private static string Csv(string value)
    {
        value ??= string.Empty;
        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            _disposed = true;
            _csv.Dispose();
            _js.Dispose();
        }
    }
}
'''
Path("pc/GpuStereoTelemetry.cs").write_text(telemetry, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Host GPU state machine. Full browser frames are classified only while a
# selected eye remains frozen. LEFT never reaches the PC swapchain; RIGHT does.
# ---------------------------------------------------------------------------
host = r'''using System.Diagnostics;
using System.Text.Json;
using CefSharp;
using CefSharp.Enums;
using SharpDX;
using SharpDX.D3DCompiler;
using SharpDX.Direct3D;
using SharpDX.Direct3D11;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private enum GpuStereoCaptureState
    {
        Idle,
        AwaitPairReady,
        AwaitLeftPresented,
        CaptureLeftPaint,
        AwaitRightPresented,
        CaptureRightPaint
    }

    private readonly GpuStereoTelemetry _gpuStereoTelemetry = new();
    private GpuStereoCaptureState _gpuStereoCaptureState = GpuStereoCaptureState.Idle;
    private long _gpuStereoCaptureSerial = -1;
    private long _gpuStereoLastCompletedSerial = -1;
    private bool _gpuStereoPairAvailable;
    private int _gpuStereoUiRefreshScheduled;

    private Texture2D? _gpuStereoLeftTexture;
    private Texture2D? _gpuStereoRightTexture;
    private ShaderResourceView? _gpuStereoLeftSrv;
    private ShaderResourceView? _gpuStereoRightSrv;
    private RenderTargetView? _gpuStereoSharedRtv;
    private PixelShader? _gpuStereoComposePixelShader;

    private static bool TryPayload(JsonElement root, out JsonDocument? document)
    {
        document = null;
        if (!root.TryGetProperty("payload", out var payloadNode)) return false;
        var payload = payloadNode.GetString();
        if (string.IsNullOrWhiteSpace(payload)) return false;
        document = JsonDocument.Parse(payload);
        return true;
    }

    private void HandleGpuStereoPairReady(JsonElement root)
    {
        try
        {
            if (!TryPayload(root, out var document) || document is null) return;
            using (document)
            {
                var p = document.RootElement;
                var serial = p.TryGetProperty("serial", out var s) ? s.GetInt64() : -1;
                var width = p.TryGetProperty("width", out var w) ? w.GetInt32() : 0;
                var height = p.TryGetProperty("height", out var h) ? h.GetInt32() : 0;
                var reason = p.TryGetProperty("reason", out var r) ? r.GetString() ?? "" : "";
                if (serial < 0) return;

                bool start;
                lock (_d3dLock)
                {
                    _gpuStereoPairAvailable = true;
                    if (serial < _gpuStereoLastCompletedSerial)
                    {
                        _gpuStereoTelemetry.Event(
                            "pair-ready-stale", serial, -1,
                            _gpuStereoCaptureState.ToString(), width, height, detail: reason);
                        return;
                    }

                    start = _gpuStereoCaptureState == GpuStereoCaptureState.Idle ||
                            _gpuStereoCaptureState == GpuStereoCaptureState.AwaitPairReady;
                    if (start)
                    {
                        _gpuStereoCaptureSerial = serial;
                        _gpuStereoCaptureState = GpuStereoCaptureState.AwaitLeftPresented;
                    }
                    _gpuStereoTelemetry.Event(
                        start ? "pair-ready" : "pair-ready-while-busy",
                        serial, -1, _gpuStereoCaptureState.ToString(), width, height,
                        detail: reason);
                }

                if (start)
                {
                    ExecuteGpuStereoScript($"window.ggqGpuPresentStereoEye && window.ggqGpuPresentStereoEye(0,{serial});");
                    ArmGpuStereoWatchdog(serial, GpuStereoCaptureState.AwaitLeftPresented);
                }
            }
        }
        catch (Exception ex)
        {
            _gpuStereoTelemetry.Event("pair-ready-error", detail: ex.Message);
        }
    }

    private void HandleGpuStereoEyePresented(JsonElement root)
    {
        try
        {
            if (!TryPayload(root, out var document) || document is null) return;
            using (document)
            {
                var p = document.RootElement;
                var serial = p.TryGetProperty("serial", out var s) ? s.GetInt64() : -1;
                var eye = p.TryGetProperty("eye", out var e) ? e.GetInt32() : -1;
                var width = p.TryGetProperty("width", out var w) ? w.GetInt32() : 0;
                var height = p.TryGetProperty("height", out var h) ? h.GetInt32() : 0;
                var drawMs = p.TryGetProperty("drawMs", out var d) ? d.GetDouble() : 0;
                var waitMs = p.TryGetProperty("compositorWaitMs", out var cw) ? cw.GetDouble() : 0;

                bool invalidate = false;
                lock (_d3dLock)
                {
                    if (serial != _gpuStereoCaptureSerial)
                    {
                        _gpuStereoTelemetry.Event(
                            "eye-presented-wrong-serial", serial, eye,
                            _gpuStereoCaptureState.ToString(), width, height,
                            detail: $"expected={_gpuStereoCaptureSerial}");
                        return;
                    }

                    if (eye == 0 &&
                        _gpuStereoCaptureState == GpuStereoCaptureState.AwaitLeftPresented)
                    {
                        _gpuStereoCaptureState = GpuStereoCaptureState.CaptureLeftPaint;
                        invalidate = true;
                    }
                    else if (eye == 1 &&
                        _gpuStereoCaptureState == GpuStereoCaptureState.AwaitRightPresented)
                    {
                        _gpuStereoCaptureState = GpuStereoCaptureState.CaptureRightPaint;
                        invalidate = true;
                    }
                    else
                    {
                        _gpuStereoTelemetry.Event(
                            "eye-presented-unexpected", serial, eye,
                            _gpuStereoCaptureState.ToString(), width, height,
                            detail: $"draw={drawMs:F3};wait={waitMs:F3}");
                        return;
                    }

                    _gpuStereoTelemetry.Event(
                        "eye-presented", serial, eye,
                        _gpuStereoCaptureState.ToString(), width, height,
                        detail: $"draw={drawMs:F3};wait={waitMs:F3}");
                }

                if (invalidate)
                {
                    try { _browser?.GetBrowserHost()?.Invalidate(PaintElementType.View); } catch { }
                    ArmGpuStereoWatchdog(
                        serial,
                        eye == 0
                            ? GpuStereoCaptureState.CaptureLeftPaint
                            : GpuStereoCaptureState.CaptureRightPaint);
                }
            }
        }
        catch (Exception ex)
        {
            _gpuStereoTelemetry.Event("eye-presented-error", detail: ex.Message);
        }
    }

    private void HandleGpuStereoDiag(JsonElement root)
    {
        try
        {
            if (root.TryGetProperty("payload", out var payload))
            {
                _gpuStereoTelemetry.Js(payload.GetString() ?? "");
            }
        }
        catch { }
    }

    private void ExecuteGpuStereoScript(string script)
    {
        if (_closing) return;
        try
        {
            var browser = _browser?.GetBrowser();
            var frame = browser?.MainFrame;
            frame?.ExecuteJavaScriptAsync(script);
        }
        catch (Exception ex)
        {
            _gpuStereoTelemetry.Event("execute-js-error", detail: ex.Message);
        }
    }

    private void ArmGpuStereoWatchdog(long serial, GpuStereoCaptureState expected)
    {
        _ = Task.Run(async () =>
        {
            await Task.Delay(900).ConfigureAwait(false);
            if (_closing) return;
            bool timedOut = false;
            lock (_d3dLock)
            {
                if (_gpuStereoCaptureSerial == serial &&
                    _gpuStereoCaptureState == expected)
                {
                    _gpuStereoCaptureState = GpuStereoCaptureState.Idle;
                    timedOut = true;
                    _gpuStereoTelemetry.Event(
                        "phase-timeout", serial, -1, expected.ToString());
                }
            }
            if (timedOut)
            {
                ExecuteGpuStereoScript(
                    $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial});");
            }
        });
    }

    private void ScheduleGpuStereoUiExport()
    {
        if (_closing || !_gpuStereoPairAvailable) return;
        if (Interlocked.Exchange(ref _gpuStereoUiRefreshScheduled, 1) != 0) return;

        _ = Task.Run(async () =>
        {
            try
            {
                // Allow the previous RIGHT capture/release command to settle.
                await Task.Delay(18).ConfigureAwait(false);
                if (_closing) return;

                bool request = false;
                lock (_d3dLock)
                {
                    if (_gpuStereoPairAvailable &&
                        _gpuStereoCaptureState == GpuStereoCaptureState.Idle)
                    {
                        _gpuStereoCaptureState = GpuStereoCaptureState.AwaitPairReady;
                        request = true;
                        _gpuStereoTelemetry.Event(
                            "ui-export-request", _gpuStereoCaptureSerial, -1,
                            _gpuStereoCaptureState.ToString());
                    }
                }

                if (request)
                {
                    ExecuteGpuStereoScript(
                        "window.ggqGpuBeginStereoExportCurrent && window.ggqGpuBeginStereoExportCurrent();");
                    ArmGpuStereoWatchdog(
                        _gpuStereoCaptureSerial,
                        GpuStereoCaptureState.AwaitPairReady);
                }
            }
            finally
            {
                Interlocked.Exchange(ref _gpuStereoUiRefreshScheduled, 0);
            }
        });
    }

    private bool TryConsumeGpuStereoPaintLocked(Texture2D cefTexture)
    {
        var state = _gpuStereoCaptureState;
        if (state == GpuStereoCaptureState.Idle)
        {
            return false;
        }

        // While waiting for the JS two-RAF acknowledgement, never let a temporary
        // LEFT/RIGHT phase leak to the physical PC swapchain.
        if (state == GpuStereoCaptureState.AwaitPairReady ||
            state == GpuStereoCaptureState.AwaitLeftPresented ||
            state == GpuStereoCaptureState.AwaitRightPresented)
        {
            return true;
        }

        EnsureGpuStereoCaptureTexturesLocked(cefTexture.Description);
        var serial = _gpuStereoCaptureSerial;

        if (state == GpuStereoCaptureState.CaptureLeftPaint)
        {
            if (_gpuStereoLeftTexture is null) return true;
            var sw = Stopwatch.StartNew();
            _device!.ImmediateContext.CopyResource(cefTexture, _gpuStereoLeftTexture);
            sw.Stop();
            _gpuStereoCaptureState = GpuStereoCaptureState.AwaitRightPresented;
            _gpuStereoTelemetry.Event(
                "left-fullframe-captured", serial, 0,
                _gpuStereoCaptureState.ToString(),
                cefTexture.Description.Width, cefTexture.Description.Height,
                copyMs: sw.Elapsed.TotalMilliseconds);

            ThreadPool.QueueUserWorkItem(_ =>
            {
                ExecuteGpuStereoScript(
                    $"window.ggqGpuPresentStereoEye && window.ggqGpuPresentStereoEye(1,{serial});");
                ArmGpuStereoWatchdog(serial, GpuStereoCaptureState.AwaitRightPresented);
            });
            return true;
        }

        if (state == GpuStereoCaptureState.CaptureRightPaint)
        {
            if (_gpuStereoRightTexture is null) return true;
            var copy = Stopwatch.StartNew();
            _device!.ImmediateContext.CopyResource(cefTexture, _gpuStereoRightTexture);

            // RIGHT is the ordinary PC-visible eye in the proven v0.9.21/v0.13.35
            // behavior. Only this phase advances the PC swapchain source.
            EnsurePcTextureLocked(cefTexture.Description);
            var next = _currentPcTexture ^ 1;
            var pcTarget = _pcTextures[next];
            if (pcTarget is not null)
            {
                _device.ImmediateContext.CopyResource(cefTexture, pcTarget);
                _currentPcTexture = next;
                Interlocked.Increment(ref _gpuFrameNumber);
            }
            copy.Stop();

            var composeMs = 0.0;
            var publishMs = 0.0;
            var published = ComposeAndPublishGpuFullSbsLocked(
                cefTexture.Description,
                out composeMs,
                out publishMs);

            _gpuStereoLastCompletedSerial = serial;
            _gpuStereoCaptureState = GpuStereoCaptureState.Idle;
            _gpuStereoPairAvailable = true;
            _gpuShareStatus = published ? "A_L|A_R GPU" : "A_L|A_R GPU bekliyor";
            _gpuStereoTelemetry.Event(
                published ? "right-captured-sbs-published" : "right-captured-publish-missed",
                serial, 1, _gpuStereoCaptureState.ToString(),
                cefTexture.Description.Width, cefTexture.Description.Height,
                copyMs: copy.Elapsed.TotalMilliseconds,
                composeMs: composeMs,
                publishMs: publishMs);

            ThreadPool.QueueUserWorkItem(_ =>
                ExecuteGpuStereoScript(
                    $"window.ggqGpuReleaseStereoPair && window.ggqGpuReleaseStereoPair({serial});"));
            BeginInvokeSafe(UpdateWindowTitle);
            return true;
        }

        return true;
    }

    private void EnsureGpuStereoCaptureTexturesLocked(Texture2DDescription source)
    {
        if (_device is null) return;
        if (_gpuStereoLeftTexture is not null &&
            _gpuStereoRightTexture is not null &&
            _gpuStereoLeftTexture.Description.Width == source.Width &&
            _gpuStereoLeftTexture.Description.Height == source.Height &&
            _gpuStereoLeftTexture.Description.Format == source.Format)
        {
            return;
        }

        _gpuStereoLeftSrv?.Dispose();
        _gpuStereoRightSrv?.Dispose();
        _gpuStereoLeftTexture?.Dispose();
        _gpuStereoRightTexture?.Dispose();
        _gpuStereoLeftSrv = null;
        _gpuStereoRightSrv = null;
        _gpuStereoLeftTexture = null;
        _gpuStereoRightTexture = null;

        var desc = new Texture2DDescription
        {
            Width = source.Width,
            Height = source.Height,
            MipLevels = 1,
            ArraySize = 1,
            Format = source.Format,
            SampleDescription = source.SampleDescription,
            Usage = ResourceUsage.Default,
            BindFlags = BindFlags.ShaderResource,
            CpuAccessFlags = CpuAccessFlags.None,
            OptionFlags = ResourceOptionFlags.None
        };
        _gpuStereoLeftTexture = new Texture2D(_device, desc);
        _gpuStereoRightTexture = new Texture2D(_device, desc);
        _gpuStereoLeftSrv = new ShaderResourceView(_device, _gpuStereoLeftTexture);
        _gpuStereoRightSrv = new ShaderResourceView(_device, _gpuStereoRightTexture);
        _gpuStereoTelemetry.Event(
            "host-eye-textures-allocated", _gpuStereoCaptureSerial, -1,
            _gpuStereoCaptureState.ToString(), source.Width, source.Height,
            detail: source.Format.ToString());
    }

    private void EnsureGpuStereoComposeShaderLocked()
    {
        if (_device is null || _gpuStereoComposePixelShader is not null) return;
        const string shader = """
            Texture2D leftTex : register(t0);
            Texture2D rightTex : register(t1);
            SamplerState samp0 : register(s0);
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            float4 PSMain(PSIn input) : SV_Target {
                bool rightEye = input.uv.x >= 0.5;
                float x = rightEye ? (input.uv.x - 0.5) * 2.0 : input.uv.x * 2.0;
                float2 uv = float2(saturate(x), saturate(input.uv.y));
                return rightEye ? rightTex.Sample(samp0, uv) : leftTex.Sample(samp0, uv);
            }
            """;
        using var bytecode = ShaderBytecode.Compile(
            shader, "PSMain", "ps_4_0_level_9_1");
        _gpuStereoComposePixelShader = new PixelShader(_device, bytecode);
    }

    private void EnsureGpuStereoSharedTargetLocked(Texture2DDescription source)
    {
        if (_device is null) return;
        var targetWidth = checked(source.Width * 2);
        if (_xrSharedTexture is not null &&
            _gpuStereoSharedRtv is not null &&
            _xrSharedTexture.Description.Width == targetWidth &&
            _xrSharedTexture.Description.Height == source.Height &&
            _xrSharedTexture.Description.Format == source.Format)
        {
            return;
        }

        if (_gpuStereoSharedRtv is not null) _retiredSharedResources.Add(_gpuStereoSharedRtv);
        if (_xrSharedMutex is not null) _retiredSharedResources.Add(_xrSharedMutex);
        if (_xrSharedTexture is not null) _retiredSharedResources.Add(_xrSharedTexture);
        _gpuStereoSharedRtv = null;
        _xrSharedMutex = null;
        _xrSharedTexture = null;
        _xrSharedHandle = IntPtr.Zero;

        _xrSharedTexture = new Texture2D(
            _device,
            new Texture2DDescription
            {
                Width = targetWidth,
                Height = source.Height,
                MipLevels = 1,
                ArraySize = 1,
                Format = source.Format,
                SampleDescription = new SampleDescription(1, 0),
                Usage = ResourceUsage.Default,
                BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
                CpuAccessFlags = CpuAccessFlags.None,
                OptionFlags = ResourceOptionFlags.SharedKeyedmutex
            });
        _gpuStereoSharedRtv = new RenderTargetView(_device, _xrSharedTexture);
        _xrSharedMutex = _xrSharedTexture.QueryInterface<KeyedMutex>();
        using var dxgiResource = _xrSharedTexture.QueryInterface<SharpDX.DXGI.Resource>();
        _xrSharedHandle = dxgiResource.SharedHandle;
        _gpuStereoTelemetry.Event(
            "shared-full-sbs-allocated", _gpuStereoCaptureSerial, -1,
            _gpuStereoCaptureState.ToString(), targetWidth, source.Height,
            detail: source.Format.ToString());
    }

    private bool ComposeAndPublishGpuFullSbsLocked(
        Texture2DDescription source,
        out double composeMs,
        out double publishMs)
    {
        composeMs = 0;
        publishMs = 0;
        if (_device is null || _gpuStereoLeftSrv is null || _gpuStereoRightSrv is null)
            return false;

        EnsureGpuStereoComposeShaderLocked();
        EnsureGpuStereoSharedTargetLocked(source);
        if (_gpuStereoComposePixelShader is null ||
            _gpuStereoSharedRtv is null || _xrSharedTexture is null ||
            _xrSharedMutex is null || _xrSharedHandle == IntPtr.Zero)
            return false;

        try
        {
            _xrSharedMutex.Acquire(0, 0);
        }
        catch
        {
            _gpuStereoTelemetry.Event(
                "shared-mutex-busy", _gpuStereoCaptureSerial, -1,
                _gpuStereoCaptureState.ToString());
            return false;
        }

        var released = false;
        try
        {
            var sw = Stopwatch.StartNew();
            var context = _device.ImmediateContext;
            context.OutputMerger.SetRenderTargets(_gpuStereoSharedRtv);
            context.Rasterizer.SetViewport(
                new Viewport(0, 0, source.Width * 2, source.Height, 0, 1));
            context.Rasterizer.State = _rasterizer;
            context.InputAssembler.PrimitiveTopology = PrimitiveTopology.TriangleList;
            context.InputAssembler.InputLayout = _inputLayout;
            if (_vertexBuffer is not null)
            {
                context.InputAssembler.SetVertexBuffers(
                    0,
                    new VertexBufferBinding(
                        _vertexBuffer,
                        System.Runtime.InteropServices.Marshal.SizeOf<VertexDx11>(),
                        0));
            }
            context.VertexShader.Set(_vertexShader);
            context.PixelShader.Set(_gpuStereoComposePixelShader);
            context.PixelShader.SetSampler(0, _sampler);
            context.PixelShader.SetShaderResource(0, _gpuStereoLeftSrv);
            context.PixelShader.SetShaderResource(1, _gpuStereoRightSrv);
            context.Draw(FullScreenTriangle.Length, 0);
            context.PixelShader.SetShaderResource(0, null);
            context.PixelShader.SetShaderResource(1, null);
            context.Flush();
            sw.Stop();
            composeMs = sw.Elapsed.TotalMilliseconds;

            _xrSharedMutex.Release(1);
            released = true;

            var publish = Stopwatch.StartNew();
            _gpuPublisher.Publish(
                _xrSharedHandle,
                source.Width * 2,
                source.Height,
                source.Format);
            publish.Stop();
            publishMs = publish.Elapsed.TotalMilliseconds;

            // Restore the PC render state immediately; this is also the exact
            // v0.13.35 viewport guard that prevented the black-area regression.
            if (_renderTarget is not null)
                context.OutputMerger.SetRenderTargets(_renderTarget);
            context.Rasterizer.SetViewport(
                new Viewport(
                    0, 0,
                    Math.Max(2, ClientSize.Width),
                    Math.Max(2, ClientSize.Height),
                    0, 1));
            context.PixelShader.Set(_pixelShader);
            return true;
        }
        finally
        {
            if (!released)
            {
                try { _xrSharedMutex.Release(0); } catch { }
            }
        }
    }

    private void DisposeGpuStereoResourcesLocked()
    {
        _gpuStereoLeftSrv?.Dispose();
        _gpuStereoRightSrv?.Dispose();
        _gpuStereoLeftTexture?.Dispose();
        _gpuStereoRightTexture?.Dispose();
        _gpuStereoSharedRtv?.Dispose();
        _gpuStereoComposePixelShader?.Dispose();
        _gpuStereoLeftSrv = null;
        _gpuStereoRightSrv = null;
        _gpuStereoLeftTexture = null;
        _gpuStereoRightTexture = null;
        _gpuStereoSharedRtv = null;
        _gpuStereoComposePixelShader = null;
    }
}
'''
Path("pc/MainFormV139.GpuStereo.cs").write_text(host, encoding="utf-8")


# ---------------------------------------------------------------------------
# 5) Host bridge and shutdown integration.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
main = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.39-gpu-fullframe-sbs',
    main,
    count=1)
main = main.replace("GeoGebraForQuest PC v0.13.36", "GeoGebraForQuest PC v0.13.39")
main = main.replace("v0.13.36", "v0.13.39")

bridge_marker = "                setDepthPointerActive: function () {},\n"
require(main, bridge_marker, "v0.13.39 QuestBridge insertion marker missing")
main = main.replace(
    bridge_marker,
    "                gpuStereoPairReady: function (payload) {\n"
    "                  post({ type: 'gpuStereoPairReady', payload: String(payload || '') });\n"
    "                },\n"
    "                gpuStereoEyePresented: function (payload) {\n"
    "                  post({ type: 'gpuStereoEyePresented', payload: String(payload || '') });\n"
    "                },\n"
    "                gpuStereoDiag: function (payload) {\n"
    "                  post({ type: 'gpuStereoDiag', payload: String(payload || '') });\n"
    "                },\n" + bridge_marker,
    1)

switch_marker = '                case "runtimeError":\n'
require(main, switch_marker, "v0.13.39 JS message switch marker missing")
main = main.replace(
    switch_marker,
    '                case "gpuStereoPairReady":\n'
    '                    HandleGpuStereoPairReady(root);\n'
    '                    break;\n'
    '                case "gpuStereoEyePresented":\n'
    '                    HandleGpuStereoEyePresented(root);\n'
    '                    break;\n'
    '                case "gpuStereoDiag":\n'
    '                    HandleGpuStereoDiag(root);\n'
    '                    break;\n' + switch_marker,
    1)

# v0.13.36 inserted LogBundle.Create immediately after host telemetry closes.
shutdown_bundle = "        _performanceTelemetry.Dispose();\n        LogBundle.Create();\n"
require(main, shutdown_bundle, "v0.13.39 log bundle shutdown marker missing")
main = main.replace(
    shutdown_bundle,
    "        _performanceTelemetry.Dispose();\n"
    "        _gpuStereoTelemetry.Dispose();\n"
    "        LogBundle.Create();\n",
    1)

# Dispose host-owned eye/full-SBS helper resources while the D3D lock is held.
d3d_shutdown = "        lock (_d3dLock)\n        {\n"
idx = main.find(d3d_shutdown, main.find("private void Shutdown()"))
if idx < 0:
    raise SystemExit("v0.13.39 D3D shutdown lock missing")
insert_at = idx + len(d3d_shutdown)
main = main[:insert_at] + "            DisposeGpuStereoResourcesLocked();\n" + main[insert_at:]

# Human-readable title only; no old B-panel wording in this architecture.
main = main.replace("XR Behind Native", "GPU Full-SBS")
main = main.replace("B bekleniyor", "A_L|A_R bekleniyor")
p.write_text(main, encoding="utf-8")


# ---------------------------------------------------------------------------
# 6) Accelerated paint: classify full-window LEFT/RIGHT GPU phases. Normal paint
# only updates the PC texture; OpenXR publication happens only after both eyes.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.Graphics.cs")
graphics = p.read_text(encoding="utf-8")
start = graphics.find("    public void OnAcceleratedPaint(")
end = graphics.find("    private void EnsurePcTextureLocked(", start)
if start < 0 or end < 0:
    raise SystemExit("v0.13.39 OnAcceleratedPaint bounds missing")

new_paint = r'''    public void OnAcceleratedPaint(
        PaintElementType type,
        Rect dirtyRect,
        AcceleratedPaintInfo acceleratedPaintInfo)
    {
        if (_closing || type != PaintElementType.View ||
            _device is null || _device1 is null) return;

        var normalPaint = false;
        try
        {
            lock (_d3dLock)
            {
                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                if (TryConsumeGpuStereoPaintLocked(cefTexture))
                {
                    return;
                }

                // Ordinary browser paint. This is the PC-visible A/right-eye
                // baseline only; it is NOT sent to XR as a stereo frame.
                EnsurePcTextureLocked(cefTexture.Description);
                var next = _currentPcTexture ^ 1;
                var target = _pcTextures[next];
                if (target is null) return;

                _device.ImmediateContext.CopyResource(cefTexture, target);
                _currentPcTexture = next;
                var frame = Interlocked.Increment(ref _gpuFrameNumber);
                normalPaint = true;

                if ((frame % 120) == 0)
                {
                    BeginInvokeSafe(UpdateWindowTitle);
                }
            }
        }
        catch (Exception ex)
        {
            if (!_closing)
            {
                _gpuPaintStatus = "GPU paint: " + ShortError(ex);
                _gpuStereoTelemetry.Event("accelerated-paint-error", detail: ex.Message);
                BeginInvokeSafe(UpdateWindowTitle);
            }
        }
        finally
        {
            if (normalPaint) ScheduleGpuStereoUiExport();
        }
    }

'''
graphics = graphics[:start] + new_paint + graphics[end:]

# Native/CEF popup no longer disables stereo. Full browser A_L/A_R composition
# keeps DOM/UI above the 3D canvas; temporary eye phases never hit the PC.
graphics = graphics.replace(
    "    public void OnPopupShow(bool show)\n    {\n        SetStereoUiSuspended(show);\n    }",
    "    public void OnPopupShow(bool show)\n    {\n        _gpuStereoTelemetry.Event(show ? \"cef-popup-show\" : \"cef-popup-hide\");\n    }",
    1)

p.write_text(graphics, encoding="utf-8")


# ---------------------------------------------------------------------------
# 7) XR: the existing GPU mapping now carries COMPLETE [A_L | A_R]. No CPU B
# MMF is read/uploaded. Existing single-panel RenderEye already samples the left
# or right half of sbsSrv, so feed it the shared full-SBS texture directly.
# ---------------------------------------------------------------------------
p = Path("pc-xr/main-v11.cpp")
xr = p.read_text(encoding="utf-8")

xr = xr.replace(
    "        const int width = std::max(1, baseTexture_.Width());\n"
    "        const int height = std::max(1, baseTexture_.Height());",
    "        // v0.13.39 baseTexture_ is [A_L|A_R], so one logical application\n"
    "        // eye is exactly half of the shared GPU texture width.\n"
    "        const int width = std::max(1, baseTexture_.Width() / 2);\n"
    "        const int height = std::max(1, baseTexture_.Height());",
    1)

sbs_start = xr.find("        SbsSnapshot sbsUpdate{};")
sbs_end = xr.find("\n    }\n\n    void RenderFrame()", sbs_start)
if sbs_start < 0 or sbs_end < 0:
    raise SystemExit("v0.13.39 XR legacy SBS refresh block missing")
xr = (
    xr[:sbs_start] +
    "        // v0.13.39: no CPU stereo MMF/read/upload path. Full A_L|A_R\n"
    "        // arrives through the GPU shared-texture publisher above.\n" +
    xr[sbs_end:]
)

compose_start = xr.find("                ID3D11ShaderResourceView* fullSbsSrv = nullptr;")
compose_end = xr.find("\n                float cursorX = 0.0f;", compose_start)
if compose_start < 0 or compose_end < 0:
    raise SystemExit("v0.13.39 XR FullSbsComposer block missing")
xr = (
    xr[:compose_start] +
    "                // Host already produced the complete [A_L|A_R] texture.\n"
    "                ID3D11ShaderResourceView* fullSbsSrv =\n"
    "                    (!showSplash && baseTexture_.Valid())\n"
    "                        ? baseTexture_.Srv() : nullptr;\n" +
    xr[compose_end:]
)

# Startup/periodic wording: this mapping is no longer plain A.
xr = xr.replace("A GPU frame consumed seq=", "FULL-SBS GPU frame consumed seq=")
xr = re.sub(
    r'Log\("GeoGebraForQuest PC v0\.11 initialized: [^"\n]*"\);',
    'Log("GeoGebraForQuest PC v0.13.39 initialized: GPU [A_L|A_R] full-window SBS -> OpenXR; no CPU framebuffer path");',
    xr,
    count=1)
p.write_text(xr, encoding="utf-8")

# RenderEye must already be the v0.13.27+ one-panel half sampler.
render = Path("pc-xr/v11-render.hpp").read_text(encoding="utf-8")
require(render, "if (sbsSrv)", "v0.13.39 requires one-panel full-SBS RenderEye")
require(render, "rightEye ? 0.5f : 0.0f",
        "v0.13.39 requires physical-eye half selection")


# ---------------------------------------------------------------------------
# 8) Release/version labels and a clean build script. Old generated validation
# guards intentionally describe JPEG/raw/B architecture and are not reused.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.13.39</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.13.39.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.13.39.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

build = r'''param(
    [switch]$FrameworkDependent
)

$ErrorActionPreference = "Stop"
$pcDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $pcDir
$xrSource = Join-Path $root "pc-xr"
$xrBuild = Join-Path $root ".pc-xr-build"
$project = Join-Path $pcDir "GeoGebraForQuest.PC.csproj"
$distRoot = Join-Path $root "dist"
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.13.39-gpu-fullframe-sbs-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$boot = Join-Path $root "app\src\main\assets\web\GeoGebra\web3d\web3d.nocache.js"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw ".NET 8 SDK bulunamadı." }
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { throw "CMake bulunamadı." }
if (-not (Test-Path $boot)) { throw "Patched GeoGebra Web3D paketi bulunamadı." }

$runtime = Get-Content (Join-Path $pcDir "pc-stereo-layout.js") -Raw
$main = Get-Content (Join-Path $pcDir "MainFormV11.cs") -Raw
$graphics = Get-Content (Join-Path $pcDir "MainFormV11.Graphics.cs") -Raw
$gpuHost = Get-Content (Join-Path $pcDir "MainFormV139.GpuStereo.cs") -Raw
$gpuTelemetry = Get-Content (Join-Path $pcDir "GpuStereoTelemetry.cs") -Raw
$xr = Get-Content (Join-Path $xrSource "main-v11.cpp") -Raw
$render = Get-Content (Join-Path $xrSource "v11-render.hpp") -Raw
$index = Get-Content (Join-Path $root "app\src\main\assets\web\index.html") -Raw
$meta = Get-Content (Join-Path $root "app\src\main\assets\web\GeoGebra\GGQ_SOURCE_BUILD.txt") -Raw

if ($runtime -match "getImageData|readPixels|toBlob|stereoRawPair|Base64") {
    throw "v0.13.39: CPU/browser pixel transport leaked into PC runtime."
}
if (-not $runtime.Contains("__ggqPcGpuFullFrameSbsV01339")) { throw "geometry-only runtime missing" }
if (-not $index.Contains("ggq-gpu-fullframe-sbs-v01339")) { throw "GPU FBO bridge missing" }
if (-not $index.Contains("framebufferTexture2D")) { throw "eye FBO texture target missing" }
if ($index.Contains("width * 2, height") -or $index.Contains("width*2,height")) {
    throw "v0.13.39: forbidden 2W WebGL presentation detected."
}
if (-not $gpuHost.Contains("CaptureLeftPaint") -or -not $gpuHost.Contains("CaptureRightPaint")) {
    throw "full-window GPU phase state machine missing"
}
if (-not $gpuHost.Contains("A_L|A_R GPU") -or -not $gpuHost.Contains("SharedKeyedmutex")) {
    throw "host full-SBS shared GPU publication missing"
}
if (-not $gpuTelemetry.Contains("Performance.GPU.csv") -or -not $gpuTelemetry.Contains("Performance.GPUJS.jsonl")) {
    throw "GPU diagnostics missing"
}
if (-not $main.Contains("gpuStereoPairReady") -or -not $main.Contains("LogBundle.Create();")) {
    throw "host bridge/log bundle integration missing"
}
if (-not $xr.Contains("baseTexture_.Width() / 2") -or -not $xr.Contains("Full-SBS GPU frame consumed")) {
    throw "XR full-SBS geometry path missing"
}
if (-not $render.Contains("rightEye ? 0.5f : 0.0f")) { throw "XR physical-eye half sampler missing" }
if (-not $meta.Contains("pc_gpu_renderer=v0.13.39")) { throw "custom GeoGebra source metadata missing" }
if (-not $meta.Contains("visible_webgl_backing=W_x_H")) { throw "W x H visible backing invariant missing" }
if (-not $meta.Contains("eye_fbos=LEFT_W_x_H_x0;RIGHT_W_x_H_x0")) { throw "eye FBO invariant missing" }

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.13.39] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.13.39] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }
Write-Host "[GGQ-PC v0.13.39] CEF/Windows app publish..."
& dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained $selfContained `
    -o $appPublish `
    -p:Platform=x64 `
    -p:PublishReadyToRun=true
if ($LASTEXITCODE -ne 0) { throw "dotnet publish başarısız." }

Copy-Item (Join-Path $appPublish "*") $publishDir -Recurse -Force
$xrOut = Join-Path $publishDir "xr"
New-Item -ItemType Directory -Force -Path $xrOut | Out-Null
$xrExe = Get-ChildItem -Path $xrBuild -Filter "GeoGebraForQuestPC.XR.exe" -Recurse | Select-Object -First 1
if (-not $xrExe) { throw "GeoGebraForQuestPC.XR.exe bulunamadı." }
Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force
$loader = Get-ChildItem -Path $xrBuild -Filter "openxr_loader.dll" -Recurse | Select-Object -First 1
if ($loader) { Copy-Item $loader.FullName (Join-Path $xrOut "openxr_loader.dll") -Force }

if (-not (Test-Path (Join-Path $publishDir "GeoGebraForQuestPC.exe"))) { throw "Main EXE missing" }
if (-not (Test-Path (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe"))) { throw "XR EXE missing" }
if (-not (Test-Path (Join-Path $publishDir "assets\web\GeoGebra\GGQ_SOURCE_BUILD.txt"))) {
    throw "GGQ_SOURCE_BUILD.txt missing"
}

Write-Host "[GGQ-PC v0.13.39] BUILD TAMAM"
Write-Host "GPU: W x H LEFT/RIGHT FBO -> full A_L/A_R CEF GPU frames -> native [A_L|A_R] -> OpenXR"
Write-Host "CPU PIXELS: none"
Write-Host "LOG: shutdown creates log.zip including Host/JS/XR/GPU/GPUJS telemetry"
'''
Path("pc/build.ps1").write_text(build, encoding="utf-8")


# ---------------------------------------------------------------------------
# 9) Final invariants.
# ---------------------------------------------------------------------------
checks = {
    "pc/pc-stereo-layout.js": ["__ggqPcGpuFullFrameSbsV01339", "mode:'gpu-fullframe-sbs-v01339'"],
    "pc/MainFormV11.cs": ["gpuStereoPairReady", "gpuStereoEyePresented", "_gpuStereoTelemetry.Dispose();", "LogBundle.Create();"],
    "pc/MainFormV11.Graphics.cs": ["TryConsumeGpuStereoPaintLocked", "ScheduleGpuStereoUiExport"],
    "pc/MainFormV139.GpuStereo.cs": ["CaptureLeftPaint", "CaptureRightPaint", "ComposeAndPublishGpuFullSbsLocked", "SharedKeyedmutex"],
    "pc/GpuStereoTelemetry.cs": ["GeoGebraForQuestPC.Performance.GPU.csv", "GeoGebraForQuestPC.Performance.GPUJS.jsonl"],
    "pc-xr/main-v11.cpp": ["baseTexture_.Width() / 2", "Full-SBS GPU frame consumed"],
    "pc-xr/v11-render.hpp": ["rightEye ? 0.5f : 0.0f"],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding="utf-8")
    for needle in needles:
        require(text, needle, f"v0.13.39 final invariant missing in {file}: {needle}")

for file in ("pc/pc-stereo-layout.js", "pc/MainFormV139.GpuStereo.cs"):
    text = Path(file).read_text(encoding="utf-8")
    for forbidden in ("getImageData", "readPixels", "toBlob", "stereoRawPair"):
        if forbidden in text:
            raise SystemExit(f"v0.13.39 CPU pixel path leaked into {file}: {forbidden}")

print("GeoGebraForQuest PC v0.13.39 GPU full-window A_L/A_R architecture applied")
