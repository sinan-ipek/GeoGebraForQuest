#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.15.1 — active WebGL stereo-source probe.

Applied after v0.15.0.  The v0.15.0 passive probe proved that waiting for the
renderer-eye DOM ids is not sufficient: the Exp46 GeoGebra renderer creates the
LEFT snapshot and aliases the RIGHT source only when a full stereo pair is
explicitly requested.

v0.15.1 therefore performs exactly one demand-driven ggqRequestStereoFrame()
request, waits for ggqGetStereoFrameSerial() to advance, then inspects the
actual sources created by the proven renderer:

  LEFT  = hidden 2D snapshot canvas
  RIGHT = GeoGebra's live main WebGL canvas (v0.9.20 alias)

No pixels are read. No transport or compositor code is changed.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) JS: actively request one proven stereo pair, wait for its serial, then
#    inspect the actual RIGHT_EYE WebGL canvas and LEFT_EYE 2D snapshot.
# ---------------------------------------------------------------------------
p = Path("pc/pc-stereo-layout.js")
s = p.read_text(encoding="utf-8")

for needle, label in (
    ("window.ggqRequestStereoFrame", "stereo request hook missing"),
    ("window.ggqGetStereoFrameSerial", "stereo serial hook missing"),
    ("document.getElementById('ggq-renderer-left-eye')", "LEFT source lookup missing"),
    ("document.getElementById('ggq-renderer-right-eye')", "RIGHT source lookup missing"),
):
    req(s, needle, "v0.15.1: " + label)

