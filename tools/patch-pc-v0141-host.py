#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.14.1 — zero-copy stereo B via one CEF GPU staging paint.

Architecture:

  proven GeoGebra LEFT/RIGHT renderer canvases (unchanged v0.13.35 semantics)
      -> Canvas2D drawImage into one temporary [L|R] DOM staging canvas
      -> Chromium accelerated-paint shared D3D11 texture
      -> host GPU CopyResource into a keyed-mutex shared texture
      -> XR GPU consumer + existing FullSbsComposer
      -> OpenXR

There is deliberately NO getImageData/readPixels/JPEG/Base64/raw pixel MMF path.
The visible GeoGebra WebGL framebuffer is never rebound or replaced. Temporary
staging paints are intercepted by the host and never presented on the PC.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

start = s.find("  var leftCaptureCanvas = document.createElement('canvas');")
end = s.find("\n  function bridge(name, value) {", start)
if start < 0 or end < 0:
    raise SystemExit('v0.14.1: old capture-canvas allocation block missing')
s = s[:start] + s[end:]

start = s.find('  function ensureCaptureCanvasSize(width, height) {')
if start >= 0:
    end = s.find('\n  }\n', start)
    if end < 0:
        raise SystemExit('v0.14.1: ensureCaptureCanvasSize end missing')
    end += len('\n  }\n')
    s = s[:start] + s[end:]

old_fields = r'''  var rawInFlight = false;
  var rawInFlightSerial = -1;
  var rawInFlightRequestedAt = 0;
  var rawPostedAt = 0;
  var RAW_ACK_TIMEOUT_MS = 1500;
'''
req(s, old_fields, 'v0.14.1: raw flight fields missing')
new_fields = r'''  var gpuInFlight = false;
  var gpuInFlightSerial = -1;
  var gpuInFlightRequestedAt = 0;
  var gpuStageShownAt = 0;
  var GPU_STAGE_TIMEOUT_MS = 1200;
  var gpuStageCanvas = null;
  var gpuStageContext = null;
  var gpuStageLayout = null;
'''
s = s.replace(old_fields, new_fields, 1)

start = s.find('  function beginRawStereoCapture(serial, requestedAt) {')
end = s.find('\n  function pollRequestedStereoPair(now) {', start)
if start < 0 or end < 0:
    raise SystemExit('v0.14.1: raw capture block boundaries missing')

