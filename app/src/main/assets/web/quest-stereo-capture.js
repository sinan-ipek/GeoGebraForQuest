(function () {
  'use strict';

  if (window.__ggqStereoCaptureV071) return;
  window.__ggqStereoCaptureV071 = true;

  // GeoGebraForQuest direct-eye capture.
  //
  // GeoGebra's Glasses renderer draws LEFT and RIGHT into the same WebGL
  // framebuffer using red/cyan colour masks. We intercept only those two eye
  // masks and temporarily replace them with RGBA=all. Thus each eye is rendered
  // as a complete RGB image before readPixels(), while GeoGebra still supplies
  // the correct left/right camera matrices. NONE/ALPHA masks used for hidden
  // geometry are left untouched.
  //
  // This is the proven v0.7.1 capture path retained by v0.7.3. The v0.7.3 work
  // is in the WebView/stereo underlay composition and automatic colour/settings
  // handling; the working eye-pair capture itself is intentionally unchanged.

  const MAX_EYE_WIDTH = 720;
  const MAX_EYE_HEIGHT = 720;
  const FRAME_INTERVAL_MS = 33; // request up to ~30 fps; native busy-drop self-throttles
  const JPEG_QUALITY = 0.80;
  const SWAP_EYES = false;

  let stereoActive = false;
  let last3DCanvas = null;
  let lastPortalRect = '';
  let lastFrameSentAt = 0;
  let lastPairLogAt = 0;
  let apiWrapTimer = null;
  let hookTimer = null;

  let leftCanvas = null;
  let left2d = null;
  let rightCanvas = null;
  let right2d = null;
  let sbsCanvas = null;
  let sbs2d = null;
  let sourceWidth = 0;
  let sourceHeight = 0;
  let targetEyeWidth = 0;
  let targetEyeHeight = 0;

  const hookedContexts = new WeakSet();
  const contextStates = new WeakMap();

  function log() {
    try {
      const args = Array.prototype.slice.call(arguments);
      args.unshift('[GGQ StereoCapture v0.7.1]');
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
    try {
      const style = getComputedStyle(canvas);
      if (style.display === 'none' || style.visibility === 'hidden') return null;
    } catch (_) {}
    if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= innerWidth || rect.top >= innerHeight) {
      return null;
    }
    return rect;
  }

  function classifyMask(red, green, blue, alpha) {
    const r = !!red;
    const g = !!green;
    const b = !!blue;
    const a = !!alpha;
    if (!r && !g && !b && !a) return 'none';
    if (r && g && b && a) return 'all';
    if (r && !g && !b && a) return 'left';
    if (!r && g && b && a) return 'right';
    if (!r && !g && b && a) return 'right';
    if (!r && !g && !b && a) return 'alpha';
    return 'other';
  }

  function createState() {
    return {
      phase: 'idle',
      captureThisFrame: false,
      needsRightColorClear: false,
      width: 0,
      height: 0,
      leftPixels: null,
      rightPixels: null,
      leftReady: false
    };
  }

  function stateOf(gl) {
    let state = contextStates.get(gl);
    if (!state) {
      state = createState();
      contextStates.set(gl, state);
    }
    return state;
  }

  function resetPhase(state) {
    state.phase = 'idle';
    state.captureThisFrame = false;
    state.needsRightColorClear = false;
    state.leftReady = false;
  }

  function ensurePixelBuffers(gl, state) {
    const width = gl.drawingBufferWidth | 0;
    const height = gl.drawingBufferHeight | 0;
    if (width <= 0 || height <= 0 || width * height > 16000000) return false;
    if (state.width !== width || state.height !== height || !state.leftPixels || !state.rightPixels) {
      state.width = width;
      state.height = height;
      const bytes = width * height * 4;
      state.leftPixels = new Uint8Array(bytes);
      state.rightPixels = new Uint8Array(bytes);
    }
    return true;
  }

  function readInto(gl, pixels) {
    try {
      gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight,
        gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      return true;
    } catch (error) {
      console.warn('[GGQ StereoCapture] readPixels failed', error);
      return false;
    }
  }

  function framebufferHasSignal(pixels) {
    if (!pixels || !pixels.length) return false;
    const pixelCount = Math.max(1, pixels.length / 4);
    const sampleCount = Math.min(384, pixelCount);
    const stride = Math.max(1, Math.floor(pixelCount / sampleCount));
    let nonBlack = 0;
    let sampled = 0;
    for (let i = 0; i < pixelCount && sampled < sampleCount; i += stride) {
      const p = i * 4;
      if (pixels[p] + pixels[p + 1] + pixels[p + 2] > 8) nonBlack += 1;
      sampled += 1;
    }
    return nonBlack >= 2;
  }

  function targetSize(width, height) {
    const scale = Math.min(
      1,
      MAX_EYE_WIDTH / Math.max(1, width),
      MAX_EYE_HEIGHT / Math.max(1, height)
    );
    return {
      width: Math.max(1, Math.round(width * scale)),
      height: Math.max(1, Math.round(height * scale))
    };
  }

  function makeHiddenCanvas(width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.style.display = 'none';
    canvas.setAttribute('aria-hidden', 'true');
    document.documentElement.appendChild(canvas);
    return canvas;
  }

  function removeCanvas(canvas) {
    try {
      if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
    } catch (_) {}
  }

  function ensurePackingCanvases(width, height) {
    const size = targetSize(width, height);
    if (leftCanvas && sourceWidth === width && sourceHeight === height &&
        targetEyeWidth === size.width && targetEyeHeight === size.height) return;

    removeCanvas(leftCanvas);
    removeCanvas(rightCanvas);
    removeCanvas(sbsCanvas);

    sourceWidth = width;
    sourceHeight = height;
    targetEyeWidth = size.width;
    targetEyeHeight = size.height;

    leftCanvas = makeHiddenCanvas(width, height);
    rightCanvas = makeHiddenCanvas(width, height);
    sbsCanvas = makeHiddenCanvas(size.width * 2, size.height);

    left2d = leftCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
    right2d = rightCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
    sbs2d = sbsCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
  }

  function imageDataFromPixels(pixels, width, height) {
    return new ImageData(
      new Uint8ClampedArray(pixels.buffer, pixels.byteOffset, pixels.byteLength),
      width,
      height
    );
  }

  function packStereoPair(state) {
    if (!state.leftReady || !state.leftPixels || !state.rightPixels) return null;
    if (!framebufferHasSignal(state.leftPixels) || !framebufferHasSignal(state.rightPixels)) return null;

    ensurePackingCanvases(state.width, state.height);
    if (!left2d || !right2d || !sbs2d) return null;

    try {
      left2d.putImageData(imageDataFromPixels(state.leftPixels, state.width, state.height), 0, 0);
      right2d.putImageData(imageDataFromPixels(state.rightPixels, state.width, state.height), 0, 0);

      const first = SWAP_EYES ? rightCanvas : leftCanvas;
      const second = SWAP_EYES ? leftCanvas : rightCanvas;
      const ew = targetEyeWidth;
      const eh = targetEyeHeight;

      sbs2d.setTransform(1, 0, 0, 1, 0, 0);
      sbs2d.clearRect(0, 0, ew * 2, eh);
      sbs2d.setTransform(1, 0, 0, -1, 0, eh);
      sbs2d.drawImage(first, 0, 0, state.width, state.height, 0, 0, ew, eh);
      sbs2d.drawImage(second, 0, 0, state.width, state.height, ew, 0, ew, eh);
      sbs2d.setTransform(1, 0, 0, 1, 0, 0);

      const dataUrl = sbsCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
      if (!dataUrl || dataUrl.length <= 64) return null;
      return { dataUrl: dataUrl, eyeWidth: ew, eyeHeight: eh };
    } catch (error) {
      console.warn('[GGQ StereoCapture] SBS encode failed', error);
      return null;
    }
  }

  function sampledDifference(a, b) {
    if (!a || !b || a.length !== b.length) return -1;
    const pixelCount = Math.max(1, a.length / 4);
    const sampleCount = Math.min(384, pixelCount);
    const stride = Math.max(1, Math.floor(pixelCount / sampleCount));
    let sum = 0;
    let sampled = 0;
    for (let i = 0; i < pixelCount && sampled < sampleCount; i += stride) {
      const p = i * 4;
      sum += Math.abs(a[p] - b[p]);
      sum += Math.abs(a[p + 1] - b[p + 1]);
      sum += Math.abs(a[p + 2] - b[p + 2]);
      sampled += 1;
    }
    return sampled ? sum / (sampled * 3) : 0;
  }

  function emitStereoPair(state) {
    if (!stereoActive) return false;
    const sbs = packStereoPair(state);
    if (!sbs) return false;

    sendPortalRect();
    bridgeCall('submitStereoFrame', sbs.dataUrl, sbs.eyeWidth, sbs.eyeHeight);
    lastFrameSentAt = performance.now();

    if (lastFrameSentAt - lastPairLogAt > 1200) {
      lastPairLogAt = lastFrameSentAt;
      log('Direct eye pair', state.width + 'x' + state.height,
        '->', sbs.eyeWidth + 'x' + sbs.eyeHeight,
        'difference', sampledDifference(state.leftPixels, state.rightPixels).toFixed(2));
    }
    return true;
  }

  function hookContext(gl) {
    if (!gl || hookedContexts.has(gl)) return;
    if (typeof gl.colorMask !== 'function' || typeof gl.clear !== 'function') return;

    const originalColorMask = gl.colorMask.bind(gl);
    const originalClear = gl.clear.bind(gl);
    const state = stateOf(gl);

    const wrappedColorMask = function (red, green, blue, alpha) {
      const kind = classifyMask(red, green, blue, alpha);

      if (!stereoActive) {
        if (state.phase !== 'idle') resetPhase(state);
        return originalColorMask(red, green, blue, alpha);
      }

      if (kind === 'none' || kind === 'alpha' || kind === 'other') {
        return originalColorMask(red, green, blue, alpha);
      }

      if (kind === 'left') {
        if (state.phase !== 'left') {
          state.phase = 'left';
          state.captureThisFrame = performance.now() - lastFrameSentAt >= FRAME_INTERVAL_MS;
          state.leftReady = false;
          state.needsRightColorClear = false;
          if (state.captureThisFrame && !ensurePixelBuffers(gl, state)) {
            state.captureThisFrame = false;
          }
        }
        return originalColorMask(true, true, true, true);
      }

      if (kind === 'right') {
        if (state.phase === 'left') {
          if (state.captureThisFrame && state.leftPixels) {
            state.leftReady = readInto(gl, state.leftPixels);
          }
          state.phase = 'right';
          state.needsRightColorClear = true;
        }
        return originalColorMask(true, true, true, true);
      }

      if (kind === 'all') {
        if (state.phase === 'right') {
          if (state.captureThisFrame && state.leftReady && state.rightPixels) {
            if (readInto(gl, state.rightPixels)) emitStereoPair(state);
          }
          resetPhase(state);
        }
        return originalColorMask(true, true, true, true);
      }

      return originalColorMask(red, green, blue, alpha);
    };

    const wrappedClear = function (mask) {
      let nextMask = mask;
      if (stereoActive && state.phase === 'right' && state.needsRightColorClear &&
          (mask & gl.DEPTH_BUFFER_BIT) !== 0) {
        nextMask = mask | gl.COLOR_BUFFER_BIT;
        state.needsRightColorClear = false;
      }
      return originalClear(nextMask);
    };

    try { wrappedColorMask.__ggqStereoMaskHookV6 = true; } catch (_) {}
    try { wrappedClear.__ggqStereoClearHookV6 = true; } catch (_) {}
    try { gl.colorMask = wrappedColorMask; } catch (_) { return; }
    try { gl.clear = wrappedClear; } catch (_) {}

    hookedContexts.add(gl);
    log('Hooked GeoGebra WebGL context', gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  function installGetContextHook() {
    if (!window.HTMLCanvasElement || !HTMLCanvasElement.prototype) return;
    const proto = HTMLCanvasElement.prototype;
    if (proto.getContext && proto.getContext.__ggqStereoGetContextHookV6) return;

    const originalGetContext = proto.getContext;
    if (typeof originalGetContext !== 'function') return;

    const wrappedGetContext = function () {
      const context = originalGetContext.apply(this, arguments);
      const type = String(arguments[0] || '').toLowerCase();
      if (context && (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl')) {
        hookContext(context);
      }
      return context;
    };

    wrappedGetContext.__ggqStereoGetContextHookV6 = true;
    try {
      proto.getContext = wrappedGetContext;
      log('Installed document-start canvas.getContext hook');
    } catch (error) {
      console.warn('[GGQ StereoCapture] getContext hook failed', error);
    }
  }

  installGetContextHook();

  function rawContextOf(canvas) {
    if (!canvas) return null;
    try {
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (gl) hookContext(gl);
      return gl;
    } catch (_) {
      return null;
    }
  }

  function find3DCanvas() {
    const root = document.getElementById('ggb-element') || document;
    let best = null;
    let bestArea = 0;
    for (const canvas of Array.from(root.querySelectorAll('canvas'))) {
      const rect = visibleRect(canvas);
      if (!rect) continue;
      const gl = rawContextOf(canvas);
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
    if (!canvas || !canvas.isConnected) return;
    const rect = visibleRect(canvas);
    if (!rect) return;

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

  function hookCurrent3DContext() {
    const canvas = find3DCanvas();
    if (!canvas) return;
    const gl = rawContextOf(canvas);
    if (gl) hookContext(gl);
    if (stereoActive) sendPortalRect();
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
    const target = projectionButtons()[index];
    if (!target) return false;
    try {
      target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
      return true;
    } catch (_) {
      return false;
    }
  }

  function setStereoEnabled(enabled, preserveProjection) {
    const next = !!enabled;
    const preserve = !!preserveProjection;

    if (stereoActive === next) {
      if (next) {
        hookCurrent3DContext();
        sendPortalRect();
      }
      return;
    }

    stereoActive = next;
    document.documentElement.dataset.ggqStereo = next ? 'on' : 'off';
    lastFrameSentAt = 0;

    if (next) {
      hookCurrent3DContext();
      sendPortalRect();
    } else if (!preserve) {
      setTimeout(function () { dispatchProjection(1); }, 0);
    }

    bridgeCall('setStereoEnabled', next);
    log('Stereo capture', next ? 'ON' : 'OFF', preserve ? '(projection preserved)' : '');
  }

  function wrapGeoGebraApi() {
    const api = window.GeoGebraForQuest;
    if (!api || typeof api.setStereoEnabled !== 'function') return false;
    if (api.setStereoEnabled.__ggqStereoCaptureWrappedV6) return true;

    const replacement = function (enabled, preserveProjection) {
      setStereoEnabled(enabled, preserveProjection);
    };
    replacement.__ggqStereoCaptureWrappedV6 = true;
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

  hookTimer = setInterval(hookCurrent3DContext, 250);
  window.addEventListener('resize', function () { if (stereoActive) sendPortalRect(); });

  window.GeoGebraQuestStereoCapture = {
    enable: function () { setStereoEnabled(true, true); },
    disable: function (preserveProjection) { setStereoEnabled(false, !!preserveProjection); },
    isEnabled: function () { return stereoActive; },
    hookNow: hookCurrent3DContext,
    setSwapEyes: function () { return SWAP_EYES; },
    requestedFrameIntervalMs: function () { return FRAME_INTERVAL_MS; }
  };
})();
