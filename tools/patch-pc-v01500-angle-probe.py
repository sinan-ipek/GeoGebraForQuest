#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.15.0 — ANGLE direct-texture capability probe.

This is deliberately NOT a new stereo transport.  It starts from the proven
v0.13.35 architecture and leaves A/B presentation and the CPU stereo path
unchanged.  The only runtime addition is a passive capability probe that waits
for the proven LEFT/RIGHT renderer canvases, inspects their already-created
contexts, and writes the result to GeoGebraForQuestPC.ANGLE-Probe.json.

The probe answers the questions needed before we build a custom CEF/Chromium
bridge for native D3D11 shared textures:
  * Are the LEFT/RIGHT renderer canvases WebGL1, WebGL2, or 2D?
  * Which ANGLE renderer/backend is actually active on the test machine?
  * What are the drawing-buffer dimensions and context capabilities?
  * Does an experimental texImage2DShared entry point already exist? (Expected
    false with stock CEF; this is the future custom bridge target.)

No getImageData/readPixels path is added by this patch and no canvas is made
visible.  The v0.13.35 stereo behavior remains the correctness baseline.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) JS capability probe: append a self-contained passive IIFE to the proven
#    runtime. It only asks for a context type that already exists on the two
#    known renderer canvases; requesting a mismatched type returns null.
# ---------------------------------------------------------------------------
p = Path("pc/pc-stereo-layout.js")
s = p.read_text(encoding="utf-8")

req(
    s,
    "document.getElementById('ggq-renderer-left-eye')",
    "v0.15.0 probe: LEFT renderer canvas marker missing",
)
req(
    s,
    "document.getElementById('ggq-renderer-right-eye')",
    "v0.15.0 probe: RIGHT renderer canvas marker missing",
)

