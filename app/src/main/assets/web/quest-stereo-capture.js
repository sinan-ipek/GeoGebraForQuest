(function () {
  'use strict';

  if (window.__ggqStereoCaptureV3) return;
  window.__ggqStereoCaptureV3 = true;

  // GeoGebraForQuest v0.6.0
  //
  // New strategy: do NOT try to intercept and separately capture the two
  // intermediate eye passes. GeoGebra already renders a complete anaglyph frame
  // from those passes. Its default glasses mode is grayscale, so the final
  // framebuffer contains the complete left eye in the RED channel and the
  // complete right eye in the GREEN/BLUE channels.
  //
  // We therefore let GeoGebra render its stock anaglyph completely unchanged,
  // capture that finished framebuffer once, decode the two channel groups back
  // into two grayscale eye images, pack them side-by-side, and send that small
  // 3D-only SBS image to Android. Android then composites each eye image into a
  // snapshot of the WHOLE GeoGebra panel. The Quest ultimately receives two
  // complete interface images; only the 3D viewport differs between them.

  const MAX_EYE_WIDTH = 720;
  const MAX_EYE_HEIGHT = 720;
  const FRAME_INTERVAL_MS = 100;
  const JPEG_QUALITY = 0.82;
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
  let sbsEyeWidth = 0;
  let sbsEyeHeight = 0;
  const hookedContexts = new WeakSet();

  function log() {
    try {
      const args = Array.prototype.slice.call(arguments);
      args.unshift('[GGQ FullPanelStereo]');
      console.log.apply(console, args);
    } catch (_) {}
  }

  function bridgeCall(name) {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge[name] !== 'function') return;
      const args = Array.prototype.slice.call(arguments, 1);
      window.QuestBridge[name].apply(window.QuestBridge, args);
    } catch (error) {
      console.error('[GGQ FullPanelStereo bridge]', name, error);
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
      console.error('[GGQ FullPanelStereo projection click]', error);
      return false;
    } finally {
      changed.forEach(function (element) {
        element.dataset.ggqStereoTarget = '1';
      });
    }
    return true;
  }

  function readFramebuffer(gl) {
    const width = gl.drawingBufferWidth | 0;
    const height = gl.drawingBufferHeight | 0;
    if (width <= 0 || height <= 0) return null;
    if (width * height > 16000000) return null;

    const pixels = new Uint8Array(width * height * 4);
    try {
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    } catch (error) {
      console.warn('[GGQ FullPanelStereo] readPixels failed', error);
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
    if (sbsCanvas && sbsEyeWidth === eyeWidth && sbsEyeHeight === eyeHeight) {
      return;
    }

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

    let dataUrl = '';
    try {
      dataUrl = sbsCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
    } catch (error) {
      console.warn('[GGQ FullPanelStereo] JPEG encode failed', error);
      return null;
    }

    if (!dataUrl || dataUrl.length <= 64) return null;
    return { dataUrl: dataUrl, eyeWidth: eyeWidth, eyeHeight: eyeHeight };
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
    const state = {
      sawLeft: false,
      sawRight: false
    };

    function resetFrameState() {
      state.sawLeft = false;
      state.sawRight = false;
    }

    gl.colorMask = function (red, green, blue, alpha) {
      const kind = classifyMask(red, green, blue, alpha);
      const result = originalColorMask(red, green, blue, alpha);

      if (!stereoActive) {
        resetFrameState();
        return result;
      }

      if (kind === 'left') {
        state.sawLeft = true;
        return result;
      }

      if (kind === 'right') {
        if (state.sawLeft) state.sawRight = true;
        return result;
      }

      if (kind === 'none' || kind === 'alpha' || kind === 'other') {
        return result;
      }

      if (kind === 'all' && state.sawLeft && state.sawRight) {
        const now = performance.now();
        if (now - lastFrameSentAt >= FRAME_INTERVAL_MS) {
          const finishedAnaglyph = readFramebuffer(gl);
          const sbs = decodeAnaglyphToSbs(finishedAnaglyph);
          if (sbs) {
            sendPortalRect();
            bridgeCall('submitStereoFrame', sbs.dataUrl, sbs.eyeWidth, sbs.eyeHeight);
            lastFrameSentAt = now;
          }
        }
        resetFrameState();
      }

      return result;
    };

    log('Hooked GeoGebra WebGL context', gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  function hookCurrent3DContext() {
    const canvas = find3DCanvas();
    if (!canvas) return;
    const gl = contextOf(canvas);
    if (gl) hookContext(gl);
    if (stereoActive) sendPortalRect();
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
      sendPortalRect();
      if (!rectTimer) {
        rectTimer = setInterval(function () {
          if (!stereoActive) return;
          hookCurrent3DContext();
          sendPortalRect();
        }, 250);
      }
    } else {
      lastFrameSentAt = 0;
      if (!preserve) {
        setTimeout(function () { dispatchProjection(1); }, 0);
      }
    }

    bridgeCall('setStereoEnabled', next);
    log('Full-panel stereo transport', next ? 'ON' : 'OFF');
  }

  function wrapGeoGebraApi() {
    const api = window.GeoGebraForQuest;
    if (!api || typeof api.setStereoEnabled !== 'function') return false;
    if (api.setStereoEnabled.__ggqFullPanelStereoWrapped) return true;

    const replacement = function (enabled, preserveProjection) {
      setStereoEnabled(enabled, preserveProjection);
    };
    replacement.__ggqFullPanelStereoWrapped = true;
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
    enable: function () { setStereoEnabled(true, false); },
    disable: function () { setStereoEnabled(false, false); },
    isEnabled: function () { return stereoActive; },
    hookNow: hookCurrent3DContext,
    setSwapEyes: function () { return SWAP_EYES; }
  };
})();