if "__ggqWebGlSourceProbeV151" not in s:
    s += r'''

// ---------------------------------------------------------------------------
// GGQ v0.15.1 active WebGL stereo-source probe.
// It requests one normal renderer-owned stereo pair and reads metadata only.
// ---------------------------------------------------------------------------
;(function () {
  'use strict';
  if (window.__ggqWebGlSourceProbeV151) return;
  window.__ggqWebGlSourceProbeV151 = true;

  var startedAt = performance.now();
  var MAX_WAIT_MS = 20000;
  var attempts = 0;
  var requestAttempts = 0;
  var requestedAt = 0;
  var baselineSerial = null;
  var completedSerial = null;
  var finished = false;

  function safe(fn, fallback) {
    try { return fn(); } catch (_) { return fallback; }
  }

  function post(report) {
    var payload = JSON.stringify(report);
    try {
      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
        window.CefSharp.PostMessage({ type: 'webglSourceProbe', payload: payload });
        return true;
      }
      if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
        window.cefSharp.postMessage({ type: 'webglSourceProbe', payload: payload });
        return true;
      }
    } catch (_) {}
    return false;
  }

  function glFacts(gl, contextType) {
    var out = {
      contextType: contextType,
      drawingBufferWidth: Number(gl.drawingBufferWidth || 0),
      drawingBufferHeight: Number(gl.drawingBufferHeight || 0),
      isContextLost: safe(function () { return !!gl.isContextLost(); }, false),
      contextAttributes: safe(function () { return gl.getContextAttributes(); }, null),
      version: safe(function () { return String(gl.getParameter(gl.VERSION) || ''); }, ''),
      shadingLanguageVersion: safe(function () {
        return String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION) || '');
      }, ''),
      vendor: safe(function () { return String(gl.getParameter(gl.VENDOR) || ''); }, ''),
      renderer: safe(function () { return String(gl.getParameter(gl.RENDERER) || ''); }, ''),
      maxTextureSize: safe(function () { return Number(gl.getParameter(gl.MAX_TEXTURE_SIZE) || 0); }, 0),
      maxRenderbufferSize: safe(function () {
        return Number(gl.getParameter(gl.MAX_RENDERBUFFER_SIZE) || 0);
      }, 0),
      framebufferBindingIsDefault: safe(function () {
        return gl.getParameter(gl.FRAMEBUFFER_BINDING) === null;
      }, false),
      viewport: safe(function () {
        var v = gl.getParameter(gl.VIEWPORT);
        return v ? Array.prototype.slice.call(v) : [];
      }, []),
      hasTexImage2DShared: typeof gl.texImage2DShared === 'function',
      supportedExtensions: safe(function () {
        var list = gl.getSupportedExtensions();
        return Array.isArray(list) ? list.slice().sort() : [];
      }, [])
    };

    var dbg = safe(function () { return gl.getExtension('WEBGL_debug_renderer_info'); }, null);
    out.webglDebugRendererInfoAvailable = !!dbg;
    out.unmaskedVendor = dbg ? safe(function () {
      return String(gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) || '');
    }, '') : '';
    out.unmaskedRenderer = dbg ? safe(function () {
      return String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || '');
    }, '') : '';
    return out;
  }

  function inspectCanvas(canvas, label) {
    if (!canvas) return { label: label, exists: false };

    var out = {
      label: label,
      exists: true,
      id: String(canvas.id || ''),
      constructorName: safe(function () { return String(canvas.constructor.name || ''); }, ''),
      width: Number(canvas.width || 0),
      height: Number(canvas.height || 0),
      clientWidth: Number(canvas.clientWidth || 0),
      clientHeight: Number(canvas.clientHeight || 0),
      connected: !!canvas.isConnected,
      display: safe(function () { return String(getComputedStyle(canvas).display || ''); }, ''),
      visibility: safe(function () { return String(getComputedStyle(canvas).visibility || ''); }, ''),
      rect: safe(function () {
        var r = canvas.getBoundingClientRect();
        return { left: r.left, top: r.top, width: r.width, height: r.height };
      }, null)
    };

    // Asking a canvas for a different context type after one is already created
    // returns null; it does not replace the renderer's existing context.
    var gl2 = safe(function () { return canvas.getContext('webgl2'); }, null);
    var gl1 = gl2 ? null : safe(function () { return canvas.getContext('webgl'); }, null);
    if (!gl1 && !gl2) {
      gl1 = safe(function () { return canvas.getContext('experimental-webgl'); }, null);
    }

    if (gl2) {
      out.contextType = 'webgl2';
      out.gl = glFacts(gl2, 'webgl2');
      return out;
    }
    if (gl1) {
      out.contextType = 'webgl';
      out.gl = glFacts(gl1, 'webgl');
      return out;
    }

    var ctx2d = safe(function () { return canvas.getContext('2d'); }, null);
    if (ctx2d) {
      out.contextType = '2d';
      out.twoD = {
        alpha: safe(function () {
          var attrs = ctx2d.getContextAttributes && ctx2d.getContextAttributes();
          return attrs && typeof attrs.alpha === 'boolean' ? attrs.alpha : null;
        }, null)
      };
    } else {
      out.contextType = 'unknown';
    }
    return out;
  }

  function listCanvases() {
    var nodes = safe(function () { return document.querySelectorAll('canvas'); }, []);
    var out = [];
    for (var i = 0; i < nodes.length; i++) {
      var c = nodes[i];
      out.push({
        index: i,
        id: String(c.id || ''),
        className: String(c.className || ''),
        width: Number(c.width || 0),
        height: Number(c.height || 0),
        clientWidth: Number(c.clientWidth || 0),
        clientHeight: Number(c.clientHeight || 0),
        display: safe(function () { return String(getComputedStyle(c).display || ''); }, ''),
        visibility: safe(function () { return String(getComputedStyle(c).visibility || ''); }, '')
      });
    }
    return out;
  }

  function finish(success, reason) {
    if (finished) return;
    finished = true;

    var left = document.getElementById('ggq-renderer-left-eye');
    var right = document.getElementById('ggq-renderer-right-eye');
    var report = {
      probe: 'GGQ-v0.15.1-webgl-source',
      schema: 1,
      success: !!success,
      reason: String(reason || ''),
      elapsedMs: Math.max(0, performance.now() - startedAt),
      attempts: attempts,
      requestAttempts: requestAttempts,
      requestedAtMs: requestedAt ? Math.max(0, requestedAt - startedAt) : null,
      baselineSerial: baselineSerial,
      completedSerial: completedSerial,
      frameLocation: String(location.href || ''),
      isTopFrame: window.top === window,
      browser: {
        userAgent: String(navigator.userAgent || ''),
        devicePixelRatio: Number(window.devicePixelRatio || 1),
        webgl1Exposed: typeof window.WebGLRenderingContext === 'function',
        webgl2Exposed: typeof window.WebGL2RenderingContext === 'function',
        webGpuExposed: !!navigator.gpu
      },
      left: inspectCanvas(left, 'LEFT_EYE'),
      right: inspectCanvas(right, 'RIGHT_EYE'),
      canvasInventory: listCanvases()
    };

    report.rightIsLiveWebGl = !!(report.right && report.right.gl);
    report.leftIsSnapshot2D = !!(report.left && report.left.contextType === '2d');
    post(report);
  }

  function tick() {
    if (finished) return;
    attempts++;
    var elapsed = Math.max(0, performance.now() - startedAt);
    if (elapsed >= MAX_WAIT_MS) {
      finish(false, baselineSerial === null ? 'request-unavailable' : 'serial-timeout');
      return;
    }

    if (baselineSerial === null) {
      if (typeof window.ggqRequestStereoFrame !== 'function' ||
          typeof window.ggqGetStereoFrameSerial !== 'function') {
        setTimeout(tick, 250);
        return;
      }
      requestAttempts++;
      var baseline = safe(function () { return Number(window.ggqRequestStereoFrame()); }, -1);
      if (!isFinite(baseline) || baseline < 0) {
        setTimeout(tick, 250);
        return;
      }
      baselineSerial = baseline;
      requestedAt = performance.now();
      setTimeout(tick, 16);
      return;
    }

    var serial = safe(function () { return Number(window.ggqGetStereoFrameSerial()); }, -1);
    if (isFinite(serial) && serial > baselineSerial) {
      completedSerial = serial;
      var left = document.getElementById('ggq-renderer-left-eye');
      var right = document.getElementById('ggq-renderer-right-eye');
      if (left && right) {
        finish(true, 'stereo-pair-completed');
        return;
      }
    }

    setTimeout(tick, 16);
  }

  setTimeout(tick, 250);
})();
'''