if "__ggqAngleDirectTextureProbeV150" not in s:
    probe = r'''

// ---------------------------------------------------------------------------
// GGQ v0.15.0 ANGLE direct-texture capability probe.
// Passive only: no pixels are read, copied, encoded, or presented.
// ---------------------------------------------------------------------------
;(function () {
  'use strict';
  if (window.__ggqAngleDirectTextureProbeV150) return;
  window.__ggqAngleDirectTextureProbeV150 = true;

  var startedAt = performance.now();
  var attempts = 0;
  var finished = false;
  var MAX_WAIT_MS = 20000;

  function safeValue(fn, fallback) {
    try { return fn(); } catch (_) { return fallback; }
  }

  function postReport(report) {
    var payload = JSON.stringify(report);
    try {
      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
        window.CefSharp.PostMessage({ type: 'angleDirectProbe', payload: payload });
        return true;
      }
      if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
        window.cefSharp.postMessage({ type: 'angleDirectProbe', payload: payload });
        return true;
      }
    } catch (_) {}
    return false;
  }

  function inspectGl(gl, type) {
    var out = {
      contextType: type,
      drawingBufferWidth: Number(gl.drawingBufferWidth || 0),
      drawingBufferHeight: Number(gl.drawingBufferHeight || 0),
      contextAttributes: safeValue(function () { return gl.getContextAttributes(); }, null),
      version: safeValue(function () { return String(gl.getParameter(gl.VERSION) || ''); }, ''),
      shadingLanguageVersion: safeValue(function () {
        return String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION) || '');
      }, ''),
      vendor: safeValue(function () { return String(gl.getParameter(gl.VENDOR) || ''); }, ''),
      renderer: safeValue(function () { return String(gl.getParameter(gl.RENDERER) || ''); }, ''),
      maxTextureSize: safeValue(function () { return Number(gl.getParameter(gl.MAX_TEXTURE_SIZE) || 0); }, 0),
      maxRenderbufferSize: safeValue(function () {
        return Number(gl.getParameter(gl.MAX_RENDERBUFFER_SIZE) || 0);
      }, 0),
      framebufferBound: safeValue(function () {
        return gl.getParameter(gl.FRAMEBUFFER_BINDING) ? true : false;
      }, false),
      texture2DBound: safeValue(function () {
        return gl.getParameter(gl.TEXTURE_BINDING_2D) ? true : false;
      }, false),
      hasTexImage2DShared: typeof gl.texImage2DShared === 'function',
      supportedExtensions: safeValue(function () {
        var list = gl.getSupportedExtensions();
        return Array.isArray(list) ? list.slice().sort() : [];
      }, [])
    };

    var dbg = safeValue(function () { return gl.getExtension('WEBGL_debug_renderer_info'); }, null);
    if (dbg) {
      out.unmaskedVendor = safeValue(function () {
        return String(gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) || '');
      }, '');
      out.unmaskedRenderer = safeValue(function () {
        return String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || '');
      }, '');
    } else {
      out.unmaskedVendor = '';
      out.unmaskedRenderer = '';
    }

    if (type === 'webgl2') {
      out.maxSamples = safeValue(function () { return Number(gl.getParameter(gl.MAX_SAMPLES) || 0); }, 0);
      out.readBuffer = safeValue(function () { return Number(gl.getParameter(gl.READ_BUFFER) || 0); }, 0);
    }
    return out;
  }

  function inspectCanvas(canvas, label) {
    if (!canvas) return { label: label, exists: false };

    var result = {
      label: label,
      exists: true,
      id: String(canvas.id || ''),
      width: Number(canvas.width || 0),
      height: Number(canvas.height || 0),
      clientWidth: Number(canvas.clientWidth || 0),
      clientHeight: Number(canvas.clientHeight || 0),
      connected: !!canvas.isConnected,
      display: safeValue(function () { return String(getComputedStyle(canvas).display || ''); }, ''),
      visibility: safeValue(function () { return String(getComputedStyle(canvas).visibility || ''); }, ''),
      offscreenTransferAvailable: typeof canvas.transferControlToOffscreen === 'function',
      imageBitmapTransferAvailable: typeof canvas.transferToImageBitmap === 'function'
    };

    var ctx = null;
    var type = '';
    var types = ['webgl2', 'webgl', 'experimental-webgl', '2d'];
    for (var i = 0; i < types.length; i++) {
      var candidate = safeValue(function () { return canvas.getContext(types[i]); }, null);
      if (candidate) {
        ctx = candidate;
        type = types[i] === 'experimental-webgl' ? 'webgl' : types[i];
        break;
      }
    }

    result.contextType = type || 'unknown';
    if (ctx && (type === 'webgl' || type === 'webgl2')) {
      result.gl = inspectGl(ctx, type);
    } else if (ctx && type === '2d') {
      result.twoD = {
        alpha: safeValue(function () {
          var a = ctx.getContextAttributes && ctx.getContextAttributes();
          return a && typeof a.alpha === 'boolean' ? a.alpha : null;
        }, null)
      };
    }
    return result;
  }

  function browserFacts() {
    return {
      userAgent: String(navigator.userAgent || ''),
      platform: String(navigator.platform || ''),
      hardwareConcurrency: Number(navigator.hardwareConcurrency || 0),
      devicePixelRatio: Number(window.devicePixelRatio || 1),
      crossOriginIsolated: !!window.crossOriginIsolated,
      webglRenderingContextAvailable: typeof window.WebGLRenderingContext === 'function',
      webgl2RenderingContextAvailable: typeof window.WebGL2RenderingContext === 'function',
      offscreenCanvasAvailable: typeof window.OffscreenCanvas === 'function',
      webGpuExposed: !!navigator.gpu,
      ggqRequestStereoFrame: typeof window.ggqRequestStereoFrame === 'function',
      ggqGetStereoFrameSerial: typeof window.ggqGetStereoFrameSerial === 'function'
    };
  }

  function tick() {
    if (finished) return;
    attempts++;

    var left = document.getElementById('ggq-renderer-left-eye');
    var right = document.getElementById('ggq-renderer-right-eye');
    var elapsed = Math.max(0, performance.now() - startedAt);
    var bothReady = !!(
      left && right &&
      Number(left.width || 0) >= 2 && Number(left.height || 0) >= 2 &&
      Number(right.width || 0) >= 2 && Number(right.height || 0) >= 2
    );

    if (!bothReady && elapsed < MAX_WAIT_MS) {
      setTimeout(tick, 250);
      return;
    }

    finished = true;
    var report = {
      probe: 'GGQ-v0.15.0-angle-direct-texture',
      schema: 1,
      success: bothReady,
      elapsedMs: elapsed,
      attempts: attempts,
      browser: browserFacts(),
      left: inspectCanvas(left, 'LEFT_EYE'),
      right: inspectCanvas(right, 'RIGHT_EYE')
    };

    if (report.left && report.right && report.left.gl && report.right.gl) {
      report.sameContextObject = false;
      report.sameDrawingBufferSize =
        report.left.gl.drawingBufferWidth === report.right.gl.drawingBufferWidth &&
        report.left.gl.drawingBufferHeight === report.right.gl.drawingBufferHeight;
    }

    postReport(report);
  }

  setTimeout(tick, 250);
})();
'''
    s += probe

p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Host: accept the one small JSON telemetry message and persist it.  No pixel
#    data flows through this message.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")

switch_marker = '                case "runtimeError":\n'
req(main, switch_marker, "v0.15.0 probe: Javascript message switch marker missing")
if 'case "angleDirectProbe":' not in main:
    main = main.replace(
        switch_marker,
        '                case "angleDirectProbe":\n'
        '                    if (root.TryGetProperty("payload", out var probePayload))\n'
        '                        SaveAngleDirectTextureProbe(probePayload.GetString());\n'
        '                    break;\n' + switch_marker,
        1,
    )

main = re.sub(
    r'(pc-stereo-layout\\.js\\?v=)[^\"\']+',
    r'\g<1>0.15.0-angle-direct-texture-probe',
    main,
    count=1,
)
main = main.replace("GeoGebraForQuest PC v0.13.35", "GeoGebraForQuest PC v0.15.0 PROBE")
main = main.replace("v0.13.35 ·", "v0.15.0 PROBE ·")
main = main.replace("0.13.35-correct-lr", "0.15.0-angle-direct-texture-probe")
p.write_text(main, encoding="utf-8")

