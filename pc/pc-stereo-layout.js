(function () {
  'use strict';

  // GeoGebraForQuest PC v0.13 GPU stereo transport.
  // No JPEG, no base64, no CPU image decode. The Exp46 left-eye image is
  // temporarily composited over the native 3D rectangle; the host copies that
  // rectangle directly from CEF's shared D3D11 texture. The right phase uses the
  // normal visible GeoGebra canvas. Transient left-eye frames are never presented
  // as A on the PC or in Quest.
  if (window.__ggqPcStereoRuntimeInstalledV13) return;
  window.__ggqPcStereoRuntimeInstalledV13 = true;

  var lastPayload = '';
  var lastCanvas = null;
  var scheduled = false;
  var inactiveReported = false;

  var transportState = 'idle';
  var transportBaseline = -1;
  var transportSerial = -1;
  var transportStartedAt = 0;
  var nextRequestAt = 0;
  var lastAckAt = performance.now();
  var overlay = null;
  var overlayContext = null;

  function post(message) {
    try {
      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
        window.CefSharp.PostMessage(message);
        return;
      }
      if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
        window.cefSharp.postMessage(message);
      }
    } catch (_) {}
  }

  function bridge(name, value) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge[name] === 'function') {
        window.QuestBridge[name](value);
      }
    } catch (_) {}
  }

  function reportRuntimeError(message) {
    post({ type: 'runtimeError', message: String(message || 'Stereo GPU transport error') });
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
    return { left: left, top: top, width: right - left, height: bottom - top };
  }

  function isWebGLCanvas(canvas) {
    if (!canvas) return false;
    try {
      return !!(canvas.getContext('webgl2') || canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl'));
    } catch (_) { return false; }
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
      if (score > bestScore) { bestScore = score; best = canvas; }
    });
    if (best) lastCanvas = best;
    return best;
  }

  function find3DCanvas() {
    return findVisible3DCanvas() || (lastCanvas && lastCanvas.isConnected ? lastCanvas : null);
  }

  function getRendererEyeCanvases() {
    var left = document.getElementById('ggq-renderer-left-eye');
    var right = document.getElementById('ggq-renderer-right-eye');
    if (!left || !right) return null;
    if (left.width < 2 || left.height < 2 || right.width < 2 || right.height < 2) return null;
    return { left: left, right: right };
  }

  function ensureOverlay() {
    if (overlay && overlay.isConnected && overlayContext) return true;
    overlay = document.createElement('canvas');
    overlay.id = 'ggq-pc-gpu-left-eye-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.position = 'fixed';
    overlay.style.margin = '0';
    overlay.style.padding = '0';
    overlay.style.border = '0';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '2147483646';
    overlay.style.display = 'none';
    overlay.style.background = 'transparent';
    overlay.style.transform = 'translateZ(0)';
    overlayContext = overlay.getContext('2d', { alpha: false, desynchronized: true });
    if (!overlayContext) { overlay = null; return false; }
    overlayContext.imageSmoothingEnabled = true;
    overlayContext.imageSmoothingQuality = 'high';
    (document.body || document.documentElement).appendChild(overlay);
    return true;
  }

  function hideOverlay() {
    if (overlay) overlay.style.display = 'none';
  }

  function showLeftOverlay() {
    var visible = find3DCanvas();
    var rect = rectOf(visible);
    var eyes = getRendererEyeCanvases();
    if (!visible || !rect || !eyes || !ensureOverlay()) return false;
    var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
    var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
    if (sourceWidth < 2 || sourceHeight < 2) return false;
    if (overlay.width !== sourceWidth) overlay.width = sourceWidth;
    if (overlay.height !== sourceHeight) overlay.height = sourceHeight;
    overlay.style.left = rect.left + 'px';
    overlay.style.top = rect.top + 'px';
    overlay.style.width = rect.width + 'px';
    overlay.style.height = rect.height + 'px';
    overlayContext.imageSmoothingEnabled = true;
    overlayContext.imageSmoothingQuality = 'high';
    overlayContext.clearRect(0, 0, sourceWidth, sourceHeight);
    overlayContext.drawImage(eyes.left, 0, 0, sourceWidth, sourceHeight,
      0, 0, sourceWidth, sourceHeight);
    overlay.style.display = 'block';
    return true;
  }

  function sendLayout() {
    scheduled = false;
    var canvas = find3DCanvas();
    var rect = rectOf(canvas);
    if (!canvas || !rect) { reportInactive(); return; }
    inactiveReported = false;
    var payload = JSON.stringify({ active: true, stereo: rect,
      viewWidth: innerWidth, viewHeight: innerHeight });
    if (payload === lastPayload) return;
    lastPayload = payload;
    bridge('updateStereoLayout', payload);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(sendLayout);
  }

  function resetTransport() {
    hideOverlay();
    transportState = 'idle';
    transportBaseline = -1;
    transportSerial = -1;
    transportStartedAt = 0;
    nextRequestAt = performance.now() + 30;
  }

  function reportInactive() {
    resetTransport();
    if (inactiveReported) return;
    inactiveReported = true;
    lastPayload = '';
    bridge('stereoInactive', '');
    bridge('updateStereoLayout', JSON.stringify({ active: false,
      viewWidth: innerWidth, viewHeight: innerHeight }));
  }

  function readStereoFrameSerial() {
    try {
      if (typeof window.ggqGetStereoFrameSerial !== 'function') return -1;
      var serial = Number(window.ggqGetStereoFrameSerial());
      return isFinite(serial) ? serial : -1;
    } catch (_) { return -1; }
  }

  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') return false;
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) return false;
      transportBaseline = baseline;
      transportStartedAt = now;
      transportState = 'wait-serial';
      return true;
    } catch (_) { return false; }
  }

  function postPhase(eye, serial) {
    post({ type: 'stereoGpuPhase', eye: eye, serial: serial });
  }

  window.ggqPcGpuTransport = {
    ack: function (eye, serial) {
      serial = Number(serial);
      if (!isFinite(serial) || serial !== transportSerial) return false;
      lastAckAt = performance.now();
      if (eye === 'left' && transportState === 'left-wait-ack') {
        hideOverlay();
        transportState = 'right-wait-ack';
        requestAnimationFrame(function () { postPhase('right', transportSerial); });
        return true;
      }
      if (eye === 'right' && transportState === 'right-wait-ack') {
        transportState = 'idle';
        transportBaseline = -1;
        transportSerial = -1;
        transportStartedAt = 0;
        nextRequestAt = performance.now() + 2;
        return true;
      }
      return false;
    },
    cancel: function () { resetTransport(); return true; }
  };

  function transportLoop(now) {
    var canvas = find3DCanvas();
    var rect = rectOf(canvas);
    if (!canvas || !rect) {
      reportInactive();
      requestAnimationFrame(transportLoop);
      return;
    }
    inactiveReported = false;
    if ((transportState === 'left-wait-ack' || transportState === 'right-wait-ack') &&
        now - lastAckAt > 350) {
      resetTransport();
    }
    if (transportState === 'wait-serial') {
      var serial = readStereoFrameSerial();
      if (serial > transportBaseline) {
        transportSerial = serial;
        if (showLeftOverlay()) {
          transportState = 'left-wait-ack';
          requestAnimationFrame(function () { postPhase('left', transportSerial); });
        } else {
          resetTransport();
        }
      } else if (now - transportStartedAt > 250) {
        resetTransport();
      }
    } else if (transportState === 'idle' && now >= nextRequestAt) {
      if (!requestStereoPair(now)) nextRequestAt = now + 16;
    }
    requestAnimationFrame(transportLoop);
  }

  if (window.ResizeObserver) {
    var resizeObserver = new ResizeObserver(schedule);
    resizeObserver.observe(document.documentElement);
    if (document.body) resizeObserver.observe(document.body);
  }
  var mutationObserver = new MutationObserver(schedule);
  mutationObserver.observe(document.documentElement, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ['class', 'hidden', 'aria-hidden']
  });
  addEventListener('resize', schedule, { passive: true });
  addEventListener('scroll', schedule, true);
  setInterval(schedule, 500);

  schedule();
  requestAnimationFrame(transportLoop);
  bridge('panelReady', '');
})();
