(function () {
  'use strict';

  // PC v0.3.1 diagnostic runtime.
  // The Windows monitor keeps GeoGebra's normal visible 3D WebGL canvas untouched.
  // Quest/OpenXR receives a synchronized LEFT/RIGHT pair for exactly that same rectangle.
  // Diagnostic markers are drawn ONLY into the captured eye frames sent to Quest.
  if (window.__ggqPcStereoRuntimeInstalled) return;
  window.__ggqPcStereoRuntimeInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;
  var inactiveReported = false;

  // Match the proven Exp46 delivery path: demand-driven pair, ~24 fps, 720 px eye width.
  var CAPTURE_INTERVAL_MS = 42;
  var CAPTURE_MAX_EYE_WIDTH = 720;
  var CAPTURE_JPEG_QUALITY = 0.78;

  var pendingStereoSerial = null;
  var pendingStereoRequestedAt = 0;
  var lastDeliveredStereoSerial = -1;
  var nextStereoRequestAt = 0;
  var identicalWarningSent = false;
  var lastSourceDiff = -1;

  var leftCaptureCanvas = document.createElement('canvas');
  var rightCaptureCanvas = document.createElement('canvas');
  var leftCaptureContext = leftCaptureCanvas.getContext('2d', {
    alpha: false,
    desynchronized: true
  });
  var rightCaptureContext = rightCaptureCanvas.getContext('2d', {
    alpha: false,
    desynchronized: true
  });

  var leftProbeCanvas = document.createElement('canvas');
  var rightProbeCanvas = document.createElement('canvas');
  leftProbeCanvas.width = 64;
  leftProbeCanvas.height = 64;
  rightProbeCanvas.width = 64;
  rightProbeCanvas.height = 64;
  var leftProbeContext = leftProbeCanvas.getContext('2d', { alpha: false });
  var rightProbeContext = rightProbeCanvas.getContext('2d', { alpha: false });

  function bridge(name, value) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge[name] === 'function') {
        window.QuestBridge[name](value);
      }
    } catch (_) {}
  }

  function bridgeStereoEyes(leftDataUrl, rightDataUrl) {
    try {
      if (window.QuestBridge &&
          typeof window.QuestBridge.updateStereoEyes === 'function') {
        window.QuestBridge.updateStereoEyes(leftDataUrl, rightDataUrl);
      }
    } catch (_) {}
  }

  function reportRuntimeError(message) {
    try {
      window.chrome.webview.postMessage({
        type: 'runtimeError',
        message: String(message || 'Stereo runtime error')
      });
    } catch (_) {}
  }

  function rectOf(element) {
    if (!element || !element.isConnected) return null;

    var style;
    try { style = getComputedStyle(element); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return null;
    if (Number(style.opacity) === 0) return null;

    var r;
    try { r = element.getBoundingClientRect(); } catch (_) { return null; }
    if (!r || r.width < 2 || r.height < 2) return null;
    if (r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return null;

    var left = Math.max(0, r.left);
    var top = Math.max(0, r.top);
    var right = Math.min(innerWidth, r.right);
    var bottom = Math.min(innerHeight, r.bottom);
    if (right - left < 2 || bottom - top < 2) return null;

    return {
      left: left,
      top: top,
      width: right - left,
      height: bottom - top
    };
  }

  function isWebGLCanvas(canvas) {
    if (!canvas) return false;
    try {
      return !!(
        canvas.getContext('webgl2') ||
        canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl')
      );
    } catch (_) {
      return false;
    }
  }

  function findVisible3DCanvas() {
    // Exp46 v0.9.20 aliases ggq-renderer-right-eye to the ACTUAL visible main
    // GeoGebra WebGL canvas. It is therefore the authoritative 3D rectangle.
    var rightEyeMain = document.getElementById('ggq-renderer-right-eye');
    if (rightEyeMain && rectOf(rightEyeMain) && isWebGLCanvas(rightEyeMain)) {
      lastCanvas = rightEyeMain;
      return rightEyeMain;
    }

    // Fallback for startup/recreation windows before the alias is attached.
    var root = document.getElementById('ggb-element') || document;
    var canvases = Array.prototype.slice.call(root.querySelectorAll('canvas'));
    var best = null;
    var bestScore = 0;

    canvases.forEach(function (canvas) {
      // Only the LEFT snapshot canvas is a hidden helper. Never exclude the
      // right-eye id: in Exp46 that id belongs to the visible main WebGL canvas.
      if (canvas.id === 'ggq-renderer-left-eye') return;

      var r = rectOf(canvas);
      if (!r || !isWebGLCanvas(canvas)) return;

      var area = r.width * r.height;
      var dpr = window.devicePixelRatio || 1;
      var largeBacking = canvas.width >= Math.floor(r.width * dpr * 0.9);
      var score = area * (largeBacking ? 2 : 1);

      if (score > bestScore) {
        bestScore = score;
        best = canvas;
      }
    });

    if (best) lastCanvas = best;
    return best;
  }

  function find3DCanvas() {
    return findVisible3DCanvas() ||
      (lastCanvas && lastCanvas.isConnected ? lastCanvas : null);
  }

  function resetStereoRequestState() {
    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;
    lastDeliveredStereoSerial = -1;
    nextStereoRequestAt = 0;
  }

  function reportInactive() {
    resetStereoRequestState();
    if (inactiveReported) return;
    inactiveReported = true;
    lastPayload = '';
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({
      active: false,
      viewWidth: innerWidth,
      viewHeight: innerHeight
    }));
  }

  function reportActive() {
    inactiveReported = false;
  }

  function sendLayout() {
    scheduled = false;

    var canvas = find3DCanvas();
    var rect = rectOf(canvas);
    if (!canvas || !rect) {
      reportInactive();
      return;
    }

    reportActive();

    var payload = JSON.stringify({
      active: true,
      stereo: rect,
      viewWidth: innerWidth,
      viewHeight: innerHeight
    });

    if (payload === lastPayload) return;
    lastPayload = payload;
    bridge('updateStereoLayout', payload);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(sendLayout);
  }

  function getRendererEyeCanvases() {
    var left = document.getElementById('ggq-renderer-left-eye');
    var right = document.getElementById('ggq-renderer-right-eye');
    if (!left || !right) return null;
    if (left.width < 2 || left.height < 2 || right.width < 2 || right.height < 2) {
      return null;
    }
    return { left: left, right: right };
  }

  function ensureCaptureCanvasSize(width, height) {
    if (leftCaptureCanvas.width !== width) leftCaptureCanvas.width = width;
    if (leftCaptureCanvas.height !== height) leftCaptureCanvas.height = height;
    if (rightCaptureCanvas.width !== width) rightCaptureCanvas.width = width;
    if (rightCaptureCanvas.height !== height) rightCaptureCanvas.height = height;
  }

  function readStereoFrameSerial() {
    try {
      if (typeof window.ggqGetStereoFrameSerial !== 'function') return -1;
      var serial = Number(window.ggqGetStereoFrameSerial());
      return isFinite(serial) ? serial : -1;
    } catch (_) {
      return -1;
    }
  }

  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') return false;
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) return false;
      pendingStereoSerial = baseline;
      pendingStereoRequestedAt = now;
      return true;
    } catch (_) {
      return false;
    }
  }

  function estimateSourceDifference() {
    if (!leftProbeContext || !rightProbeContext) return -1;

    try {
      leftProbeContext.drawImage(leftCaptureCanvas, 0, 0, 64, 64);
      rightProbeContext.drawImage(rightCaptureCanvas, 0, 0, 64, 64);

      var a = leftProbeContext.getImageData(0, 0, 64, 64).data;
      var b = rightProbeContext.getImageData(0, 0, 64, 64).data;
      if (!a || !b || a.length !== b.length) return -1;

      var sum = 0;
      var count = 0;
      for (var i = 0; i < a.length; i += 16) {
        sum += Math.abs(a[i] - b[i]);
        sum += Math.abs(a[i + 1] - b[i + 1]);
        sum += Math.abs(a[i + 2] - b[i + 2]);
        count += 3;
      }
      return count ? sum / count : 0;
    } catch (_) {
      return -1;
    }
  }

  function drawEyeMarker(context, eyeName, diff, width, height) {
    if (!context) return;

    var markerSize = Math.max(48, Math.min(88, Math.round(Math.min(width, height) * 0.13)));
    var pad = Math.max(8, Math.round(markerSize * 0.16));
    var isLeft = eyeName === 'L';
    var x = isLeft ? pad : Math.max(pad, width - markerSize - pad);
    var y = pad;

    context.save();
    context.globalAlpha = 0.96;
    context.fillStyle = isLeft ? '#d93025' : '#1565c0';
    context.fillRect(x, y, markerSize, markerSize);

    context.globalAlpha = 1;
    context.fillStyle = '#ffffff';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.font = 'bold ' + Math.max(30, Math.round(markerSize * 0.62)) + 'px sans-serif';
    context.fillText(eyeName, x + markerSize / 2, y + markerSize / 2);

    var label = diff >= 0 ? 'L/R fark=' + diff.toFixed(2) : 'L/R fark=?';
    context.font = 'bold ' + Math.max(14, Math.round(markerSize * 0.22)) + 'px sans-serif';
    context.textAlign = isLeft ? 'left' : 'right';
    context.textBaseline = 'top';
    var tx = isLeft ? pad : width - pad;
    var ty = y + markerSize + Math.max(6, Math.round(markerSize * 0.08));

    var measure = context.measureText(label);
    var boxW = Math.ceil(measure.width) + 12;
    var boxH = Math.max(22, Math.round(markerSize * 0.30));
    var boxX = isLeft ? tx - 5 : tx - boxW + 5;

    context.fillStyle = diff >= 0 && diff < 0.35 ? '#ff8f00' : 'rgba(0,0,0,0.78)';
    context.fillRect(boxX, ty - 3, boxW, boxH);
    context.fillStyle = '#ffffff';
    context.fillText(label, tx, ty);
    context.restore();
  }

  function captureStereoEyes(serial) {
    if (!leftCaptureContext || !rightCaptureContext) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var canvas = find3DCanvas();
    var rect = rectOf(canvas);
    if (!canvas || !rect) {
      reportInactive();
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var scale = Math.min(1, CAPTURE_MAX_EYE_WIDTH / sourceWidth);
      var eyeWidth = Math.max(2, Math.round(sourceWidth * scale));
      var eyeHeight = Math.max(2, Math.round(sourceHeight * scale));
      ensureCaptureCanvasSize(eyeWidth, eyeHeight);

      leftCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      rightCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );

      // Measure the REAL source pair before adding any diagnostic graphics.
      lastSourceDiff = estimateSourceDifference();

      // Eye-isolation markers. These are never drawn to the Windows GeoGebra canvas;
      // they exist only in the frames sent through the Quest/OpenXR path.
      drawEyeMarker(leftCaptureContext, 'L', lastSourceDiff, eyeWidth, eyeHeight);
      drawEyeMarker(rightCaptureContext, 'R', lastSourceDiff, eyeWidth, eyeHeight);

      var leftDataUrl = leftCaptureCanvas.toDataURL(
        'image/jpeg', CAPTURE_JPEG_QUALITY
      );
      var rightDataUrl = rightCaptureCanvas.toDataURL(
        'image/jpeg', CAPTURE_JPEG_QUALITY
      );

      if (!leftDataUrl || leftDataUrl.length <= 64 ||
          !rightDataUrl || rightDataUrl.length <= 64) {
        return false;
      }

      if (!identicalWarningSent && lastSourceDiff >= 0 && lastSourceDiff < 0.05) {
        identicalWarningSent = true;
        reportRuntimeError(
          'STEREO KAYNAK UYARISI: L/R gerçek görüntü farkı ' + lastSourceDiff.toFixed(3)
        );
      }

      bridgeStereoEyes(leftDataUrl, rightDataUrl);
      lastDeliveredStereoSerial = serial;
      return true;
    } catch (_) {
      return false;
    }
  }

  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null) return false;

    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;
    if (!captureStereoEyes(serial)) return false;

    var requestedAt = pendingStereoRequestedAt;
    var renderLatency = Math.max(0, now - requestedAt);
    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;

    nextStereoRequestAt = renderLatency >= CAPTURE_INTERVAL_MS
      ? now + 8
      : requestedAt + CAPTURE_INTERVAL_MS;
    return true;
  }

  function captureLoop(now) {
    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
      requestAnimationFrame(captureLoop);
      return;
    }

    var canvas = find3DCanvas();
    var rect = rectOf(canvas);
    if (!canvas || !rect) {
      reportInactive();
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      requestAnimationFrame(captureLoop);
      return;
    }

    reportActive();

    if (!requestStereoPair(now)) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }

    requestAnimationFrame(captureLoop);
  }

  if (window.ResizeObserver) {
    var resizeObserver = new ResizeObserver(schedule);
    resizeObserver.observe(document.documentElement);
    if (document.body) resizeObserver.observe(document.body);
  }

  var mutationObserver = new MutationObserver(schedule);
  mutationObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class', 'hidden', 'aria-hidden']
  });

  addEventListener('resize', schedule, { passive: true });
  addEventListener('scroll', schedule, true);
  setInterval(schedule, 500);

  schedule();
  requestAnimationFrame(captureLoop);
  bridge('panelReady', '');
})();
