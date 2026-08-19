(function () {
  'use strict';

  if (window.__ggqStereoCaptureV1) return;
  window.__ggqStereoCaptureV1 = true;

  // GeoGebraForQuest v0.5.0 stereo transport.
  //
  // GeoGebra's PROJECTION_GLASSES path renders the 3D view twice. It first
  // selects the left-eye camera, draws, then selects the right-eye camera and
  // draws again. The stock renderer turns those two passes into an anaglyph by
  // changing WebGL colorMask().
  //
  // We hook that final WebGL stage only. While Quest stereo is enabled:
  //   1. GeoGebra still computes its own left/right eye cameras and geometry.
  //   2. We replace the red/cyan color masks with an all-channel mask, so each
  //      eye pass remains a normal full-color render (or GeoGebra's own
  //      grayscale render if that option is active in the current build).
  //   3. Just before the right-eye pass starts, readPixels() captures the
  //      completed left-eye framebuffer.
  //   4. The right-eye depth clear is upgraded to a color+depth clear so the
  //      second eye gets a clean framebuffer instead of an anaglyph blend.
  //   5. When GeoGebra restores colorMask(ALL) at the end of the frame, we
  //      capture the right eye, pack both views side-by-side, JPEG-compress the
  //      frame and hand it to Android.
  //
  // Android feeds that SBS frame to a Spatial SDK media panel configured with
  // StereoMode.LeftRight. The compositor then shows the left half only to the
  // left eye and the right half only to the right eye.

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

    // Make only the tight wrappers around GeoGebra's 3D canvas transparent.
    // Toolbars, Algebra view, menus and every other UI pixel stay untouched.
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

    // The existing Quest icon interception recognizes data-ggq-stereo-target.
    // Remove that marker only for this nested synthetic click so GeoGebra's own
    // SelectionTable handler receives the event and really enters Anaglyph.
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
      // WebGL readPixels is bottom-up; Canvas ImageData is top-down.
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

  function hookContext(gl) {
    if (!gl || hookedContexts.has(gl)) return;
    hookedContexts.add(gl);

    const originalColorMask = gl.colorMask.bind(gl);
    const originalClear = gl.clear.bind(gl);
    const state = {
      phase: 'idle',
      captureThisFrame: false,
      left: null,
      needsRightColorClear: false,
      lastMaskAt: 0
    };

    gl.colorMask = function (red, green, blue, alpha) {
      if (!stereoActive) {
        state.phase = 'idle';
        state.left = null;
        state.needsRightColorClear = false;
        return originalColorMask(red, green, blue, alpha);
      }

      const all = !!red && !!green && !!blue && !!alpha;
      const now = performance.now();

      if (!all) {
        if (state.phase === 'idle' || now - state.lastMaskAt > 100) {
          // First anaglyph color mask = beginning of GeoGebra's left-eye pass.
          state.phase = 'left';
          state.captureThisFrame = now - lastFrameSentAt >= FRAME_INTERVAL_MS;
          state.left = null;
          state.needsRightColorClear = false;
        } else if (state.phase === 'left') {
          // Second anaglyph mask arrives after the left-eye draw has completed.
          if (state.captureThisFrame) {
            state.left = readFramebuffer(gl);
          }
          state.phase = 'right';
          state.needsRightColorClear = true;
        }

        state.lastMaskAt = now;

        // Bypass GeoGebra's red/cyan filter. The eye camera is still GeoGebra's;
        // only the output-channel restriction is removed.
        return originalColorMask(true, true, true, true);
      }

      if (state.phase === 'right') {
        // GeoGebra restores ALL channels immediately after the right-eye draw.
        if (state.captureThisFrame && state.left) {
          const right = readFramebuffer(gl);
          emitStereoFrame(state.left, right);
        }
        state.phase = 'idle';
        state.left = null;
        state.needsRightColorClear = false;
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
        // Stock anaglyph keeps the left-eye color buffer and clears only depth.
        // For two independent eye images the right pass needs a clean color
        // buffer, so add COLOR_BUFFER_BIT exactly once before the right draw.
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
      hookCurrent3DContext();
      // Make GeoGebra itself select PROJECTION_GLASSES. Its renderer will now
      // generate the two eye camera passes we capture below.
      setTimeout(function () {
        dispatchProjection(2);
        hookCurrent3DContext();
      }, 0);

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
        // Toggling the headset off directly returns to Perspective. If the user
        // selected another projection themselves, the projection patch calls us
        // with preserveProjection=true so their choice is left untouched.
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

  // The object is created by index.html; page timing differs slightly between
  // the local bundle and CDN fallback, so keep retrying until it exists.
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
    enable: function () { setStereoEnabled(true, false); },
    disable: function () { setStereoEnabled(false, false); },
    isEnabled: function () { return stereoActive; },
    hookNow: hookCurrent3DContext,
    setSwapEyes: function () {
      // Kept as a compatibility placeholder for a future user-facing L/R swap.
      // SWAP_EYES is intentionally constant in v0.5.0 for predictable testing.
      return SWAP_EYES;
    }
  };
})();
