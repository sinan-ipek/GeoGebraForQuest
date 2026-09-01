(function () {
  'use strict';

  // GeoGebraForQuest PC v0.5 High-Res SBS runtime.
  // The Windows monitor keeps GeoGebra's normal visible 3D WebGL canvas untouched.
  // Quest/OpenXR receives a synchronized LEFT/RIGHT pair for exactly that same rectangle.
  if (window.__ggqPcStereoRuntimeInstalledV5) return;
  window.__ggqPcStereoRuntimeInstalledV5 = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;
  var inactiveReported = false;

  // Exp46 stereo renderer is still demand-driven. Unlike the standalone Quest build,
  // this PC path does not use the old 720 px transport limit. Each eye is captured
  // at the renderer's native backing resolution up to 2048x2048.
  var CAPTURE_INTERVAL_MS = 42;
  var CAPTURE_MAX_EYE_WIDTH = 2048;
  var CAPTURE_MAX_EYE_HEIGHT = 2048;
  var CAPTURE_JPEG_QUALITY = 0.95;

  var pendingStereoSerial = null;
  var pendingStereoRequestedAt = 0;
  var lastDeliveredStereoSerial = -1;
  var nextStereoRequestAt = 0;
  var identicalWarningSent = false;

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

  if (leftCaptureContext) {
    leftCaptureContext.imageSmoothingEnabled = true;
    leftCaptureContext.imageSmoothingQuality = 'high';
  }
  if (rightCaptureContext) {
    rightCaptureContext.imageSmoothingEnabled = true;
    rightCaptureContext.imageSmoothingQuality = 'high';
  }

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
    // Exp46 aliases ggq-renderer-right-eye to the actual visible GeoGebra WebGL canvas.
    var rightEyeMain = document.getElementById('ggq-renderer-right-eye');
    if (rightEyeMain && rectOf(rightEyeMain) && isWebGLCanvas(rightEyeMain)) {
      lastCanvas = rightEyeMain;
      return rightEyeMain;
    }

    // Fallback during renderer startup/recreation.
    var root = document.getElementById('ggb-element') || document;
    var canvases = Array.prototype.slice.call(root.querySelectorAll('canvas'));
    var best = null;
    var bestScore = 0;

    canvases.forEach(function (canvas) {
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

    if (leftCaptureContext) {
      leftCaptureContext.imageSmoothingEnabled = true;
      leftCaptureContext.imageSmoothingQuality = 'high';
    }
    if (rightCaptureContext) {
      rightCaptureContext.imageSmoothingEnabled = true;
      rightCaptureContext.imageSmoothingQuality = 'high';
    }
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

  function computeCaptureSize(sourceWidth, sourceHeight) {
    var scale = Math.min(
      1,
      CAPTURE_MAX_EYE_WIDTH / sourceWidth,
      CAPTURE_MAX_EYE_HEIGHT / sourceHeight
    );

    return {
      width: Math.max(2, Math.round(sourceWidth * scale)),
      height: Math.max(2, Math.round(sourceHeight * scale))
    };
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

      var captureSize = computeCaptureSize(sourceWidth, sourceHeight);
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;
      ensureCaptureCanvasSize(eyeWidth, eyeHeight);

      leftCaptureContext.clearRect(0, 0, eyeWidth, eyeHeight);
      rightCaptureContext.clearRect(0, 0, eyeWidth, eyeHeight);

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

      if (!identicalWarningSent && leftDataUrl === rightDataUrl) {
        identicalWarningSent = true;
        reportRuntimeError('STEREO HATA: Exp46 sol ve sağ göz kareleri birebir aynı');
      }

      bridgeStereoEyes(leftDataUrl, rightDataUrl);
      lastDeliveredStereoSerial = serial;
      return true;
    } catch (error) {
      reportRuntimeError(
        'High-Res stereo capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
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