probe_cs = r'''using System.Text.Json;
using SharpDX.Direct3D11;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private readonly object _angleDirectProbeLock = new();

    private void SaveAngleDirectTextureProbe(string? payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return;

        try
        {
            using var document = JsonDocument.Parse(payload);
            var js = document.RootElement.Clone();

            string adapterName = "";
            int vendorId = 0;
            int deviceId = 0;
            string featureLevel = "";

            try
            {
                if (_device is not null)
                {
                    featureLevel = _device.FeatureLevel.ToString();
                    using var dxgiDevice = _device.QueryInterface<SharpDX.DXGI.Device>();
                    using var adapter = dxgiDevice.Adapter;
                    var desc = adapter.Description;
                    adapterName = desc.Description?.Trim() ?? "";
                    vendorId = desc.VendorId;
                    deviceId = desc.DeviceId;
                }
            }
            catch
            {
                // Probe persistence must never affect the proven renderer.
            }

            var report = new
            {
                capturedAtUtc = DateTimeOffset.UtcNow,
                application = "GeoGebraForQuest PC v0.15.0 ANGLE direct-texture probe",
                baseline = "v0.13.35-working-depth",
                forcedAngleBackend = "d3d11",
                host = new
                {
                    processId = Environment.ProcessId,
                    os = Environment.OSVersion.ToString(),
                    is64BitProcess = Environment.Is64BitProcess,
                    d3dFeatureLevel = featureLevel,
                    adapter = adapterName,
                    vendorId,
                    deviceId
                },
                javascript = js
            };

            var json = JsonSerializer.Serialize(
                report,
                new JsonSerializerOptions { WriteIndented = true });
            var path = Path.Combine(
                AppContext.BaseDirectory,
                "GeoGebraForQuestPC.ANGLE-Probe.json");

            lock (_angleDirectProbeLock)
            {
                File.WriteAllText(path, json);
            }

            _cefPageText = "ANGLE probe yazıldı";
            BeginInvokeSafe(UpdateWindowTitle);
        }
        catch (Exception ex)
        {
            _cefPageText = "ANGLE probe: " + ShortError(ex);
            BeginInvokeSafe(UpdateWindowTitle);
        }
    }
}
'''
Path("pc/MainFormV15.AngleDirectProbe.cs").write_text(probe_cs, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Version/package label only. The rendering architecture stays v0.13.35.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.15.0</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.15.0.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.15.0.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

p = Path("pc/build.ps1")
build = p.read_text(encoding="utf-8")
build = build.replace(
    "GeoGebraForQuest-PC-v0.13.35-correct-lr-win-x64",
    "GeoGebraForQuest-PC-v0.15.0-angle-direct-texture-probe-win-x64",
)
build = build.replace("0.13.35-correct-lr", "0.15.0-angle-direct-texture-probe")
build = build.replace(r"0\.13\.35-correct-lr", r"0\.15\.0-angle-direct-texture-probe")
build = build.replace("v0.13.35", "v0.15.0")
build = build.replace(r"v0\.13\.35", r"v0\.15\.0")
p.write_text(build, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Guard the experiment.  This release MUST still contain the proven CPU path;
#    that is intentional because this is a capability probe, not the new transport.
# ---------------------------------------------------------------------------
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
main = Path("pc/MainFormV11.cs").read_text(encoding="utf-8")
probe_host = Path("pc/MainFormV15.AngleDirectProbe.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

for text, needle, label in (
    (runtime, "type: 'stereoRawPair'", "proven v0.13.35 stereo path missing"),
    (runtime, "leftCaptureContext.getImageData", "proven LEFT CPU source missing"),
    (runtime, "rightCaptureContext.getImageData", "proven RIGHT CPU source missing"),
    (runtime, "__ggqAngleDirectTextureProbeV150", "JS probe missing"),
    (runtime, "hasTexImage2DShared", "custom-entry-point detection missing"),
    (main, 'case "angleDirectProbe":', "host probe message handler missing"),
    (probe_host, "GeoGebraForQuestPC.ANGLE-Probe.json", "probe file persistence missing"),
    (project, "<Version>0.15.0</Version>", "probe project version missing"),
    (build, "v0.15.0-angle-direct-texture-probe", "probe package label missing"),
):
    req(text, needle, "v0.15.0 probe: " + label)

for forbidden in (
    "ggq-gpu-stereo-stage-v0141",
    "GpuStereoV141State",
    "StereoGpuTexturePublisher",
):
    if forbidden in runtime or forbidden in main or forbidden in probe_host:
        raise SystemExit("v0.15.0 probe contaminated by abandoned v0.14 staging path: " + forbidden)

print("GeoGebraForQuest PC v0.15.0 ANGLE direct-texture capability probe applied")
