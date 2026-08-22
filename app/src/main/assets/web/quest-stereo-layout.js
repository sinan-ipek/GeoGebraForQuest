(function () {
  'use strict';

  if (window.__ggqStereoLayoutInstalled) return;
  window.__ggqStereoLayoutInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;

  // v0.9.17 diagnostic: v0.9.16 proved that even a nominal half of the
  // WebGL backing store still contains two visible views on Quest. Instead of
  // guessing the true eye boundary, capture four equal horizontal quarters.
  // Native code can then compare 1+2 versus 1+3 on the SAME verified
  // StereoMode.LeftRight VideoSurface without changing panel configuration.
  var CAPTURE_INTERVAL_MS = 100;
  var CAPTURE_MAX_QUARTER_WIDTH = 384;
  var CAPTURE_JPEG_QUALITY = 0.72;
  var lastCaptureAt = 0;

  var quarterCanvases = [];
  var quarterContexts = [];
  for (var i = 0; i < 4; i += 1) {
    var canvas = document.createElement('canvas');
    quarterCanvases.push(canvas);
    quarterContexts.push(canvas.getContext('2d', {
      alpha: false,
      desynchronized: true
    }));
  }

  function bridge(name, value) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge[name] === 'function') {
        window.QuestBridge[name](value);
      }
    } catch (_) {}
  }

  function bridgeStereoQuarters(q1, q2, q3, q4) {
    try {
      if (window.QuestBridge &&
          typeof window.QuestBridge.updateStereoQuarters === 'function') {
        window.QuestBridge.updateStereoQuarters(q1, q2, q3, q4);
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

  function ensureQuarterCanvasSize(width, height) {
    for (var i = 0; i < 4; i += 1) {
      if (quarterCanvases[i].width !== width) quarterCanvases[i].width = width;
      if (quarterCanvases[i].height !== height) quarterCanvases[i].height = height;
    }
  }

  function captureStereoQuarters() {
    for (var i = 0; i < 4; i += 1) {
      if (!quarterContexts[i]) return;
    }

    var source = find3DCanvas();
    if (!source || source.width < 8 || source.height < 2) return;

    try {
      var sourceQuarterWidth = Math.floor(source.width / 4);
      if (sourceQuarterWidth < 2) return;

      var scale = Math.min(1, CAPTURE_MAX_QUARTER_WIDTH / sourceQuarterWidth);
      var quarterWidth = Math.max(2, Math.round(sourceQuarterWidth * scale));
      var quarterHeight = Math.max(2, Math.round(source.height * scale));
      ensureQuarterCanvasSize(quarterWidth, quarterHeight);

      for (var q = 0; q < 4; q += 1) {
        var sourceX = q === 3
          ? source.width - sourceQuarterWidth
          : q * sourceQuarterWidth;
        quarterContexts[q].drawImage(
          source,
          sourceX, 0, sourceQuarterWidth, source.height,
          0, 0, quarterWidth, quarterHeight
        );
      }

      var urls = quarterCanvases.map(function (canvas) {
        return canvas.toDataURL('image/jpeg', CAPTURE_JPEG_QUALITY);
      });

      if (urls.every(function (url) { return url && url.length > 64; })) {
        bridgeStereoQuarters(urls[0], urls[1], urls[2], urls[3]);
      }
    } catch (_) {
      // GeoGebra may replace the canvas during a layout transition. The next
      // capture discovers the active WebGL canvas again.
    }
  }

  function captureLoop(now) {
    if (now - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
      lastCaptureAt = now;
      captureStereoQuarters();
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
