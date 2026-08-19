(function () {
  'use strict';

  if (window.__ggqStereoCaptureV2) return;
  window.__ggqStereoCaptureV2 = true;

  // GeoGebraForQuest v0.5.2 stereo transport.
  //
  // GeoGebra's PROJECTION_GLASSES path renders the 3D view twice. The important
  // detail is that GeoGebra also temporarily uses ColorMask.NONE while drawing
  // hidden/occluded geometry inside EACH eye pass. v0.5.0/v0.5.1 treated every
  // non-ALL WebGL colorMask as an eye transition, so an internal NONE mask was
  // incorrectly mistaken for the right-eye pass. The result was exactly what we
  // saw on Quest: anaglyph filtering was bypassed, but no valid SBS pair reached
  // the stereo surface.
  //
  // v0.5.2 classifies GeoGebra's real masks explicitly:
  //   RED              = left-eye filter
  //   BLUE / GREEN+BLUE= right-eye filter
  //   NONE             = hidden-surface pass (preserve it unchanged)
  //   ALL              = end of stereo frame
  //
  // Only the two actual eye filters are bypassed to ALL. NONE remains NONE, so
  // GeoGebra's depth/occlusion algorithm is left untouched.

  const EYE_WIDTH = 640;
  const EYE_HEIGHT = 480;
  const FRAME_INTERVAL_MS = 125; // proof-of-concept: at most 8 stereo frames/s
  const JPEG_QUALITY = 0.74;
  const SWAP_EYES = false;

  let stereoActive = false;
  let last3DCanvas = null;
  let lastPortalRect = '';
  let rectTimer = null;
  let hookTimer = null;
  let apiWrapTimer = null;
  let lastFrameSentAt = 0;
  let sbsCanvas = null;
  let sbsContext = null;
  let sbsImageData = null;
  const hookedContexts = new WeakSet();

  function log() {
    try {
      const args = Array.prototype.slice.call(arguments);
      args.unshift('[GGQ StereoCapture]');
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
    if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= innerWidth || rect.top >= innerHeight) {
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

  function clearPortalTransparency() {
    document.querySelectorAll('.ggq-stereo-canvas').forEach(function (node) {
      node.classList.remove('ggq-stereo-canvas');
    });
    document.querySelectorAll('.ggq-stereo-transparent').forEach(function (node) {
      node.classList.remove('ggq-stereo-transparent');
    });
  }

  function applyPortalTransparency(canvas) {
    clearPortalTransparency();
    if (!canvas) return;

    canvas.classList.add('ggq-stereo-canvas');
    const canvasRect = canvas.getBoundingClientRect();
    let parent = canvas.parentElement;

    for (let i = 0; parent && i < 10; i += 1, parent = parent.parentElement) {
      if (parent === document.body || parent.id === 'ggb-element') break;
      const rect = parent.getBoundingClientRect();
      const closeToCanvas =
        rect.width <= canvasRect.width + 140 &&
        rect.height <= canvasRect.height + 140 &&
        rect.width >= canvasRect.width - 30 &&
        rect.height >= canvasRect.height - 30;
      if (!closeToCanvas) break;
      parent.classList.add('ggq-stereo-transparent');
    }
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
    if (!target) {
      log('Projection target not ready:', index);
      return false;
    }

    const changed = [];
    let node = target;
    for (let i = 0; node && i < 4; i += 1, node = node.parentElement) {
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
    } catch (error) {
      console.error('[GGQ StereoCapture projection click]', error);
      return false;
    } finally {
      changed.forEach(function (element) {
        element.dataset.ggqStereoTarget = '1';
      });
    }
    return true;
  }

  function ensureSbsCanvas() {
    if (sbsCanvas) return;
    sbsCanvas = document.createElement('canvas');
    sbsCanvas.width = EYE_WIDTH * 2;
    sbsCanvas.height = EYE_HEIGHT;
    sbsCanvas.style.display = 'none';
    sbsCanvas.setAttribute('aria-hidden', 'true');
    document.documentElement.appendChild(sbsCanvas);
    sbsContext = sbsCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
    sbsImageData = sbsContext.createImageData(EYE_WIDTH * 2, EYE_HEIGHT);
  }

  function readFramebuffer(gl) {
    const width = gl.drawingBufferWidth | 0;
    const height = gl.drawingBufferHeight | 0;
    if (width <= 0 || height <= 0) return null;
    if (width * height > 12000000) return null;

    const pixels = new Uint8Array(width * height * 4);
    try {
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    } catch (error) {
      console.warn('[GGQ StereoCapture] readPixels failed', error);
      return null;
    }
    return { pixels: pixels, width: width, height: height };
  }

  function copyEyeNearest(source, destination, eyeOffsetX) {
    const src = source.pixels;
    const srcW = source.width;
    const srcH = source.height;
    const out = destination.data;
    const fullOutW = EYE_WIDTH * 2;

    for (let y = 0; y < EYE_HEIGHT; y += 1) {
      const sy = srcH - 1 - Math.min(srcH - 1, Math.floor(y * srcH / EYE_HEIGHT));
      for (let x = 0; x < EYE_WIDTH; x += 1) {
        const sx = Math.min(srcW - 1, Math.floor(x * srcW / EYE_WIDTH));
        const srcIndex = (sy * srcW + sx) * 4;
        const dstIndex = (y * fullOutW + eyeOffsetX + x) * 4;
        out[dstIndex] = src[srcIndex];
        out[dstIndex + 1] = src[srcIndex + 1];
        out[dstIndex + 2] = src[srcIndex + 2];
        out[dstIndex + 3] = 255;
      }
    }
  }

  function emitStereoFrame(left, right) {
    if (!stereoActive || !left || !right) return;
    ensureSbsCanvas();

    const leftSource = SWAP_EYES ? right : left;
    const rightSource = SWAP_EYES ? left : right;
    copyEyeNearest(leftSource, sbsImageData, 0);
    copyEyeNearest(rightSource, sbsImageData, EYE_WIDTH);
    sbsContext.putImageData(sbsImageData, 0, 0);

    let dataUrl = '';
    try {
      dataUrl = sbsCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
    } catch (error) {
      console.warn('[GGQ StereoCapture] JPEG encode failed', error);
      return;
    }

    if (dataUrl && dataUrl.length > 64) {
      bridgeCall('submitStereoFrame', dataUrl, EYE_WIDTH, EYE_HEIGHT);
      lastFrameSentAt = performance.now();
    }
  }

  function classifyMask(red, green, blue, alpha) {
    const r = !!red;
    const g = !!green;
    const b = !!blue;
    const a = !!alpha;

    if (r && g && b && a) return 'all';
    if (!r && !g && !b && !a) return 'none';
    if (r && !g && !b && a) return 'left';
    if (!r && !g && b && a) return 'right';
    if (!r && g && b && a) return 'right';
    if (!r && !g && !b && a) return 'alpha';
    return 'other';
  }

  function hookContext(gl) {
    if (!gl || hookedContexts.has(gl)) return;
    hookedContexts.add(gl);

    const originalColorMask = gl.colorMask.bind(gl);
    const originalClear = gl.clear.bind(gl);
    const state = {
      phase: 'idle',
      captureThisFrame: false,
      left: null,
      needsRightColorClear: false
    };

    function resetFrameState() {
      state.phase = 'idle';
      state.captureThisFrame = false;
      state.left = null;
      state.needsRightColorClear = false;
    }

    gl.colorMask = function (red, green, blue, alpha) {
      if (!stereoActive) {
        resetFrameState();
        return originalColorMask(red, green, blue, alpha);
      }

      const kind = classifyMask(red, green, blue, alpha);
      const now = performance.now();

      if (kind === 'none' || kind === 'alpha' || kind === 'other') {
        // Crucial v0.5.2 fix: NONE is used inside both eye renders to draw
        // occlusion/hiding depth. It is NOT an eye switch and must stay NONE.
        return originalColorMask(red, green, blue, alpha);
      }

      if (kind === 'left') {
        if (state.phase !== 'left') {
          state.phase = 'left';
          state.captureThisFrame = now - lastFrameSentAt >= FRAME_INTERVAL_MS;
          state.left = null;
          state.needsRightColorClear = false;
        }

        // Bypass only GeoGebra's red eye filter; keep its left-eye camera.
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

        if (state.phase === 'right') {
          // Bypass only the cyan/blue eye filter; keep its right-eye camera.
          return originalColorMask(true, true, true, true);
        }

        // A right mask without a preceding left mask is not a complete stereo
        // frame; do not invent one. Preserve GeoGebra's request for safety.
        return originalColorMask(red, green, blue, alpha);
      }

      if (kind === 'all') {
        if (state.phase === 'right') {
          if (state.captureThisFrame && state.left) {
            const right = readFramebuffer(gl);
            emitStereoFrame(state.left, right);
          }
          resetFrameState();
        }
        return originalColorMask(red, green, blue, alpha);
      }

      return originalColorMask(red, green, blue, alpha);
    };

    gl.clear = function (mask) {
      if (
        stereoActive &&
        state.phase === 'right' &&
        state.needsRightColorClear &&
        (mask & gl.DEPTH_BUFFER_BIT) !== 0
      ) {
        state.needsRightColorClear = false;
        // Stock anaglyph keeps left-eye color and clears only depth before the
        // right eye. For independent eye images, clear color exactly once here.
        return originalClear(mask | gl.COLOR_BUFFER_BIT);
      }
      return originalClear(mask);
    };

    log('Hooked GeoGebra WebGL context', gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  function hookCurrent3DContext() {
    const canvas = find3DCanvas();
    if (!canvas) return;
    const gl = contextOf(canvas);
    if (gl) hookContext(gl);
    if (stereoActive) {
      applyPortalTransparency(canvas);
      sendPortalRect();
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
      // v0.5.2 does NOT synthesize a second Glasses click here. The projection
      // patch arms this capture hook at window-capture time and then lets the
      // user's original click reach GeoGebra. That original event is the sole
      // source of the PROJECTION_GLASSES transition.
      hookCurrent3DContext();
      applyPortalTransparency(find3DCanvas());
      sendPortalRect();
      if (!rectTimer) {
        rectTimer = setInterval(function () {
          if (!stereoActive) return;
          applyPortalTransparency(find3DCanvas());
          sendPortalRect();
        }, 200);
      }
    } else {
      clearPortalTransparency();
      lastFrameSentAt = 0;
      if (!preserve) {
        setTimeout(function () { dispatchProjection(1); }, 0);
      }
    }

    bridgeCall('setStereoEnabled', next);
    log('Stereo transport', next ? 'ON' : 'OFF');
  }

  function wrapGeoGebraApi() {
    const api = window.GeoGebraForQuest;
    if (!api || typeof api.setStereoEnabled !== 'function') return false;
    if (api.setStereoEnabled.__ggqStereoCaptureWrapped) return true;

    const replacement = function (enabled, preserveProjection) {
      setStereoEnabled(enabled, preserveProjection);
    };
    replacement.__ggqStereoCaptureWrapped = true;
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

  hookTimer = setInterval(hookCurrent3DContext, 500);
  window.addEventListener('resize', function () {
    if (stereoActive) sendPortalRect();
  });

  window.GeoGebraQuestStereoCapture = {
    enable: function () {
      // Programmatic enable only arms capture. Normal user activation is driven
      // by the headset click so GeoGebra itself chooses PROJECTION_GLASSES.
      setStereoEnabled(true, false);
    },
    disable: function () { setStereoEnabled(false, false); },
    isEnabled: function () { return stereoActive; },
    hookNow: hookCurrent3DContext,
    setSwapEyes: function () { return SWAP_EYES; }
  };
})();