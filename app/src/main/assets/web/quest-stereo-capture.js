(function () {
  'use strict';

  if (window.__ggqStereoCaptureV6) return;
  window.__ggqStereoCaptureV6 = true;

  // GeoGebraForQuest v0.6.5
  //
  // The previous build decoded the final red/cyan anaglyph framebuffer. That
  // transport reached Quest, but it still did not produce a dependable stereo
  // pair. v0.6.5 captures the two GeoGebra eye renders themselves.
  //
  // GeoGebra's Glasses renderer performs this sequence every frame:
  //
  //   RED colorMask                 left eye starts
  //   ... left-eye draw ...
  //   BLUE or BLUE+GREEN colorMask  right eye starts
  //   depth clear
  //   ... right-eye draw ...
  //   ALL colorMask                 frame ends
  //
  // While Quest stereo is enabled we replace only the actual eye masks with
  // RGBA=all so each eye is rendered as a complete full-colour image. Internal
  // NONE and ALPHA masks are preserved because GeoGebra uses them for hidden
  // geometry/occlusion. At the transition to the right eye we read the finished
  // left framebuffer. On the following depth clear we also clear colour so the
  // right eye starts from a clean buffer. At final ALL we read the finished
  // right framebuffer and pack LEFT | RIGHT as SBS.
  //
  // This file is also installed as a document-start script by Android, before
  // GeoGebra creates its WebGL context. That guarantees our getContext wrapper
  // sees the real renderer context before GeoGebra can cache WebGL methods.

  const MAX_EYE_WIDTH = 720;
  const MAX_EYE_HEIGHT = 720;
  const FRAME_INTERVAL_MS = 100;
  const JPEG_QUALITY = 0.84;
  const SWAP_EYES = false;

  let stereoActive = false;
  let last3DCanvas = null;
  let lastPortalRect = '';
  let apiWrapTimer = null;
  let hookTimer = null;
  let lastFrameSentAt = 0;
  let sbsCanvas = null;
  let sbsContext = null;
  let sbsImageData = null;
  let sbsEyeWidth = 0;
  let sbsEyeHeight = 0;

  const hookedContexts = new WeakSet();
  const contextStates = new WeakMap();

  function log() {
    try {
      const args = Array.prototype.slice.call(arguments);
      args.unshift('[GGQ StereoCapture v0.6.5]');
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
    if (
      rect.right <= 0 || rect.bottom <= 0 ||
      rect.left >= innerWidth || rect.top >= innerHeight
    ) {
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

  function newContextState() {
    return {
      phase: 'idle',
      captureThisFrame: false,
      left: null,
      needsRightColorClear: false
    };
  }

  function stateOf(gl) {
    let state = contextStates.get(gl);
    if (!state) {
      state = newContextState();
      contextStates.set(gl, state);
    }
    return state;
  }

  function resetContextState(gl) {
    contextStates.set(gl, newContextState());
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

  function framebufferHasSignal(source) {
    if (!source || !source.pixels || !source.pixels.length) return false;

    const pixels = source.pixels;
    const pixelCount = Math.max(1, pixels.length / 4);
    const sampleCount = Math.min(512, pixelCount);
    const stride = Math.max(1, Math.floor(pixelCount / sampleCount));

    let nonBlack = 0;
    let sampled = 0;
    for (let i = 0; i < pixelCount && sampled < sampleCount; i += stride) {
      const p = i * 4;
      if (pixels[p] + pixels[p + 1] + pixels[p + 2] > 8) {
        nonBlack += 1;
      }
      sampled += 1;
    }

    return nonBlack >= 2;
  }

  function pairDifference(left, right) {
    if (!left || !right || left.width !== right.width || left.height !== right.height) {
      return -1;
    }

    const a = left.pixels;
    const b = right.pixels;
    const pixelCount = Math.max(1, Math.min(a.length, b.length) / 4);
    const sampleCount = Math.min(768, pixelCount);
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

    return sampled > 0 ? sum / (sampled * 3) : 0;
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

    sbsContext = sbsCanvas.getContext('2d', {
      alpha: false,
      willReadFrequently: false
    });
    sbsImageData = sbsContext.createImageData(eyeWidth * 2, eyeHeight);
  }

  function packStereoPair(left, right) {
    if (!left || !right) return null;
    if (!framebufferHasSignal(left) || !framebufferHasSignal(right)) return null;
    if (left.width !== right.width || left.height !== right.height) return null;

    const size = targetEyeSize(left.width, left.height);
    const eyeWidth = size.width;
    const eyeHeight = size.height;
    ensureSbsCanvas(eyeWidth, eyeHeight);

    const first = SWAP_EYES ? right : left;
    const second = SWAP_EYES ? left : right;
    const firstPixels = first.pixels;
    const secondPixels = second.pixels;
    const srcW = left.width;
    const srcH = left.height;
    const out = sbsImageData.data;
    const fullOutW = eyeWidth * 2;

    for (let y = 0; y < eyeHeight; y += 1) {
      const sy = srcH - 1 - Math.min(
        srcH - 1,
        Math.floor(y * srcH / eyeHeight)
      );

      for (let x = 0; x < eyeWidth; x += 1) {
        const sx = Math.min(
          srcW - 1,
          Math.floor(x * srcW / eyeWidth)
        );
        const srcIndex = (sy * srcW + sx) * 4;

        let dst = (y * fullOutW + x) * 4;
        out[dst] = firstPixels[srcIndex];
        out[dst + 1] = firstPixels[srcIndex + 1];
        out[dst + 2] = firstPixels[srcIndex + 2];
        out[dst + 3] = 255;

        dst = (y * fullOutW + eyeWidth + x) * 4;
        out[dst] = secondPixels[srcIndex];
        out[dst + 1] = secondPixels[srcIndex + 1];
        out[dst + 2] = secondPixels[srcIndex + 2];
        out[dst + 3] = 255;
      }
    }

    sbsContext.putImageData(sbsImageData, 0, 0);

    try {
      const dataUrl = sbsCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
      if (!dataUrl || dataUrl.length <= 64) return null;
      return {
        dataUrl: dataUrl,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight
      };
    } catch (error) {
      console.warn('[GGQ StereoCapture] JPEG encode failed', error);
      return null;
    }
  }

  function emitStereoPair(left, right) {
    if (!stereoActive) return false;

    const sbs = packStereoPair(left, right);
    if (!sbs) {
      log('Ignored unusable direct eye pair');
      return false;
    }

    const diff = pairDifference(left, right);
    log('Direct eye pair', left.width + 'x' + left.height, 'difference', diff.toFixed(2));

    sendPortalRect();
    bridgeCall(
      'submitStereoFrame',
      sbs.dataUrl,
      sbs.eyeWidth,
      sbs.eyeHeight
    );
    lastFrameSentAt = performance.now();
    return true;
  }

  function hookContext(gl) {
    if (!gl || hookedContexts.has(gl)) return;
    if (typeof gl.colorMask !== 'function' || typeof gl.clear !== 'function') return;

    const originalColorMask = gl.colorMask.bind(gl);
    const originalClear = gl.clear.bind(gl);
    resetContextState(gl);

    gl.colorMask = function (red, green, blue, alpha) {
      const kind = classifyMask(red, green, blue, alpha);
      const state = stateOf(gl);

      if (!stereoActive) {
        if (state.phase !== 'idle') resetContextState(gl);
        return originalColorMask(red, green, blue, alpha);
      }

      // NONE/ALPHA are not eye transitions. GeoGebra uses these while drawing
      // occluded geometry, so preserving them is essential.
      if (kind === 'none' || kind === 'alpha' || kind === 'other') {
        return originalColorMask(red, green, blue, alpha);
      }

      if (kind === 'left') {
        if (state.phase !== 'left') {
          state.phase = 'left';
          state.captureThisFrame =
            performance.now() - lastFrameSentAt >= FRAME_INTERVAL_MS;
          state.left = null;
          state.needsRightColorClear = false;
        }

        // Render the actual left eye in full colour instead of RED-only.
        return originalColorMask(true, true, true, true);
      }

      if (kind === 'right') {
        if (state.phase === 'left') {
          if (state.captureThisFrame) {
            state.left = readFramebuffer(gl);
          }
          state.phase = 'right';
          state.needsRightColorClear = true;
        }

        // Repeated right masks after internal NONE are normal. Do not re-arm the
        // colour clear; only the first left->right transition does that.
        return originalColorMask(true, true, true, true);
      }

      if (kind === 'all') {
        if (state.phase === 'right') {
          if (state.captureThisFrame && state.left) {
            const right = readFramebuffer(gl);
            emitStereoPair(state.left, right);
          }
          resetContextState(gl);
        }
        return originalColorMask(true, true, true, true);
      }

      return originalColorMask(red, green, blue, alpha);
    };

    gl.clear = function (mask) {
      const state = stateOf(gl);
      let nextMask = mask;

      if (
        stereoActive &&
        state.phase === 'right' &&
        state.needsRightColorClear &&
        (mask & gl.DEPTH_BUFFER_BIT) !== 0
      ) {
        // GeoGebra normally clears only depth between anaglyph eyes because the
        // two colour-channel images share one framebuffer. We are capturing two
        // complete RGBA images, so the right eye needs a fresh colour buffer.
        nextMask = mask | gl.COLOR_BUFFER_BIT;
        state.needsRightColorClear = false;
      }

      return originalClear(nextMask);
    };

    try { gl.colorMask.__ggqStereoMaskHookV6 = true; } catch (_) {}
    try { gl.clear.__ggqStereoClearHookV6 = true; } catch (_) {}

    hookedContexts.add(gl);
    log('Hooked GeoGebra WebGL context', gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  // Document-start fast path. Because Android injects this file before GeoGebra,
  // every WebGL context created afterwards is hooked immediately.
  function installGetContextHook() {
    if (!window.HTMLCanvasElement || !HTMLCanvasElement.prototype) return;
    const proto = HTMLCanvasElement.prototype;
    if (proto.getContext && proto.getContext.__ggqStereoGetContextHookV6) return;

    const originalGetContext = proto.getContext;
    if (typeof originalGetContext !== 'function') return;

    const wrappedGetContext = function () {
      const context = originalGetContext.apply(this, arguments);
      const type = String(arguments[0] || '').toLowerCase();
      if (
        context &&
        (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl')
      ) {
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
      const gl = canvas.getContext('webgl2') ||
        canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl');
      if (gl) hookContext(gl);
      return gl;
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
        .filter(function (node) {
          return node.offsetWidth > 0 && node.offsetHeight > 0;
        });
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
        if (element && element.dataset) {
          element.dataset.ggqStereoTarget = '1';
        }
      });
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

    if (next) {
      lastFrameSentAt = 0;
      hookCurrent3DContext();
      sendPortalRect();
    } else {
      lastFrameSentAt = 0;
      contextStates.forEach;
      if (!preserve) {
        setTimeout(function () {
          dispatchProjection(1);
        }, 0);
      }
    }

    bridgeCall('setStereoEnabled', next);
    log('Stereo capture', next ? 'ON' : 'OFF');
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

  hookTimer = setInterval(function () {
    hookCurrent3DContext();
  }, 300);

  window.addEventListener('resize', function () {
    if (stereoActive) sendPortalRect();
  });

  window.GeoGebraQuestStereoCapture = {
    enable: function () {
      setStereoEnabled(true, false);
    },
    disable: function () {
      setStereoEnabled(false, false);
    },
    isEnabled: function () {
      return stereoActive;
    },
    hookNow: hookCurrent3DContext,
    setSwapEyes: function () {
      return SWAP_EYES;
    }
  };
})();