p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Host message + persistence. This carries JSON metadata only.
# ---------------------------------------------------------------------------
p = Path("pc/MainFormV11.cs")
main = p.read_text(encoding="utf-8")
switch_marker = '                case "runtimeError":\n'
req(main, switch_marker, "v0.15.1: Javascript message switch marker missing")
if 'case "webglSourceProbe":' not in main:
    main = main.replace(
        switch_marker,
        '                case "webglSourceProbe":\n'
        '                    if (root.TryGetProperty("payload", out var webglProbePayload))\n'
        '                        SaveWebGlSourceProbe(webglProbePayload.GetString());\n'
        '                    break;\n' + switch_marker,
        1,
    )

main = main.replace("GeoGebraForQuest PC v0.15.0 PROBE", "GeoGebraForQuest PC v0.15.1 WEBGL PROBE")
main = main.replace("v0.15.0 PROBE ·", "v0.15.1 WEBGL PROBE ·")
main = main.replace("0.15.0-angle-direct-texture-probe", "0.15.1-webgl-source-hook-probe")
p.write_text(main, encoding="utf-8")

probe_cs = r'''using System.Text.Json;

namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private readonly object _webGlSourceProbeLock = new();

    private void SaveWebGlSourceProbe(string? payload)
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
                // Probe persistence must never alter renderer behavior.
            }

            var report = new
            {
                capturedAtUtc = DateTimeOffset.UtcNow,
                application = "GeoGebraForQuest PC v0.15.1 WebGL source probe",
                baseline = "v0.13.35-working-depth",
                purpose = "Locate the live GeoGebra WebGL RIGHT_EYE source after one renderer-owned stereo pair",
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
                "GeoGebraForQuestPC.WebGL-Source-Probe.json");

            lock (_webGlSourceProbeLock)
            {
                File.WriteAllText(path, json);
            }

            _cefPageText = "WebGL source probe yazıldı";
            BeginInvokeSafe(UpdateWindowTitle);
        }
        catch (Exception ex)
        {
            _cefPageText = "WebGL source probe: " + ShortError(ex);
            BeginInvokeSafe(UpdateWindowTitle);
        }
    }
}
'''
Path("pc/MainFormV151.WebGlSourceProbe.cs").write_text(probe_cs, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Version/package labels.
# ---------------------------------------------------------------------------
p = Path("pc/GeoGebraForQuest.PC.csproj")
project = p.read_text(encoding="utf-8")
project = re.sub(r"<Version>[^<]+</Version>", "<Version>0.15.1</Version>", project, count=1)
project = re.sub(r"<FileVersion>[^<]+</FileVersion>", "<FileVersion>0.15.1.0</FileVersion>", project, count=1)
project = re.sub(r"<AssemblyVersion>[^<]+</AssemblyVersion>", "<AssemblyVersion>0.15.1.0</AssemblyVersion>", project, count=1)
p.write_text(project, encoding="utf-8")

p = Path("pc/build.ps1")
build = p.read_text(encoding="utf-8")
build = build.replace(
    "GeoGebraForQuest-PC-v0.15.0-angle-direct-texture-probe-win-x64",
    "GeoGebraForQuest-PC-v0.15.1-webgl-source-hook-probe-win-x64",
)
build = build.replace("0.15.0-angle-direct-texture-probe", "0.15.1-webgl-source-hook-probe")
build = build.replace(r"0\.15\.0-angle-direct-texture-probe", r"0\.15\.1-webgl-source-hook-probe")
build = build.replace("v0.15.0", "v0.15.1")
build = build.replace(r"v0\.15\.0", r"v0\.15\.1")
p.write_text(build, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Experiment guards. v0.15.1 is still a probe: proven CPU transport remains.
# ---------------------------------------------------------------------------
runtime = Path("pc/pc-stereo-layout.js").read_text(encoding="utf-8")
main = Path("pc/MainFormV11.cs").read_text(encoding="utf-8")
probe_host = Path("pc/MainFormV151.WebGlSourceProbe.cs").read_text(encoding="utf-8")
project = Path("pc/GeoGebraForQuest.PC.csproj").read_text(encoding="utf-8")
build = Path("pc/build.ps1").read_text(encoding="utf-8")

for text, needle, label in (
    (runtime, "type: 'stereoRawPair'", "checkpoint true-L/R raw IPC missing"),
    (runtime, "leftCaptureContext.getImageData", "checkpoint LEFT capture missing"),
    (runtime, "rightCaptureContext.getImageData", "checkpoint RIGHT capture missing"),
    (runtime, "__ggqWebGlSourceProbeV151", "v0.15.1 JS probe missing"),
    (runtime, "window.ggqRequestStereoFrame", "renderer-owned request call missing"),
    (runtime, "rightIsLiveWebGl", "live WebGL verification missing"),
    (main, 'case "webglSourceProbe":', "host WebGL probe message missing"),
    (probe_host, "GeoGebraForQuestPC.WebGL-Source-Probe.json", "WebGL probe persistence missing"),
    (project, "<Version>0.15.1</Version>", "v0.15.1 version missing"),
    (build, "v0.15.1-webgl-source-hook-probe", "v0.15.1 package label missing"),
):
    req(text, needle, "v0.15.1: " + label)

if "ggq-gpu-stereo-stage-v0141" in runtime:
    raise SystemExit("v0.15.1: abandoned v0.14 staging contamination")
if "GpuStereoV141State" in main:
    raise SystemExit("v0.15.1: abandoned v0.14 host contamination")

print("GeoGebraForQuest PC v0.15.1 active WebGL source probe applied")
