(function () {
  'use strict';

  if (window.__ggqStereoLayoutInstalled) return;
  window.__ggqStereoLayoutInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;

  // Keep the proven stable capture path untouched: 20 fps, explicit left/right eye canvases.
  var CAPTURE_INTERVAL_MS = 50;
  var CAPTURE_MAX_EYE_WIDTH = 720;
  var CAPTURE_JPEG_QUALITY = 0.78;
  var lastCaptureAt = 0;
  var hasSeenActive3D = false;
  var inactiveReported = false;

  // Experimental embedded-stereo test: the visible 3D canvas is made optically transparent,
  // but remains pointer-active. Android places a non-hittable Spatial test panel behind it.
  var transparentRootPrepared = false;

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

  function reportStereoInactive() {
    if (!hasSeenActive3D || inactiveReported) return;
    inactiveReported = true;
    bridge('stereoInactive', '');
    // Also hide the embedded proof panel when the real 3D view is closed.
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }

  function reportStereoActive() {
    hasSeenActive3D = true;
    inactiveReported = false;
  }

  function prepareTransparentRoot() {
    if (transparentRootPrepared) return;
    transparentRootPrepared = true;

    try {
      document.documentElement.style.setProperty('background', 'transparent', 'important');
      if (document.body) {
        document.body.style.setProperty('background', 'transparent', 'important');
      }
      var root = document.getElementById('ggb-element');
      if (root) {
        root.style.setProperty('background', 'transparent', 'important');
      }
    } catch (_) {}
  }

  function markTransparentCarrier(node, canvasRect) {
    if (!node || node === document.documentElement || node === document.body) return;
    if (node.dataset && node.dataset.ggqStereoHoleCarrier === 'true') return;

    try {
      var r = node.getBoundingClientRect();
      var closeToCanvas =
        Math.abs(r.left - canvasRect.left) < 8 &&
        Math.abs(r.top - canvasRect.top) < 8 &&
        Math.abs(r.width - canvasRect.width) < 16 &&
        Math.abs(r.height - canvasRect.height) < 16;
      if (!closeToCanvas) return;

      if (node.dataset) node.dataset.ggqStereoHoleCarrier = 'true';
      node.style.setProperty('background', 'transparent', 'important');
      node.style.setProperty('background-color', 'transparent', 'important');
    } catch (_) {}
  }

  function ensureEmbeddedStereoHole(canvas) {
    if (!canvas || !canvas.isConnected) return;
    prepareTransparentRoot();

    try {
      if (!(canvas.dataset && canvas.dataset.ggqStereoHole === 'true')) {
        if (canvas.dataset) canvas.dataset.ggqStereoHole = 'true';
        // opacity:0 keeps hit-testing/pointer routing alive; do not use display:none,
        // visibility:hidden or pointer-events:none here.
        canvas.style.setProperty('opacity', '0', 'important');
        canvas.style.setProperty('background', 'transparent', 'important');
        canvas.style.setProperty('background-color', 'transparent', 'important');
        canvas.style.setProperty('pointer-events', 'auto', 'important');
      }

      var canvasRect = canvas.getBoundingClientRect();
      var node = canvas.parentElement;
      var depth = 0;
      while (node && depth < 6) {
        markTransparentCarrier(node, canvasRect);
        node = node.parentElement;
        depth++;
      }
    } catch (_) {}
  }

  function rectOf(element) {
    if (!element || !element.isConnected) return null;
    var style;
    try { style = getComputedStyle(element); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return null;

    // The deliberately transparent 3D canvas is still an active view in this experiment.
    var isStereoHole = !!(
      element.dataset && element.dataset.ggqStereoHole === 'true'
    );
    if (Number(style.opacity) === 0 && !isStereoHole) return null;

    var r = element.getBoundingClientRect();
    if (!r || r.width < 2 || r.height < 2) return null;
    if (r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return null;
    return {
      left: Math.max(0, r.left),
      top: Math.max(0, r.top),
      width: Math.max(0, Math.min(innerWidth, r.right) - Math.max(0, r.left)),
      height: Math.max(0, Math.min(innerHeight, r.bottom) - Math.max(0, r.top))
    };
  }

  function isWebGLCanvas(canvas) {
    if (!canvas) return false;
    try {
      return !!(canvas.getContext('webgl2') || canvas.getContext('webgl') ||
          canvas.getContext('experimental-webgl'));
    } catch (_) {
      return false;
    }
  }

  function findVisible3DCanvas() {
    var root = document.getElementById('ggb-element') || document;
    var canvases = Array.prototype.slice.call(root.querySelectorAll('canvas'));
    var best = null;
    var bestArea = 0;

    canvases.forEach(function (canvas) {
      var r = rectOf(canvas);
      if (!r || !isWebGLCanvas(canvas)) return;
      var area = r.width * r.height;
      var stereoBacking = canvas.width >= Math.floor(
        r.width * (window.devicePixelRatio || 1) * 1.7
      );
      var score = area * (stereoBacking ? 4 : 1);
      if (score > bestArea) {
        bestArea = score;
        best = canvas;
      }
    });

    if (best) {
      lastCanvas = best;
      ensureEmbeddedStereoHole(best);
    }
    return best;
  }

  function find3DCanvas() {
    var visible = findVisible3DCanvas();
    if (visible) return visible;
    return lastCanvas && lastCanvas.isConnected ? lastCanvas : null;
  }

  function intersects(a, b) {
    return a.left < b.left + b.width &&
      a.left + a.width > b.left &&
      a.top < b.top + b.height &&
      a.top + a.height > b.top;
  }

  function intersection(a, b) {
    var left = Math.max(a.left, b.left);
    var top = Math.max(a.top, b.top);
    var right = Math.min(a.left + a.width, b.left + b.width);
    var bottom = Math.min(a.top + a.height, b.top + b.height);
    if (right <= left || bottom <= top) return null;
    return { left: left, top: top, width: right - left, height: bottom - top };
  }

  function collectOcclusions(stereoRect, canvas) {
    var selectors = [
      '[role="dialog"]',
      '[aria-modal="true"]',
      '.gwt-PopupPanel',
      '.popup',
      '.popupPanel',
      '.menuPanel',
      '.matMenu',
      '.dialog',
      '.modal',
      '.propertiesPanel',
      '.contextMenu',
      '.selectionMenu',
      '.settingsView'
    ];

    var seen = new Set();
    var occlusions = [];

    selectors.forEach(function (selector) {
      var nodes;
      try { nodes = document.querySelectorAll(selector); } catch (_) { return; }
      Array.prototype.forEach.call(nodes, function (node) {
        if (!node || node === canvas || seen.has(node) || node.contains(canvas)) return;
        seen.add(node);
        var r = rectOf(node);
        if (!r || !intersects(r, stereoRect)) return;
        var clipped = intersection(r, stereoRect);
        if (!clipped || clipped.width * clipped.height < 16) return;
        occlusions.push(clipped);
      });
    });

    occlusions.sort(function (a, b) {
      return b.width * b.height - a.width * a.height;
    });
    return occlusions.slice(0, 4);
  }

  function sendLayout() {
    scheduled = false;
    var canvas = find3DCanvas();
    var stereoRect = rectOf(canvas);
    if (!stereoRect) return;

    var payload = JSON.stringify({
      active: true,
      stereo: stereoRect,
      viewWidth: innerWidth,
      viewHeight: innerHeight,
      occlusions: collectOcclusions(stereoRect, canvas)
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

  function ensureCaptureCanvasSize(width, height) {
    if (leftCaptureCanvas.width !== width) leftCaptureCanvas.width = width;
    if (leftCaptureCanvas.height !== height) leftCaptureCanvas.height = height;
    if (rightCaptureCanvas.width !== width) rightCaptureCanvas.width = width;
    if (rightCaptureCanvas.height !== height) rightCaptureCanvas.height = height;
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

  function captureStereoEyes() {
    if (!leftCaptureContext || !rightCaptureContext) return;

    var visible3DCanvas = findVisible3DCanvas();
    if (!visible3DCanvas) {
      reportStereoInactive();
      return;
    }
    reportStereoActive();

    var eyes = getRendererEyeCanvases();
    if (!eyes) return;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return;

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

      var leftDataUrl = leftCaptureCanvas.toDataURL(
        'image/jpeg',
        CAPTURE_JPEG_QUALITY
      );
      var rightDataUrl = rightCaptureCanvas.toDataURL(
        'image/jpeg',
        CAPTURE_JPEG_QUALITY
      );

      if (
        leftDataUrl && leftDataUrl.length > 64 &&
        rightDataUrl && rightDataUrl.length > 64
      ) {
        bridgeStereoEyes(leftDataUrl, rightDataUrl);
      }
    } catch (_) {
      // Renderer canvases can be replaced during a 3D view reconstruction.
    }
  }

  function captureLoop(now) {
    if (now - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
      lastCaptureAt = now;
      captureStereoEyes();
    }
    requestAnimationFrame(captureLoop);
  }

  if (window.ResizeObserver) {
    var resizeObserver = new ResizeObserver(schedule);
    resizeObserver.observe(document.documentElement);
    if (document.body) resizeObserver.observe(document.body);
  }

  var mutationObserver = new MutationObserver(function () {
    schedule();
    if (!findVisible3DCanvas()) reportStereoInactive();
  });
  mutationObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden']
  });

  addEventListener('resize', schedule, { passive: true });
  addEventListener('scroll', schedule, true);

  setInterval(schedule, 500);

  schedule();
  requestAnimationFrame(captureLoop);
  bridge('panelReady', '');
})();
