(function () {
  'use strict';

  // GeoGebraForQuest PC v0.12 Performance runtime.
  // A stays as CEF's native GPU surface. Exp46 still generates the true LEFT/RIGHT
  // cameras, but JPEG encoding is asynchronous so GeoGebra's UI thread is not blocked
  // by two synchronous 2K canvas.toDataURL() calls every frame.
  if (window.__ggqPcStereoRuntimeInstalledV12) return;
  window.__ggqPcStereoRuntimeInstalledV12 = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;
  var inactiveReported = false;

  var CAPTURE_INTERVAL_MS = 33;
  var CAPTURE_MAX_EYE_WIDTH = 2048;
  var CAPTURE_MAX_EYE_HEIGHT = 2048;
  var CAPTURE_JPEG_QUALITY = 0.96;

  var pendingStereoSerial = null;
  var pendingStereoRequestedAt = 0;
  var lastDeliveredStereoSerial = -1;
  var nextStereoRequestAt = 0;
  var encodingInFlight = false;
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

  function configureCaptureContext(context) {
    if (!context) return;
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
  }

  configureCaptureContext(leftCaptureContext);
  configureCaptureContext(rightCaptureContext);

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
    bridge('runtimeError', String(message || 'Stereo runtime error'));
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
    var rightEyeMain = document.getElementById('ggq-renderer-right-eye');
    if (rightEyeMain && rectOf(rightEyeMain) && isWebGLCanvas(rightEyeMain)) {
      lastCanvas = rightEyeMain;
      return rightEyeMain;
    }

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
    encodingInFlight = false;
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
    configureCaptureContext(leftCaptureContext);
    configureCaptureContext(rightCaptureContext);
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

  function canvasToDataUrlAsync(canvas) {
    return new Promise(function (resolve, reject) {
      if (!canvas || typeof canvas.toBlob !== 'function') {
        try {
          resolve(canvas.toDataURL('image/jpeg', CAPTURE_JPEG_QUALITY));
        } catch (fallbackError) {
          reject(fallbackError);
        }
        return;
      }

      canvas.toBlob(function (blob) {
        if (!blob) {
          reject(new Error('canvas.toBlob JPEG boş döndü'));
          return;
        }

        var reader = new FileReader();
        reader.onload = function () { resolve(String(reader.result || '')); };
        reader.onerror = function () { reject(reader.error || new Error('FileReader hatası')); };
        reader.readAsDataURL(blob);
      }, 'image/jpeg', CAPTURE_JPEG_QUALITY);
    });
  }

  function beginAsyncStereoCapture(serial, requestedAt) {
    if (!leftCaptureContext || !rightCaptureContext || encodingInFlight) return false;
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

      encodingInFlight = true;
      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;

      Promise.all([
        canvasToDataUrlAsync(leftCaptureCanvas),
        canvasToDataUrlAsync(rightCaptureCanvas)
      ]).then(function (urls) {
        var leftDataUrl = urls[0];
        var rightDataUrl = urls[1];

        if (!leftDataUrl || leftDataUrl.length <= 64 ||
            !rightDataUrl || rightDataUrl.length <= 64) {
          throw new Error('JPEG stereo kare boş');
        }

        if (!identicalWarningSent && leftDataUrl === rightDataUrl) {
          identicalWarningSent = true;
          reportRuntimeError('STEREO HATA: Exp46 sol ve sağ göz kareleri birebir aynı');
        }

        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        lastDeliveredStereoSerial = serial;

        var now = performance.now();
        var renderLatency = Math.max(0, now - requestedAt);
        nextStereoRequestAt = renderLatency >= CAPTURE_INTERVAL_MS
          ? now + 1
          : requestedAt + CAPTURE_INTERVAL_MS;
      }).catch(function (error) {
        reportRuntimeError(
          'Async stereo JPEG hatası: ' +
          (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
        );
        nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
      }).finally(function () {
        encodingInFlight = false;
      });

      return true;
    } catch (error) {
      encodingInFlight = false;
      reportRuntimeError(
        'Stereo capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }

  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null || encodingInFlight) return false;

    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    return beginAsyncStereoCapture(serial, requestedAt);
  }

  function captureLoop(now) {
    if (encodingInFlight) {
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