new_capture = r'''  function ensureGpuStageCanvas() {
    if (gpuStageCanvas && gpuStageCanvas.isConnected && gpuStageContext) {
      return true;
    }

    gpuStageCanvas = document.createElement('canvas');
    gpuStageCanvas.id = 'ggq-gpu-stereo-stage-v0141';
    gpuStageCanvas.setAttribute('aria-hidden', 'true');
    var st = gpuStageCanvas.style;
    st.position = 'fixed';
    st.left = '0px';
    st.top = '0px';
    st.width = '2px';
    st.height = '2px';
    st.display = 'none';
    st.pointerEvents = 'none';
    st.zIndex = '2147483000';
    st.background = '#000';
    st.margin = '0';
    st.padding = '0';
    st.border = '0';
    st.opacity = '1';
    st.transform = 'none';
    st.imageRendering = 'auto';

    gpuStageContext = gpuStageCanvas.getContext('2d', {
      alpha: false,
      desynchronized: true
    });
    if (!gpuStageContext) {
      gpuStageCanvas = null;
      return false;
    }
    gpuStageContext.imageSmoothingEnabled = true;
    gpuStageContext.imageSmoothingQuality = 'high';
    (document.body || document.documentElement).appendChild(gpuStageCanvas);
    return true;
  }

  function computeGpuStageLayout(sourceWidth, sourceHeight) {
    var vw = Math.max(2, innerWidth);
    var vh = Math.max(2, innerHeight);
    var combinedAspect = (sourceWidth * 2) / Math.max(1, sourceHeight);
    var maxW = Math.max(2, vw - 4);
    var maxH = Math.max(2, vh - 4);
    var width = maxW;
    var height = width / combinedAspect;
    if (height > maxH) {
      height = maxH;
      width = height * combinedAspect;
    }
    width = Math.max(2, Math.floor(width));
    height = Math.max(2, Math.floor(height));
    var left = Math.max(0, Math.floor((vw - width) * 0.5));
    var top = Math.max(0, Math.floor((vh - height) * 0.5));
    width = Math.max(2, width & ~1);
    return { left:left, top:top, width:width, height:height };
  }

  function hideGpuStage() {
    if (gpuStageCanvas) gpuStageCanvas.style.display = 'none';
    gpuStageLayout = null;
  }

  function beginGpuStereoCapture(serial, requestedAt) {
    if (gpuInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left || !eyes.right) return false;
    if (!ensureGpuStageCanvas()) return false;

    var sourceWidth = Math.min(eyes.left.width | 0, eyes.right.width | 0);
    var sourceHeight = Math.min(eyes.left.height | 0, eyes.right.height | 0);
    if (sourceWidth < 2 || sourceHeight < 2) return false;

    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;
    gpuInFlight = true;
    gpuInFlightSerial = serial;
    gpuInFlightRequestedAt = requestedAt;
    gpuStageShownAt = 0;
    gpuStageLayout = computeGpuStageLayout(sourceWidth, sourceHeight);

    bridge('gpuStereoPairReady', JSON.stringify({
      serial: serial,
      sourceWidth: sourceWidth,
      sourceHeight: sourceHeight,
      viewWidth: innerWidth,
      viewHeight: innerHeight,
      stereo: geometry.rect
    }));
    return true;
  }

  window.ggqGpuPresentStereoStage = function (serial) {
    serial = Number(serial);
    if (!gpuInFlight || !isFinite(serial) || serial !== gpuInFlightSerial) {
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left || !eyes.right || !ensureGpuStageCanvas()) return false;
    var sourceWidth = Math.min(eyes.left.width | 0, eyes.right.width | 0);
    var sourceHeight = Math.min(eyes.left.height | 0, eyes.right.height | 0);
    if (sourceWidth < 2 || sourceHeight < 2) return false;

    var layout = gpuStageLayout || computeGpuStageLayout(sourceWidth, sourceHeight);
    gpuStageLayout = layout;

    if (gpuStageCanvas.width !== sourceWidth * 2) gpuStageCanvas.width = sourceWidth * 2;
    if (gpuStageCanvas.height !== sourceHeight) gpuStageCanvas.height = sourceHeight;
    gpuStageContext.imageSmoothingEnabled = true;
    gpuStageContext.imageSmoothingQuality = 'high';
    gpuStageContext.setTransform(1, 0, 0, 1, 0, 0);
    gpuStageContext.clearRect(0, 0, sourceWidth * 2, sourceHeight);
    gpuStageContext.drawImage(
      eyes.left,
      0, 0, sourceWidth, sourceHeight,
      0, 0, sourceWidth, sourceHeight
    );
    gpuStageContext.drawImage(
      eyes.right,
      0, 0, sourceWidth, sourceHeight,
      sourceWidth, 0, sourceWidth, sourceHeight
    );

    var st = gpuStageCanvas.style;
    st.left = layout.left + 'px';
    st.top = layout.top + 'px';
    st.width = layout.width + 'px';
    st.height = layout.height + 'px';
    st.display = 'block';
    gpuStageShownAt = performance.now();

    var tokenSerial = serial;
    var done = false;
    function signalPresented(source) {
      if (done || !gpuInFlight || tokenSerial !== gpuInFlightSerial) return;
      done = true;
      bridge('gpuStereoStagePresented', JSON.stringify({
        serial: tokenSerial,
        viewWidth: innerWidth,
        viewHeight: innerHeight,
        stage: gpuStageLayout,
        sourceWidth: sourceWidth,
        sourceHeight: sourceHeight,
        ackSource: source,
        waitMs: Math.max(0, performance.now() - gpuStageShownAt)
      }));
    }

    try {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { signalPresented('raf2'); });
      });
    } catch (_) {}
    setTimeout(function () { signalPresented('timeout'); }, 36);
    return true;
  };

  window.ggqGpuReleaseStereoPair = function (serial, ok) {
    serial = Number(serial);
    if (!gpuInFlight || !isFinite(serial) || serial !== gpuInFlightSerial) {
      hideGpuStage();
      return false;
    }

    var now = performance.now();
    var requestedAt = gpuInFlightRequestedAt;
    if (ok !== false) lastDeliveredStereoSerial = serial;
    hideGpuStage();
    gpuInFlight = false;
    gpuInFlightSerial = -1;
    gpuInFlightRequestedAt = 0;
    gpuStageShownAt = 0;

    var cycleMs = requestedAt ? Math.max(0, now - requestedAt) : 0;
    nextStereoRequestAt = requestedAt && cycleMs < CAPTURE_INTERVAL_MS
      ? requestedAt + CAPTURE_INTERVAL_MS
      : now + 1;
    return true;
  };
'''
s = s[:start] + new_capture + s[end:]

