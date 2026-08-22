(function () {
  'use strict';

  if (window.__ggqStereoLayoutInstalled) return;
  window.__ggqStereoLayoutInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;

  // v0.9.13 live stereo capture. Keep this deliberately bounded: synchronous
  // JPEG encoding in a WebView is expensive, so stale native frames are also
  // dropped by LiveStereoFrameSink instead of building latency.
  var CAPTURE_INTERVAL_MS = 100;
  var CAPTURE_MAX_WIDTH = 1152;
  var CAPTURE_JPEG_QUALITY = 0.72;
  var lastCaptureAt = 0;
  var captureCanvas = document.createElement('canvas');
  var captureContext = captureCanvas.getContext('2d', {
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

  function rectOf(element) {
    if (!element || !element.isConnected) return null;
    var style;
    try { style = getComputedStyle(element); } catch (_) { return null; }
    if (!style || style.display === 'none' || style.visibility === 'hidden') return null;
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

  function find3DCanvas() {
    var root = document.getElementById('ggb-element') || document;
    var canvases = Array.prototype.slice.call(root.querySelectorAll('canvas'));
    var best = null;
    var bestArea = 0;

    canvases.forEach(function (canvas) {
      var r = rectOf(canvas);
      if (!r || !isWebGLCanvas(canvas)) return;
      var area = r.width * r.height;
      // The source Quest renderer owns the 2x-wide WebGL backing store. Prefer
      // that canvas when more than one WebGL canvas is temporarily present.
      var stereoBacking = canvas.width >= Math.floor(r.width * (window.devicePixelRatio || 1) * 1.7);
      var score = area * (stereoBacking ? 4 : 1);
      if (score > bestArea) {
        bestArea = score;
        best = canvas;
      }
    });

    if (best) lastCanvas = best;
    return best || (lastCanvas && lastCanvas.isConnected ? lastCanvas : null);
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

  function captureStereoFrame() {
    if (!captureContext) return;

    var source = find3DCanvas();
    if (!source || source.width < 4 || source.height < 2) return;

    try {
      var scale = Math.min(1, CAPTURE_MAX_WIDTH / source.width);
      var width = Math.max(4, Math.round(source.width * scale));
      // StereoMode.LeftRight requires two exactly equal horizontal halves.
      if (width % 2 !== 0) width -= 1;
      var height = Math.max(2, Math.round(source.height * scale));

      if (captureCanvas.width !== width) captureCanvas.width = width;
      if (captureCanvas.height !== height) captureCanvas.height = height;

      captureContext.drawImage(
        source,
        0, 0, source.width, source.height,
        0, 0, width, height
      );

      var dataUrl = captureCanvas.toDataURL('image/jpeg', CAPTURE_JPEG_QUALITY);
      if (dataUrl && dataUrl.length > 64) {
        bridge('updateStereoFrame', dataUrl);
      }
    } catch (_) {
      // Canvas may be replaced during a GeoGebra layout transition. The next
      // scheduled capture will discover the new active 3D canvas.
    }
  }

  function captureLoop(now) {
    if (now - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
      lastCaptureAt = now;
      captureStereoFrame();
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
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden']
  });

  addEventListener('resize', schedule, { passive: true });
  addEventListener('scroll', schedule, true);

  setInterval(schedule, 500);

  schedule();
  requestAnimationFrame(captureLoop);
  bridge('panelReady', '');
})();
