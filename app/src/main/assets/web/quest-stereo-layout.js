(function () {
  'use strict';

  if (window.__ggqStereoLayoutInstalled) return;
  window.__ggqStereoLayoutInstalled = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;

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

    // The shader has four cheap rectangle uniforms. Keep the four largest
    // overlays; GeoGebra normally has only one open popup/dialog at a time.
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

  // Low-frequency safety net for GeoGebra layout changes that do not mutate
  // observable DOM attributes. This never touches WebGL pixels.
  setInterval(schedule, 500);

  schedule();
  bridge('panelReady', '');
})();