s = s.replace(
    '    if (pendingStereoSerial === null || rawInFlight) return false;\n',
    '    if (pendingStereoSerial === null || gpuInFlight) return false;\n',
    1)
s = s.replace(
    '    return beginRawStereoCapture(serial, requestedAt);\n',
    '    return beginGpuStereoCapture(serial, requestedAt);\n',
    1)

loop_start = s.find('  function captureLoop(now) {')
loop_end = s.find('\n  if (window.ResizeObserver) {', loop_start)
if loop_start < 0 or loop_end < 0:
    raise SystemExit('v0.14.1: captureLoop boundaries missing')
new_loop = r'''  function captureLoop(now) {
    if (gpuInFlight) {
      var anchor = gpuStageShownAt || gpuInFlightRequestedAt;
      if (anchor > 0 && now - anchor > GPU_STAGE_TIMEOUT_MS) {
        var serial = gpuInFlightSerial;
        window.ggqGpuReleaseStereoPair(serial, false);
        reportRuntimeError('GPU stereo stage timeout serial=' + serial);
      }
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!geometryState) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      requestAnimationFrame(captureLoop);
      return;
    }

    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!requestStereoPair(now)) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }

    requestAnimationFrame(captureLoop);
  }
'''
s = s[:loop_start] + new_loop + s[loop_end:]

s = s.replace(
    "    canvases.forEach(function (canvas) {\n      if (canvas.id === 'ggq-renderer-left-eye') return;",
    "    canvases.forEach(function (canvas) {\n      if (canvas.id === 'ggq-renderer-left-eye' ||\n          canvas.id === 'ggq-gpu-stereo-stage-v0141') return;",
    1)

s = s.replace('  var CAPTURE_INTERVAL_MS = 16;\n', '  var CAPTURE_INTERVAL_MS = 1;\n', 1)

for forbidden in (
    'getImageData(', "type: 'stereoRawPair'", 'window.ggqRawStereoAck',
    'canvasToDataUrlAsync', "'image/jpeg'", '"image/jpeg"', 'readPixels('
):
    if forbidden in s:
        raise SystemExit('v0.14.1 forbidden CPU pixel path remains: ' + forbidden)
for needed in (
    "document.getElementById('ggq-renderer-left-eye')",
    "document.getElementById('ggq-renderer-right-eye')",
    "ggq-gpu-stereo-stage-v0141",
    'gpuStageContext.drawImage',
    'window.ggqGpuPresentStereoStage',
    'window.ggqGpuReleaseStereoPair',
    "bridge('gpuStereoPairReady'",
    "bridge('gpuStereoStagePresented'",
):
    req(s, needed, 'v0.14.1 runtime invariant missing: ' + needed)
p.write_text(s, encoding='utf-8')

p = Path('pc/MainFormV11.cs')
main = p.read_text(encoding='utf-8')
main = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.14.1-zero-copy-b',
    main,
    count=1)
main = re.sub(r'GeoGebraForQuest PC v0\.13\.35', 'GeoGebraForQuest PC v0.14.1', main)
main = main.replace('v0.13.35', 'v0.14.1')

bridge_marker = '                setDepthPointerActive: function () {},\n'
req(main, bridge_marker, 'v0.14.1: QuestBridge insertion marker missing')
main = main.replace(
    bridge_marker,
    "                gpuStereoPairReady: function (payload) {\n"
    "                  post({ type: 'gpuStereoPairReady', payload: String(payload || '') });\n"
    "                },\n"
    "                gpuStereoStagePresented: function (payload) {\n"
    "                  post({ type: 'gpuStereoStagePresented', payload: String(payload || '') });\n"
    "                },\n" + bridge_marker,
    1)

switch_marker = '                case "runtimeError":\n'
req(main, switch_marker, 'v0.14.1: JS message switch marker missing')
main = main.replace(
    switch_marker,
    '                case "gpuStereoPairReady":\n'
    '                    HandleGpuStereoV141PairReady(root);\n'
    '                    break;\n'
    '                case "gpuStereoStagePresented":\n'
    '                    HandleGpuStereoV141StagePresented(root);\n'
    '                    break;\n' + switch_marker,
    1)

