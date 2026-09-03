(function () {
  'use strict';

  // GeoGebraForQuest PC v0.12.3 XR-Behind Native runtime.
  // A remains the untouched native-DPI CEF GPU image on the PC.
  // B uses the proven Exp46 LEFT/RIGHT cameras, but its source size is derived from
  // Quest 3 angular pixel density instead of the Windows monitor resolution.
  // In XR, B is rendered behind an A-shaped transparent 3D hole. When a GeoGebra
  // menu/dialog covers the 3D viewport, B is disabled so A becomes fully opaque.
  if (window.__ggqPcStereoRuntimeInstalledV123) return;
  window.__ggqPcStereoRuntimeInstalledV123 = true;

  var CAPTURE_INTERVAL_MS = 33;
  var GEOMETRY_REFRESH_MS = 100;

  // Meta Quest 3: 25 PPD, 110 degree horizontal FOV, 2064x2208 physical per eye.
  // Our A plane is 1.65 m wide at 1.55 m, about 56 degrees horizontally.
  // 56 deg * 25 PPD is about 1400 useful texels. A small pre-warp margin puts the
  // full A target near 1536 texels. B gets only its proportional share of that.
  var QUEST3_PPD = 25.0;
  var XR_SCREEN_WIDTH_METERS = 1.65;
  var XR_SCREEN_DISTANCE_METERS = 1.55;
  var XR_SCREEN_FOV_DEG =
    2 * Math.atan((XR_SCREEN_WIDTH_METERS * 0.5) / XR_SCREEN_DISTANCE_METERS) *
    180 / Math.PI;
  var QUEST_FULL_A_TARGET_WIDTH = Math.round(XR_SCREEN_FOV_DEG * QUEST3_PPD * 1.09);
  QUEST_FULL_A_TARGET_WIDTH = Math.max(1280, Math.min(1536, QUEST_FULL_A_TARGET_WIDTH));

  var CAPTURE_MIN_EYE_WIDTH = 640;
  var CAPTURE_MAX_EYE_WIDTH = 1536;
  var CAPTURE_MAX_EYE_HEIGHT = 1664;
  var CAPTURE_JPEG_QUALITY = 0.99;

  var lastPayload = '';
  var lastCanvas = null;
  var geometryState = null;
  var geometryScheduled = false;
  var inactiveReported = false;

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
    if (Number(style.opacity) <= 0.001) return null;

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

  function visibleElement(element) {
    return !!rawRectOf(element);
  }

  function rectArea(rect) {
    return rect ? Math.max(0, rect.width) * Math.max(0, rect.height) : 0;
  }

  function classAndIdText(element) {
    if (!element) return '';
    var cls = '';
    try { cls = typeof element.className === 'string' ? element.className : ''; } catch (_) {}
    return (String(element.id || '') + ' ' + cls).toLowerCase();
  }

  function isMenuLike(element) {
    if (!element) return false;
    var role = String(element.getAttribute && element.getAttribute('role') || '').toLowerCase();
    var ariaModal = String(element.getAttribute && element.getAttribute('aria-modal') || '').toLowerCase();
    var tag = String(element.tagName || '').toLowerCase();
    if (role === 'menu' || role === 'menuitem' || role === 'dialog' ||
        role === 'listbox' || role === 'tree' || role === 'combobox' ||
        ariaModal === 'true' || tag === 'dialog') {
      return true;
    }

    var text = classAndIdText(element);
    return /(^|[\s_-])(menu|popup|dialog|dropdown|contextmenu|context-menu)([\s_-]|$)/.test(text) ||
      text.indexOf('gwt-popup') >= 0 ||
      text.indexOf('gwt-dialog') >= 0;
  }

  function hasPaint(element) {
    if (!element) return false;
    var style;
    try { style = getComputedStyle(element); } catch (_) { return false; }
    if (!style) return false;

    var background = String(style.backgroundColor || '');
    var backgroundImage = String(style.backgroundImage || 'none');
    var boxShadow = String(style.boxShadow || 'none');
    var borderWidth =
      parseFloat(style.borderTopWidth || '0') +
      parseFloat(style.borderRightWidth || '0') +
      parseFloat(style.borderBottomWidth || '0') +
      parseFloat(style.borderLeftWidth || '0');

    var coloredBackground =
      background &&
      background !== 'transparent' &&
      background !== 'rgba(0, 0, 0, 0)' &&
      background !== 'rgba(0,0,0,0)';

    var text = '';
    try { text = String(element.innerText || '').trim(); } catch (_) {}

    return coloredBackground || backgroundImage !== 'none' ||
      boxShadow !== 'none' || borderWidth > 0 || text.length > 0;
  }

  function canvasIndexInStack(stack, canvas) {
    for (var i = 0; i < stack.length; i++) {
      if (stack[i] === canvas) return i;
    }
    return -1;
  }

  function blockingElementAboveCanvasAt(x, y, canvas, panelArea) {
    var stack;
    try { stack = document.elementsFromPoint(x, y); } catch (_) { return null; }
    if (!stack || !stack.length) return null;

    var canvasIndex = canvasIndexInStack(stack, canvas);
    var limit = canvasIndex >= 0 ? canvasIndex : Math.min(stack.length, 6);

    for (var i = 0; i < limit; i++) {
      var element = stack[i];
      if (!element || element === canvas) continue;
      if (element.contains && element.contains(canvas)) continue;
      if (!visibleElement(element)) continue;

      var rect = rawRectOf(element);
      if (!rect) continue;

      // Small permanent 3D controls are allowed to coexist with B. Menus/dialogs are
      // never allowed to be cut out by the XR transparent hole.
      if (isMenuLike(element)) return element;
      if (rectArea(rect) < panelArea * 0.035) continue;

      var style;
      try { style = getComputedStyle(element); } catch (_) { style = null; }
      if (!style) continue;
      var z = parseInt(style.zIndex, 10);
      var positioned =
        style.position === 'fixed' ||
        style.position === 'absolute' ||
        style.position === 'sticky';

      if ((positioned || (isFinite(z) && z > 10)) && hasPaint(element)) {
        return element;
      }
    }
    return null;
  }

  function knownBlockingMenu(canvas, rect) {
    var selectors = [
      '[role="dialog"]',
      '[aria-modal="true"]',
      '[role="menu"]',
      '[role="listbox"]',
      '.gwt-PopupPanel',
      '.gwt-DialogBox',
      '[class*="Popup"]',
      '[class*="popup"]',
      '[class*="Dialog"]',
      '[class*="dialog"]',
      '[class*="Dropdown"]',
      '[class*="dropdown"]',
      '[class*="Menu"]',
      '[class*="menu"]'
    ].join(',');

    var candidates;
    try { candidates = document.querySelectorAll(selectors); } catch (_) { return false; }

    var panelArea = rectArea(rect);
    for (var i = 0; i < candidates.length; i++) {
      var element = candidates[i];
      if (!visibleElement(element)) continue;
      if (element === canvas ||
          (element.contains && element.contains(canvas)) ||
          (canvas.contains && canvas.contains(element))) continue;

      var er = rawRectOf(element);
      if (!er || !intersectRect(er, rect)) continue;

      var role = String(element.getAttribute && element.getAttribute('role') || '').toLowerCase();
      var ariaModal = String(element.getAttribute && element.getAttribute('aria-modal') || '').toLowerCase();
      var style;
      try { style = getComputedStyle(element); } catch (_) { style = null; }
      var positioned = style &&
        (style.position === 'absolute' || style.position === 'fixed' || style.position === 'sticky');
      var z = style ? parseInt(style.zIndex, 10) : NaN;

      if (role === 'dialog' || role === 'menu' || role === 'listbox' ||
          ariaModal === 'true' || positioned || (isFinite(z) && z > 10)) {
        if (rectArea(er) >= Math.max(400, panelArea * 0.01)) return true;
      }
    }
    return false;
  }

  function denseGridBlocked(canvas, rect) {
    var panelArea = rectArea(rect);
    var xs = [0.12, 0.30, 0.50, 0.70, 0.88];
    var ys = [0.12, 0.30, 0.50, 0.70, 0.88];

    for (var yi = 0; yi < ys.length; yi++) {
      for (var xi = 0; xi < xs.length; xi++) {
        var x = rect.left + rect.width * xs[xi];
        var y = rect.top + rect.height * ys[yi];
        var blocker = blockingElementAboveCanvasAt(x, y, canvas, panelArea);
        if (blocker && isMenuLike(blocker)) return true;
      }
    }
    return false;
  }

  function clipAgainstPersistentEdgePanels(canvas, rect) {
    var result = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height
    };
    var panelArea = rectArea(rect);

    function applyBlocker(blocker) {
      if (!blocker || isMenuLike(blocker)) return;
      var br = rawRectOf(blocker);
      if (!br) return;
      var overlap = intersectRect(br, result);
      if (!overlap) return;

      var currentRight = result.left + result.width;
      var currentBottom = result.top + result.height;
      var overlapVertical = overlap.height / Math.max(1, result.height);
      var overlapHorizontal = overlap.width / Math.max(1, result.width);

      if (overlapVertical >= 0.38 && br.left > result.left + result.width * 0.30) {
        result.width = Math.max(2, Math.min(currentRight, br.left) - result.left);
      } else if (overlapVertical >= 0.38 && br.left <= result.left + 2) {
        var newLeft = Math.max(result.left, br.left + br.width);
        result.width = Math.max(2, currentRight - newLeft);
        result.left = newLeft;
      } else if (overlapHorizontal >= 0.38 && br.top <= result.top + 2) {
        var newTop = Math.max(result.top, br.top + br.height);
        result.height = Math.max(2, currentBottom - newTop);
        result.top = newTop;
      } else if (overlapHorizontal >= 0.38 && br.top > result.top + result.height * 0.30) {
        result.height = Math.max(2, Math.min(currentBottom, br.top) - result.top);
      }
    }

    var samples = [0.25, 0.50, 0.75];
    for (var i = 0; i < samples.length; i++) {
      var y = rect.top + rect.height * samples[i];
      applyBlocker(blockingElementAboveCanvasAt(rect.left + 2, y, canvas, panelArea));
      applyBlocker(blockingElementAboveCanvasAt(rect.left + rect.width - 2, y, canvas, panelArea));
    }
    for (var j = 0; j < samples.length; j++) {
      var x = rect.left + rect.width * samples[j];
      applyBlocker(blockingElementAboveCanvasAt(x, rect.top + 2, canvas, panelArea));
      applyBlocker(blockingElementAboveCanvasAt(x, rect.top + rect.height - 2, canvas, panelArea));
    }

    return intersectRect(result, rect);
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
    geometryState = null;
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
    inactiveReported = false;
  }

  function refreshGeometry() {
    geometryScheduled = false;

    var canvas = find3DCanvas();
    var rect = clippedRectOf(canvas);
    if (!canvas || !rect) {
      reportInactive('no-3d');
      return;
    }

    // Floating GeoGebra UI has precedence over the XR stereo hole.
    if (knownBlockingMenu(canvas, rect) || denseGridBlocked(canvas, rect)) {
      reportInactive('ui-overlay');
      return;
    }

    // Persistent side/edge panels reduce the actual visible 3D viewport rather than
    // being covered by B.
    var visibleRect = clipAgainstPersistentEdgePanels(canvas, rect);
    if (!visibleRect || visibleRect.width < 20 || visibleRect.height < 20) {
      reportInactive('3d-clipped');
      return;
    }

    geometryState = { canvas: canvas, rect: visibleRect };
    reportActive();

    var payload = JSON.stringify({
      active: true,
      stereo: visibleRect,
      viewWidth: innerWidth,
      viewHeight: innerHeight
    });

    if (payload !== lastPayload) {
      lastPayload = payload;
      bridge('updateStereoLayout', payload);
    }
  }

  function scheduleGeometry() {
    if (geometryScheduled) return;
    geometryScheduled = true;
    requestAnimationFrame(refreshGeometry);
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
    var panelFraction = Math.max(0.02, Math.min(1, stereoRect.width / viewWidth));
    var desiredWidth = Math.round(QUEST_FULL_A_TARGET_WIDTH * panelFraction);
    desiredWidth = Math.max(CAPTURE_MIN_EYE_WIDTH, desiredWidth);
    desiredWidth = Math.min(CAPTURE_MAX_EYE_WIDTH, desiredWidth);

    var scale = Math.min(
      1,
      desiredWidth / Math.max(1, sourceWidth),
      CAPTURE_MAX_EYE_HEIGHT / Math.max(1, sourceHeight)
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
        reader.onerror = function () {
          reject(reader.error || new Error('FileReader hatası'));
        };
        reader.readAsDataURL(blob);
      }, 'image/jpeg', CAPTURE_JPEG_QUALITY);
    });
  }

  function beginAsyncStereoCapture(serial, requestedAt) {
    if (!leftCaptureContext || !rightCaptureContext || encodingInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
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

  if (window.ResizeObserver) {
    var resizeObserver = new ResizeObserver(scheduleGeometry);
    resizeObserver.observe(document.documentElement);
    if (document.body) resizeObserver.observe(document.body);
  }

  var mutationObserver = new MutationObserver(scheduleGeometry);
  mutationObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: [
      'class', 'style', 'hidden', 'aria-hidden', 'aria-modal',
      'role', 'open'
    ]
  });

  addEventListener('resize', scheduleGeometry, { passive: true });
  addEventListener('scroll', scheduleGeometry, true);
  addEventListener('pointerdown', scheduleGeometry, true);
  addEventListener('pointerup', scheduleGeometry, true);
  addEventListener('click', scheduleGeometry, true);
  addEventListener('focusin', scheduleGeometry, true);
  addEventListener('focusout', scheduleGeometry, true);

  setInterval(scheduleGeometry, GEOMETRY_REFRESH_MS);

  scheduleGeometry();
  requestAnimationFrame(captureLoop);
  bridge('panelReady', '');
})();
