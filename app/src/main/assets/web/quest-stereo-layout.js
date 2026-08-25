(function () {
  'use strict';

  if (window.__ggqStereoLayoutInstalled) return;
  window.__ggqStereoLayoutInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;

  // Exp3b selective-hole state. The critical rule is that the 20 fps capture path is read-only:
  // it may locate the 3D canvas, but it must never mutate DOM styles.
  var holeCanvas = null;
  var holeStyleRecords = [];
  var holeRectSignature = '';
  var holeApplyGeneration = 0;

  var CAPTURE_INTERVAL_MS = 50;
  var CAPTURE_MAX_EYE_WIDTH = 720;
  var CAPTURE_JPEG_QUALITY = 0.78;
  var lastCaptureAt = 0;
  var hasSeenActive3D = false;
  var inactiveReported = false;

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
    restoreSelectiveHole();
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false }));
  }

  function reportStereoActive() {
    hasSeenActive3D = true;
    inactiveReported = false;
  }

  function saveInlineStyle(node, property) {
    if (!node || !node.style) return;
    for (var i = 0; i < holeStyleRecords.length; i++) {
      var record = holeStyleRecords[i];
      if (record.node === node && record.property === property) return;
    }
    holeStyleRecords.push({
      node: node,
      property: property,
      value: node.style.getPropertyValue(property),
      priority: node.style.getPropertyPriority(property)
    });
  }

  function forceStyle(node, property, value) {
    if (!node || !node.style) return;
    try {
      // Avoid even a no-op style mutation. Exp3 repeatedly wrote the same values and its
      // MutationObserver watched style changes, creating a self-triggering UI-thread loop.
      if (node.style.getPropertyValue(property) === value &&
          node.style.getPropertyPriority(property) === 'important') {
        return;
      }
      saveInlineStyle(node, property);
      node.style.setProperty(property, value, 'important');
    } catch (_) {}
  }

  function transparentBackground(node) {
    if (!node || !node.style) return;
    forceStyle(node, 'background', 'transparent');
    forceStyle(node, 'background-color', 'transparent');
    forceStyle(node, 'background-image', 'none');
  }

  function restoreSelectiveHole() {
    holeApplyGeneration++;
    for (var i = holeStyleRecords.length - 1; i >= 0; i--) {
      var record = holeStyleRecords[i];
      if (!record.node || !record.node.style) continue;
      try {
        if (record.value) {
          record.node.style.setProperty(record.property, record.value, record.priority || '');
        } else {
          record.node.style.removeProperty(record.property);
        }
      } catch (_) {}
    }
    holeStyleRecords = [];
    if (holeCanvas && holeCanvas.dataset) {
      try { delete holeCanvas.dataset.ggqStereoHole; } catch (_) {}
    }
    holeCanvas = null;
    holeRectSignature = '';
  }

  function rawRect(element) {
    if (!element || !element.isConnected) return null;
    var r;
    try { r = element.getBoundingClientRect(); } catch (_) { return null; }
    if (!r || r.width < 2 || r.height < 2) return null;
    return {
      left: r.left,
      top: r.top,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height
    };
  }

  function rectSignature(rect) {
    if (!rect) return '';
    return [
      Math.round(rect.left),
      Math.round(rect.top),
      Math.round(rect.width),
      Math.round(rect.height)
    ].join(':');
  }

  function intersectionArea(a, b) {
    var left = Math.max(a.left, b.left);
    var top = Math.max(a.top, b.top);
    var right = Math.min(a.right, b.right);
    var bottom = Math.min(a.bottom, b.bottom);
    if (right <= left || bottom <= top) return 0;
    return (right - left) * (bottom - top);
  }

  function coversMostOfCanvas(node, canvasRect) {
    var r = rawRect(node);
    if (!r) return false;
    var canvasArea = canvasRect.width * canvasRect.height;
    if (canvasArea <= 0) return false;
    return intersectionArea(r, canvasRect) / canvasArea >= 0.55;
  }

  function collectCoveringLayers(canvas, canvasRect) {
    var layers = [];
    var seen = new Set();

    function add(node) {
      if (!node || seen.has(node)) return;
      seen.add(node);
      layers.push(node);
    }

    var root = document.getElementById('ggb-element');
    var node = canvas;
    while (node) {
      add(node);
      if (node === root) break;
      node = node.parentElement;
    }
    add(root);
    add(document.body);
    add(document.documentElement);

    // This paint-stack sampling is intentionally expensive, so exp3b executes it only when
    // a new 3D canvas appears or its rectangle actually changes, plus two finite settling passes.
    var insetX = Math.max(2, Math.min(12, canvasRect.width * 0.05));
    var insetY = Math.max(2, Math.min(12, canvasRect.height * 0.05));
    var samples = [
      [canvasRect.left + canvasRect.width * 0.50, canvasRect.top + canvasRect.height * 0.50],
      [canvasRect.left + insetX, canvasRect.top + insetY],
      [canvasRect.right - insetX, canvasRect.top + insetY],
      [canvasRect.left + insetX, canvasRect.bottom - insetY],
      [canvasRect.right - insetX, canvasRect.bottom - insetY]
    ];

    samples.forEach(function (point) {
      var stack = [];
      try { stack = document.elementsFromPoint(point[0], point[1]); } catch (_) {}
      for (var i = 0; i < stack.length; i++) {
        var candidate = stack[i];
        if (!candidate || candidate === document.documentElement || candidate === document.body) {
          continue;
        }
        if (!root || candidate === root || root.contains(candidate)) {
          if (candidate === canvas ||
              candidate.contains(canvas) ||
              coversMostOfCanvas(candidate, canvasRect)) {
            add(candidate);
          }
        }
      }
    });

    return layers;
  }

  function applySelectiveHole(canvas, force) {
    if (!canvas || !canvas.isConnected) return;

    var canvasRect = rawRect(canvas);
    if (!canvasRect) return;
    var signature = rectSignature(canvasRect);

    if (!force && holeCanvas === canvas && holeRectSignature === signature) {
      return;
    }

    // When the target or geometry changes, restore the previous finite set first so we never
    // accumulate stale transparent styles on old GeoGebra carriers.
    if (holeCanvas) {
      restoreSelectiveHole();
    }

    holeCanvas = canvas;
    holeRectSignature = signature;
    var generation = ++holeApplyGeneration;

    if (canvas.dataset) canvas.dataset.ggqStereoHole = 'true';
    forceStyle(canvas, 'opacity', '0');
    forceStyle(canvas, 'pointer-events', 'auto');
    transparentBackground(canvas);

    var layers = collectCoveringLayers(canvas, canvasRect);
    for (var i = 0; i < layers.length; i++) {
      if (layers[i] !== canvas) transparentBackground(layers[i]);
    }

    // GeoGebra can finish constructing a carrier shortly after the WebGL canvas appears.
    // Do exactly two delayed settling passes, never a repeating style-write loop.
    if (!force) {
      setTimeout(function () {
        if (generation !== holeApplyGeneration || holeCanvas !== canvas || !canvas.isConnected) {
          return;
        }
        applySelectiveHole(canvas, true);
      }, 250);

      setTimeout(function () {
        if (holeCanvas !== canvas || !canvas.isConnected) return;
        applySelectiveHole(canvas, true);
      }, 1000);
    }
  }

  function rectOf(element) {
    if (!element || !element.isConnected) return null;
    var style;
    try { style = getComputedStyle(element); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return null;

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

  // Pure read-only lookup. Never call applySelectiveHole() from here.
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

    if (best) lastCanvas = best;
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

    var canvas = findVisible3DCanvas();
    if (!canvas) {
      if (holeCanvas) restoreSelectiveHole();
      reportStereoInactive();
      return;
    }

    reportStereoActive();

    // This is the only normal path that mutates styles. It runs on layout/DOM signals or the
    // 500 ms watchdog, and applySelectiveHole() becomes a no-op unless target geometry changed.
    applySelectiveHole(canvas, false);

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

    // Read-only 20 fps path: no selective-hole style writes and no elementsFromPoint scanning.
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
    } catch (_) {}
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
    // Never observe "style": exp3's own transparent style writes recursively retriggered this
    // observer and froze the GeoGebra WebView. Structural/class/visibility changes are enough to
    // detect view creation/removal; the 500 ms watchdog covers missed cases.
    schedule();
  });
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