shutdown_bundle = '        _performanceTelemetry.Dispose();\n        LogBundle.Create();\n'
req(main, shutdown_bundle, 'v0.14.1: shutdown telemetry marker missing')
main = main.replace(
    shutdown_bundle,
    '        _performanceTelemetry.Dispose();\n'
    '        _gpuStereoV141Telemetry.Dispose();\n'
    '        _stereoGpuPublisher.Dispose();\n'
    '        LogBundle.Create();\n',
    1)

shutdown_pos = main.find('private void Shutdown()')
lock_marker = '        lock (_d3dLock)\n        {\n'
idx = main.find(lock_marker, shutdown_pos)
if shutdown_pos < 0 or idx < 0:
    raise SystemExit('v0.14.1: D3D shutdown lock missing')
insert = idx + len(lock_marker)
main = main[:insert] + '            DisposeGpuStereoV141ResourcesLocked();\n' + main[insert:]
main = main.replace('XR Behind Native', 'GPU Zero-Copy B')
p.write_text(main, encoding='utf-8')

p = Path('pc/MainFormV11.Graphics.cs')
graphics = p.read_text(encoding='utf-8')
marker = '''                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                EnsurePcTextureLocked(cefTexture.Description);
'''
req(graphics, marker, 'v0.14.1: accelerated paint marker missing')
graphics = graphics.replace(
    marker,
    '''                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(
                    acceleratedPaintInfo.SharedTextureHandle);

                if (TryConsumeGpuStereoV141PaintLocked(cefTexture))
                {
                    return;
                }

                // Ordinary A paint remains on the proven v0.13.35 path.
                EnsurePcTextureLocked(cefTexture.Description);
''',
    1)
p.write_text(graphics, encoding='utf-8')

p = Path('pc/D3DChromiumWebBrowser.cs')
browser = p.read_text(encoding='utf-8')
req(browser, 'WindowlessFrameRate = 60,', 'v0.14.1: CEF frame-rate marker missing')
browser = browser.replace('WindowlessFrameRate = 60,', 'WindowlessFrameRate = 120,', 1)
p.write_text(browser, encoding='utf-8')

p = Path('pc/GeoGebraForQuest.PC.csproj')
project = p.read_text(encoding='utf-8')
project = re.sub(r'<Version>[^<]+</Version>', '<Version>0.14.1</Version>', project, count=1)
project = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.14.1.0</FileVersion>', project, count=1)
project = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.14.1.0</AssemblyVersion>', project, count=1)
p.write_text(project, encoding='utf-8')

p = Path('pc/build.ps1')
build = p.read_text(encoding='utf-8')
build = build.replace(
    'GeoGebraForQuest-PC-v0.13.35-correct-lr-win-x64',
    'GeoGebraForQuest-PC-v0.14.1-zero-copy-b-win-x64')
build = build.replace('0.13.35-correct-lr', '0.14.1-zero-copy-b')
build = build.replace(r'0\.13\.35-correct-lr', r'0\.14\.1-zero-copy-b')
build = build.replace('v0.13.35', 'v0.14.1')
build = build.replace(r'v0\.13\.35', r'v0\.14\.1')
legacy_tokens = (
    "type: 'stereoRawPair'", 'leftCaptureContext.getImageData',
    'rightCaptureContext.getImageData', 'window.ggqRawStereoAck',
    'WriteRawStereoPairRgba', 'rgbaSbs[i + 2]'
)
lines = build.splitlines()
lines = [line for line in lines if not any(tok in line for tok in legacy_tokens)]
build = '\n'.join(lines) + '\n'
p.write_text(build, encoding='utf-8')

runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
main = Path('pc/MainFormV11.cs').read_text(encoding='utf-8')
graphics = Path('pc/MainFormV11.Graphics.cs').read_text(encoding='utf-8')
browser = Path('pc/D3DChromiumWebBrowser.cs').read_text(encoding='utf-8')
for forbidden in ('getImageData(', "stereoRawPair", 'ggqRawStereoAck', 'readPixels('):
    if forbidden in runtime:
        raise SystemExit('v0.14.1 host forbidden runtime path: ' + forbidden)
for needed, text in (
    ('ggq-gpu-stereo-stage-v0141', runtime),
    ('gpuStageContext.drawImage', runtime),
    ('gpuStereoPairReady', main),
    ('gpuStereoStagePresented', main),
    ('TryConsumeGpuStereoV141PaintLocked', graphics),
    ('WindowlessFrameRate = 120', browser),
):
    req(text, needed, 'v0.14.1 host invariant missing: ' + needed)
print('GeoGebraForQuest PC v0.14.1 host zero-copy staging patch applied')
