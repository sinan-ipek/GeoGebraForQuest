(function () {
  'use strict';

  // GeoGebraForQuest PC v0.12.2 Native Quality runtime.
  // A stays on the proven CEF D3D11 GPU path. B keeps the proven Exp46 LEFT/RIGHT
  // path, but its source resolution is matched to the actual angular size of the
  // 3D panel instead of blindly encoding 2048 px per eye.
  if (window.__ggqPcStereoRuntimeInstalledV122) return;
  window.__ggqPcStereoRuntimeInstalledV122 = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;
  var inactiveReported = false;

  var CAPTURE_INTERVAL_MS = 33;
  var QUEST_PANEL_TARGET_WIDTH = 1680;
  var QUEST_PANEL_HARD_MAX_WIDTH = 1920;
  var CAPTURE_MIN_EYE_WIDTH = 720;
  var CAPTURE_MAX_EYE_WIDTH = 1600;
  var CAPTURE_MAX_EYE_HEIGHT = 1600;
  var CAPTURE_JPEG_QUALITY = 0.98;

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

  function intersectRect(a, b) {
    if (!a || !b) return null;
    var left = Math.max(a.left, b.left);
    var top = Math.max(a.top, b.top);
    var right = Math.min(a.left + a.width, b.left + b.width);
    var bottom = Math.min(a.top + a.height, b.top + b.height);
    if (right - left < 2 || bottom - top < 2) return null;
    return {
      left: left,
      top: top,
      width: right - left,
      height: bottom - top
    };
  }

  function rawRectOf(element) {
    if (!element || !element.isConnected) return null;

    var style;
    try { style = getComputedStyle(element); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return null;
    if (Number(style.opacity) === 0) return null;

    var r;
    try { r = element.getBoundingClientRect(); } catch (_) { return null; }
    if (!r || r.width < 2 || r.height < 2) return null;

    return {
      left: r.left,
      top: r.top,
      width: r.width,
      height: r.height
    };
  }

  function clippedRectOf(element) {
    var rect = rawRectOf(element);
    if (!rect) return null;

    rect = intersectRect(rect, {
      left: 0,
      top: 0,
      width: innerWidth,
      height: innerHeight
    });
    if (!rect) return null;

    var parent = element.parentElement;
    while (parent && parent !== document.documentElement) {
      var style;
      try { style = getComputedStyle(parent); } catch (_) { style = null; }
      if (style) {
        var overflowX = String(style.overflowX || style.overflow || 'visible');
        var overflowY = String(style.overflowY || style.overflow || 'visible');
        var clipX = overflowX !== 'visible';
        var clipY = overflowY !== 'visible';

        if (clipX || clipY) {
          var pr = rawRectOf(parent);
          if (pr) {
            var clipRect = {
              left: clipX ? pr.left : 0,
              top: clipY ? pr.top : 0,
              width: clipX ? pr.width : innerWidth,
              height: clipY ? pr.height : innerHeight
            };
            rect = intersectRect(rect, clipRect);
            if (!rect) return null;
          }
        }
      }
      parent = parent.parentElement;
    }

    return rect;
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

  function elementIsVisible(element) {
    if (!element || !element.isConnected) return false;
    var style;
    try { style = getComputedStyle(element); } catch (_) { return false; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    if (Number(style.opacity) === 0) return false;
    var rect = rawRectOf(element);
    return !!rect && rect.width >= 2 && rect.height >= 2;
  }

  function rectsOverlap(a, b) {
    return !!intersectRect(a, b);
  }

  function knownBlockingOverlay(canvas, stereoRect) {
    var selectors = [
      '[role="dialog"]',
      '[aria-modal="true"]',
      '[role="menu"]',
      '[role="listbox"]',
      '.gwt-PopupPanel',
      '.gwt-DialogBox',
      '.mat-menu-panel',
      '.mat-mdc-menu-panel',
      '.dropdown-menu',
      '.context-menu',
      '.modal',
      '.dialog',
      '.popup'
    ].join(',');

    var candidates;
    try { candidates = document.querySelectorAll(selectors); } catch (_) { return false; }

    for (var i = 0; i < candidates.length; i++) {
      var element = candidates[i];
      if (!elementIsVisible(element)) continue;
      if (element === canvas || element.contains(canvas) || canvas.contains(element)) continue;
      var rect = rawRectOf(element);
      if (rect && rectsOverlap(rect, stereoRect)) return true;
    }
    return false;
  }

  function pointHasBlockingOverlay(x, y, canvas) {
    var stack;
    try { stack = document.elementsFromPoint(x, y); } catch (_) { return false; }
    if (!stack || !stack.length) return false;

    for (var i = 0; i < stack.length; i++) {
      var element = stack[i];
      if (element === canvas || canvas.contains(element)) return false;
      if (!element || !elementIsVisible(element)) continue;
      if (element.id === 'ggq-renderer-left-eye' ||
          element.id === 'ggq-renderer-right-eye') continue;

      var role = String(element.getAttribute && element.getAttribute('role') || '').toLowerCase();
      var ariaModal = String(element.getAttribute && element.getAttribute('aria-modal') || '').toLowerCase();
      if (role === 'dialog' || role === 'menu' || role === 'listbox' || ariaModal === 'true') {
        return true;
      }

      var style;
      try { style = getComputedStyle(element); } catch (_) { style = null; }
      if (!style) continue;
      var z = parseInt(style.zIndex, 10);
      if ((style.position === 'fixed' || style.position === 'absolute') &&
          isFinite(z) && z >= 100) {
        return true;
      }
    }
    return false;
  }

  function stereoUiOccluded(canvas, rect) {
    if (!canvas || !rect) return true;
    if (knownBlockingOverlay(canvas, rect)) return true;

    var xs = [0.2, 0.5, 0.8];
    var ys = [0.2, 0.5, 0.8];
    for (var yi = 0; yi < ys.length; yi++) {
      for (var xi = 0; xi < xs.length; xi++) {
        var x = rect.left + rect.width * xs[xi];
        var y = rect.top + rect.height * ys[yi];
        if (pointHasBlockingOverlay(x, y, canvas)) return true;
      }
    }
    return false;
  }

  function findVisible3DCanvas() {
    var rightEyeMain = document.getElementById('ggq-renderer-right-eye');
    if (rightEyeMain && clippedRectOf(rightEyeMain) && isWebGLCanvas(rightEyeMain)) {
      lastCanvas = rightEyeMain;
      return rightEyeMain;
    }

    var root = document.getElementById('ggb-element') || document;
    var canvases = Array.prototype.slice.call(root.querySelectorAll('canvas'));
    var best = null;
    var bestScore = 0;

    canvases.forEach(function (canvas) {
      if (canvas.id === 'ggq-renderer-left-eye') return;

      var r = clippedRectOf(canvas);
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

  function reportInactive(reason) {
    resetStereoRequestState();
    if (inactiveReported) return;
    inactiveReported = true;
    lastPayload = '';
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({
      active: false,
      reason: String(reason || 'inactive'),
      viewWidth: innerWidth,
      viewHeight: innerHeight
    }));
  }

  function reportActive() {
    if (inactiveReported) {
      inactiveReported = false;
      lastPayload = '';
      schedule();
      return;
    }
    inactiveReported = false;
  }

  function currentStereoGeometry() {
    var canvas = find3DCanvas();
    var rect = clippedRectOf(canvas);
    if (!canvas || !rect) return null;
    if (stereoUiOccluded(canvas, rect)) return null;
    return { canvas: canvas, rect: rect };
  }

  function sendLayout() {
    scheduled = false;

    var geometry = currentStereoGeometry();
    if (!geometry) {
      reportInactive('ui-or-no-3d');
      return;
    }

    reportActive();

    var payload = JSON.stringify({
      active: true,
      stereo: geometry.rect,
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

  function computeCaptureSize(sourceWidth, sourceHeight, stereoRect) {
    var viewWidth = Math.max(1, innerWidth);
    var panelFraction = Math.max(0.05, Math.min(1, stereoRect.width / viewWidth));
    var desiredWidth = Math.round(QUEST_PANEL_TARGET_WIDTH * panelFraction);
    desiredWidth = Math.min(QUEST_PANEL_HARD_MAX_WIDTH, desiredWidth);
    desiredWidth = Math.max(CAPTURE_MIN_EYE_WIDTH, desiredWidth);
    desiredWidth = Math.min(CAPTURE_MAX_EYE_WIDTH, desiredWidth);

    var scale = Math.min(
      1,
      desiredWidth / sourceWidth,
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

    var geometry = currentStereoGeometry();
    if (!geometry) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    var eyes = getRendererEyeCanvases();
    if (!eyes) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(
        sourceWidth,
        sourceHeight,
        geometry.rect
      );
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

    var geometry = currentStereoGeometry();
    if (!geometry) {
      reportInactive('ui-or-no-3d');
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      requestAnimationFrame(captureLoop);
      return;
    }

    reportActive();

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
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden', 'aria-modal']
  });

  addEventListener('resize', schedule, { passive: true });
  addEventListener('scroll', schedule, true);
  setInterval(schedule, 250);

  schedule();
  requestAnimationFrame(captureLoop);
  bridge('panelReady', '');
})();
