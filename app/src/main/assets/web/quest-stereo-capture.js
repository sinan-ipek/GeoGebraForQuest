(function () {
  'use strict';

  if (window.__ggqStereoCaptureV4) return;
  window.__ggqStereoCaptureV4 = true;

  // GeoGebraForQuest v0.6.3
  //
  // v0.6.1 proved the Android -> Spatial SDK -> StereoMode.LeftRight output.
  // v0.6.2 showed that no GeoGebra raw frame was emitted. The main cause was
  // upstream: older input interceptors prevented GeoGebra's own Glasses button
  // from receiving the real user gesture, so PROJECTION_GLASSES was never
  // reliably selected.
  //
  // This version no longer depends on replacing a WebGL context instance method.
  // It captures the finished WebGL drawing buffer on requestAnimationFrame while
  // stereo is armed. When GeoGebra is in its normal grayscale anaglyph mode, the
  // RED channel contains the left eye and GREEN/BLUE contain the right eye. We
  // decode those channels to two grayscale images, pack them SBS, and send them
  // to Android. A prototype colorMask observer is also installed as a fast path,
  // but rAF polling remains the fallback so cached WebGL methods cannot prevent
  // capture entirely.

  const MAX_EYE_WIDTH = 720;
  const MAX_EYE_HEIGHT = 720;
  const FRAME_INTERVAL_MS = 100;
  const JPEG_QUALITY = 0.82;
  const SWAP_EYES = false;

  let stereoActive = false;
  let last3DCanvas = null;
  let lastPortalRect = '';
  let apiWrapTimer = null;
  let lastFrameSentAt = 0;
  let captureLoopStarted = false;
  let sbsCanvas = null;
  let sbsContext = null;
  let sbsImageData = null;
  let sbsEyeWidth = 0;
  let sbsEyeHeight = 0;
  const maskState = new WeakMap();

  function log() {
    try {
      const args = Array.prototype.slice.call(arguments);
      args.unshift('[GGQ StereoCapture v0.6.3]');
      console.log.apply(console, args);
    } catch (_) {}
  }

  function bridgeCall(name) {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge[name] !== 'function') return;
      const args = Array.prototype.slice.call(arguments, 1);
      window.QuestBridge[name].apply(window.QuestBridge, args);
    } catch (error) {
      console.error('[GGQ StereoCapture bridge]', name, error);
    }
  }

  function visibleRect(canvas) {
    if (!canvas || !canvas.getBoundingClientRect) return null;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 160 || rect.height < 140) return null;
    if (rect.right <= 0 || rect.bottom <= 0 ||
        rect.left >= innerWidth || rect.top >= innerHeight) {
      return null;
    }
    return rect;
  }

  function contextOf(canvas) {
    if (!canvas) return null;
    try {
      return canvas.getContext('webgl2') ||
        canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl');
    } catch (_) {
      return null;
    }
  }

  function find3DCanvas() {
    const root = document.getElementById('ggb-element') || document;
    const canvases = Array.from(root.querySelectorAll('canvas'));
    let best = null;
    let bestArea = 0;

    for (const canvas of canvases) {
      const rect = visibleRect(canvas);
      if (!rect) continue;
      const gl = contextOf(canvas);
      if (!gl) continue;
      const area = rect.width * rect.height;
      if (area > bestArea) {
        bestArea = area;
        best = canvas;
      }
    }

    if (best) last3DCanvas = best;
    return best || last3DCanvas;
  }

  function sendPortalRect() {
    const canvas = find3DCanvas();
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const json = JSON.stringify({
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      viewWidth: innerWidth,
      viewHeight: innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1
    });
    if (json !== lastPortalRect) {
      lastPortalRect = json;
      bridgeCall('updatePortalRect', json);
    }
  }

  function projectionTable() {
    return document.querySelector('[data-ggq-projection-container="1"]');
  }

  function projectionButtons() {
    const table = projectionTable();
    if (!table) return [];
    let buttons = Array.from(table.querySelectorAll('.stylebarButton'));
    if (buttons.length < 4) {
      buttons = Array.from(table.querySelectorAll('td,button,[role="button"]'))
        .filter(function (node) { return node.offsetWidth > 0 && node.offsetHeight > 0; });
    }
    return buttons.slice(0, 4);
  }

  function dispatchProjection(index) {
    const buttons = projectionButtons();
    const target = buttons[index];
    if (!target) return false;

    const changed = [];
    let node = target;
    for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {
      if (node.dataset && node.dataset.ggqStereoTarget === '1') {
        changed.push(node);
        delete node.dataset.ggqStereoTarget;
      }
    }

    try {
      target.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window
      }));
      return true;
    } catch (error) {
      console.warn('[GGQ StereoCapture] projection dispatch failed', error);
      return false;
    } finally {
      changed.forEach(function (element) {
        if (element && element.dataset) element.dataset.ggqStereoTarget = '1';
      });
    }
  }

  function readFramebuffer(gl) {
    if (!gl) return null;
    const width = gl.drawingBufferWidth | 0;
    const height = gl.drawingBufferHeight | 0;
    if (width <= 0 || height <= 0) return null;
    if (width * height > 16000000) return null;

    const pixels = new Uint8Array(width * height * 4);
    try {
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    } catch (error) {
      console.warn('[GGQ StereoCapture] readPixels failed', error);
      return null;
    }
    return { pixels: pixels, width: width, height: height };
  }

  function targetEyeSize(sourceWidth, sourceHeight) {
    const scale = Math.min(
      1,
      MAX_EYE_WIDTH / Math.max(1, sourceWidth),
      MAX_EYE_HEIGHT / Math.max(1, sourceHeight)
    );
    return {
      width: Math.max(1, Math.round(sourceWidth * scale)),
      height: Math.max(1, Math.round(sourceHeight * scale))
    };
  }

  function ensureSbsCanvas(eyeWidth, eyeHeight) {
    if (sbsCanvas && sbsEyeWidth === eyeWidth && sbsEyeHeight === eyeHeight) return;

    if (sbsCanvas && sbsCanvas.parentNode) {
      try { sbsCanvas.parentNode.removeChild(sbsCanvas); } catch (_) {}
    }

    sbsEyeWidth = eyeWidth;
    sbsEyeHeight = eyeHeight;
    sbsCanvas = document.createElement('canvas');
    sbsCanvas.width = eyeWidth * 2;
    sbsCanvas.height = eyeHeight;
    sbsCanvas.style.display = 'none';
    sbsCanvas.setAttribute('aria-hidden', 'true');
    document.documentElement.appendChild(sbsCanvas);
    sbsContext = sbsCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
    sbsImageData = sbsContext.createImageData(eyeWidth * 2, eyeHeight);
  }

  function decodeAnaglyphToSbs(source) {
    if (!source) return null;

    const size = targetEyeSize(source.width, source.height);
    const eyeWidth = size.width;
    const eyeHeight = size.height;
    ensureSbsCanvas(eyeWidth, eyeHeight);

    const src = source.pixels;
    const srcW = source.width;
    const srcH = source.height;
    const out = sbsImageData.data;
    const fullOutW = eyeWidth * 2;

    for (let y = 0; y < eyeHeight; y += 1) {
      const sy = srcH - 1 - Math.min(srcH - 1, Math.floor(y * srcH / eyeHeight));
      for (let x = 0; x < eyeWidth; x += 1) {
        const sx = Math.min(srcW - 1, Math.floor(x * srcW / eyeWidth));
        const srcIndex = (sy * srcW + sx) * 4;

        const leftGray = src[srcIndex];
        const rightGray = Math.round((src[srcIndex + 1] + src[srcIndex + 2]) * 0.5);
        const firstGray = SWAP_EYES ? rightGray : leftGray;
        const secondGray = SWAP_EYES ? leftGray : rightGray;

        let dst = (y * fullOutW + x) * 4;
        out[dst] = firstGray;
        out[dst + 1] = firstGray;
        out[dst + 2] = firstGray;
        out[dst + 3] = 255;

        dst = (y * fullOutW + eyeWidth + x) * 4;
        out[dst] = secondGray;
        out[dst + 1] = secondGray;
        out[dst + 2] = secondGray;
        out[dst + 3] = 255;
      }
    }

    sbsContext.putImageData(sbsImageData, 0, 0);

    try {
      const dataUrl = sbsCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
      if (!dataUrl || dataUrl.length <= 64) return null;
      return { dataUrl: dataUrl, eyeWidth: eyeWidth, eyeHeight: eyeHeight };
    } catch (error) {
      console.warn('[GGQ StereoCapture] JPEG encode failed', error);
      return null;
    }
  }

  function captureAndSend(gl, force) {
    if (!stereoActive) return false;
    const now = performance.now();
    if (!force && now - lastFrameSentAt < FRAME_INTERVAL_MS) return false;

    const source = readFramebuffer(gl);
    const sbs = decodeAnaglyphToSbs(source);
    if (!sbs) return false;

    sendPortalRect();
    bridgeCall('submitStereoFrame', sbs.dataUrl, sbs.eyeWidth, sbs.eyeHeight);
    lastFrameSentAt = now;
    return true;
  }

  function classifyMask(red, green, blue, alpha) {
    const r = !!red;
    const g = !!green;
    const b = !!blue;
    const a = !!alpha;
    if (r && g && b && a) return 'all';
    if (r && !g && !b && a) return 'left';
    if (!r && g && b && a) return 'right';
    if (!r && !g && b && a) return 'right';
    return 'other';
  }

  function installPrototypeMaskHook(ctor, label) {
    if (!ctor || !ctor.prototype || typeof ctor.prototype.colorMask !== 'function') return;
    const proto = ctor.prototype;
    if (proto.colorMask.__ggqStereoMaskHook) return;

    const original = proto.colorMask;
    const wrapped = function (red, green, blue, alpha) {
      const result = original.call(this, red, green, blue, alpha);
      if (!stereoActive) return result;

      let state = maskState.get(this);
      if (!state) {
        state = { left: false, right: false };
        maskState.set(this, state);
      }

      const kind = classifyMask(red, green, blue, alpha);
      if (kind === 'left') {
        state.left = true;
      } else if (kind === 'right' && state.left) {
        state.right = true;
      } else if (kind === 'all' && state.left && state.right) {
        captureAndSend(this, false);
        state.left = false;
        state.right = false;
      }
      return result;
    };
    wrapped.__ggqStereoMaskHook = true;

    try {
      proto.colorMask = wrapped;
      log('Installed prototype colorMask hook:', label);
    } catch (error) {
      console.warn('[GGQ StereoCapture] prototype hook failed', label, error);
    }
  }

  installPrototypeMaskHook(window.WebGLRenderingContext, 'WebGL1');
  installPrototypeMaskHook(window.WebGL2RenderingContext, 'WebGL2');

  function captureLoop() {
    if (stereoActive) {
      const canvas = find3DCanvas();
      const gl = contextOf(canvas);
      if (gl) captureAndSend(gl, false);
    }
    requestAnimationFrame(captureLoop);
  }

  function ensureCaptureLoop() {
    if (captureLoopStarted) return;
    captureLoopStarted = true;
    requestAnimationFrame(captureLoop);
  }

  function setStereoEnabled(enabled, preserveProjection) {
    const next = !!enabled;
    const preserve = !!preserveProjection;

    if (stereoActive === next) {
      if (next) {
        sendPortalRect();
        ensureCaptureLoop();
      }
      return;
    }

    stereoActive = next;
    document.documentElement.dataset.ggqStereo = next ? 'on' : 'off';

    if (next) {
      lastFrameSentAt = 0;
      sendPortalRect();
      ensureCaptureLoop();
    } else {
      lastFrameSentAt = 0;
      if (!preserve) {
        setTimeout(function () { dispatchProjection(1); }, 0);
      }
    }

    bridgeCall('setStereoEnabled', next);
    log('Stereo capture', next ? 'ON' : 'OFF');
  }

  function wrapGeoGebraApi() {
    const api = window.GeoGebraForQuest;
    if (!api || typeof api.setStereoEnabled !== 'function') return false;
    if (api.setStereoEnabled.__ggqStereoCaptureWrappedV4) return true;

    const replacement = function (enabled, preserveProjection) {
      setStereoEnabled(enabled, preserveProjection);
    };
    replacement.__ggqStereoCaptureWrappedV4 = true;
    api.setStereoEnabled = replacement;
    log('Wrapped GeoGebraForQuest.setStereoEnabled');
    return true;
  }

  apiWrapTimer = setInterval(function () {
    if (wrapGeoGebraApi()) {
      clearInterval(apiWrapTimer);
      apiWrapTimer = null;
    }
  }, 100);

  window.addEventListener('resize', function () {
    if (stereoActive) sendPortalRect();
  });

  window.GeoGebraQuestStereoCapture = {
    enable: function () { setStereoEnabled(true, false); },
    disable: function () { setStereoEnabled(false, false); },
    isEnabled: function () { return stereoActive; },
    captureNow: function () {
      const canvas = find3DCanvas();
      const gl = contextOf(canvas);
      return gl ? captureAndSend(gl, true) : false;
    },
    setSwapEyes: function () { return SWAP_EYES; }
  };
})();
