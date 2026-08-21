(function () {
  'use strict';

  if (window.__ggqAuto3DV075) return;
  window.__ggqAuto3DV075 = true;

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  const MIN_INITIAL_STABLE_MS = 1500;
  const MIN_STABLE_TICKS = 6;
  const MIN_PRESENTED_FRAMES = 3;
  const REBUILD_TIMEOUT_MS = 3500;

  let activeCanvas = null;
  let glassesSelected = false;
  let projectionArmed = false;
  let projectionPopupRequested = false;
  let stereoRequested = false;
  let portalSuppressed = false;
  let missingTicks = 0;
  let lastLog = '';
  let cachedProjection = null;
  let projectionRetryAt = 0;

  let firstCanvasSeenAt = 0;
  let stableCanvasTicks = 0;
  let lastCanvasSignature = '';

  let warmRebuildState = 'idle';
  let warmRebuildStartedAt = 0;
  let warmRebuildTimeout = 0;
  let rendererKickStartedAt = 0;
  let rendererReselectDone = false;

  function log(message) {
    if (message === lastLog) return;
    lastLog = message;
    console.log('[GGQ Auto3D v0.7.5] ' + message);
  }

  function cssBackground(element) {
    if (!element || element.nodeType !== 1) return '';
    try {
      return element.style.backgroundImage || getComputedStyle(element).backgroundImage || '';
    } catch (_) {
      return element.style ? element.style.backgroundImage || '' : '';
    }
  }

  function decodeBackground(background) {
    let text = String(background || '').trim();
    const match = text.match(/^url\((.*)\)$/i);
    if (match) {
      text = match[1].trim();
      if ((text[0] === '"' && text[text.length - 1] === '"') ||
          (text[0] === "'" && text[text.length - 1] === "'")) {
        text = text.slice(1, -1);
      }
    }
    if (/projection_(orthographic|perspective|glasses|oblique)/i.test(text)) return text;
    try {
      if (/^data:image\/svg\+xml;base64,/i.test(text)) return atob(text.slice(text.indexOf(',') + 1));
      if (/^data:image\/svg\+xml/i.test(text)) return decodeURIComponent(text.slice(text.indexOf(',') + 1));
    } catch (_) {}
    return text;
  }

  function kindOf(element) {
    if (!element) return '';
    const source = decodeBackground(cssBackground(element))
      .replace(/\s+/g, '').replace(/%20/gi, '').toLowerCase();
    if (!source) return '';
    if (source.includes('projection_orthographic') || source.includes(SIG.orthographic.toLowerCase())) return 'orthographic';
    if (source.includes('projection_perspective') || source.includes(SIG.perspective.toLowerCase())) return 'perspective';
    if (source.includes('projection_glasses') || source.includes(SIG.glasses.toLowerCase())) return 'glasses';
    if (source.includes('projection_oblique') || source.includes(SIG.oblique.toLowerCase())) return 'oblique';
    return '';
  }

  function visible(element) {
    if (!element || !element.isConnected) return false;
    try {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        Number(style.opacity || 1) > 0 && rect.width > 2 && rect.height > 2 &&
        rect.bottom > 0 && rect.right > 0 && rect.left < innerWidth && rect.top < innerHeight;
    } catch (_) {
      return false;
    }
  }

  function visibleWebGlCanvas() {
    const root = document.getElementById('ggb-element') || document;
    let best = null;
    let bestArea = 0;

    for (const canvas of Array.from(root.querySelectorAll('canvas'))) {
      try {
        const rect = canvas.getBoundingClientRect();
        const style = getComputedStyle(canvas);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (rect.width < 160 || rect.height < 140) continue;
        if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= innerWidth || rect.top >= innerHeight) continue;

        const gl = canvas.getContext('webgl2') ||
          canvas.getContext('webgl') ||
          canvas.getContext('experimental-webgl');
        if (!gl) continue;

        const area = rect.width * rect.height;
        if (area > bestArea) {
          best = canvas;
          bestArea = area;
        }
      } catch (_) {}
    }

    return best;
  }

  function canvasSignature(canvas) {
    if (!canvas) return '';
    try {
      const r = canvas.getBoundingClientRect();
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      return [
        Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height),
        gl ? gl.drawingBufferWidth : 0, gl ? gl.drawingBufferHeight : 0
      ].join(':');
    } catch (_) {
      return '';
    }
  }

  function updateCanvasStability(canvas) {
    const signature = canvasSignature(canvas);
    if (!firstCanvasSeenAt) firstCanvasSeenAt = performance.now();
    if (signature && signature === lastCanvasSignature) stableCanvasTicks += 1;
    else {
      lastCanvasSignature = signature;
      stableCanvasTicks = 1;
    }
  }

  function initialCanvasStable() {
    return firstCanvasSeenAt > 0 &&
      performance.now() - firstCanvasSeenAt >= MIN_INITIAL_STABLE_MS &&
      stableCanvasTicks >= MIN_STABLE_TICKS;
  }

  function projectionTableInfo() {
    if (cachedProjection && cachedProjection.table && cachedProjection.table.isConnected &&
        cachedProjection.glasses && cachedProjection.glasses.isConnected) {
      return cachedProjection;
    }

    cachedProjection = null;

    for (const table of Array.from(document.querySelectorAll('.SelectionTable'))) {
      const icons = Array.from(table.querySelectorAll('.stylebarButton'))
        .filter(function (element) { return !!cssBackground(element); });
      if (icons.length !== 4) continue;

      const kinds = icons.map(kindOf);
      if (kinds[0] === 'orthographic' && kinds[1] === 'perspective' &&
          kinds[2] === 'glasses' && kinds[3] === 'oblique') {
        cachedProjection = {
          table: table,
          glasses: icons[2],
          icons: icons
        };
        return cachedProjection;
      }
    }

    return null;
  }

  function projectionLauncher() {
    const candidates = Array.from(document.querySelectorAll(
      '.stylebarButton,button,[role="button"],[style*="background-image"]'
    ));

    for (const element of candidates) {
      if (element.closest && element.closest('.SelectionTable')) continue;
      if (!kindOf(element) || !visible(element)) continue;
      return element;
    }

    return null;
  }

  function synthesizeActivation(target) {
    if (!target) return false;

    try {
      const mouse = function (type) {
        target.dispatchEvent(new MouseEvent(type, {
          bubbles: true,
          cancelable: true,
          view: window,
          button: 0,
          buttons: type === 'mousedown' ? 1 : 0
        }));
      };

      mouse('mousedown');
      mouse('mouseup');
      if (typeof target.click === 'function') target.click();
      else mouse('click');
      return true;
    } catch (_) {
      return false;
    }
  }

  function concealProjectionUi(info) {
    if (info && info.table) {
      info.table.style.setProperty('opacity', '0', 'important');
      info.table.style.setProperty('pointer-events', 'none', 'important');
      info.table.style.setProperty('visibility', 'hidden', 'important');
      info.table.setAttribute('aria-hidden', 'true');
    }

    const launcher = projectionLauncher();
    if (launcher) {
      launcher.style.setProperty('display', 'none', 'important');
      launcher.setAttribute('aria-hidden', 'true');
    }
  }

  function captureEnabled() {
    try {
      return !!(window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled());
    } catch (_) {
      return false;
    }
  }

  function setStereo(enabled) {
    try {
      if (window.GeoGebraForQuest && typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
        window.GeoGebraForQuest.setStereoEnabled(!!enabled, true);
        stereoRequested = !!enabled;
        return true;
      }

      if (window.GeoGebraQuestStereoCapture) {
        if (enabled && typeof window.GeoGebraQuestStereoCapture.enable === 'function') {
          window.GeoGebraQuestStereoCapture.enable();
          stereoRequested = true;
          return true;
        }

        if (!enabled && typeof window.GeoGebraQuestStereoCapture.disable === 'function') {
          window.GeoGebraQuestStereoCapture.disable(true);
          stereoRequested = false;
          return true;
        }
      }
    } catch (error) {
      console.error('[GGQ Auto3D v0.7.5 stereo]', error);
    }

    return false;
  }

  function setPortalVisible(visibleNow) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge.setPortalVisible === 'function') {
        window.QuestBridge.setPortalVisible(!!visibleNow);
      }
    } catch (_) {}
  }

  function nativeStatus() {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge.getStereoDebugStatus !== 'function') return null;
      const raw = window.QuestBridge.getStereoDebugStatus();
      return raw ? JSON.parse(String(raw)) : null;
    } catch (_) {
      return null;
    }
  }

  function nativePresentedFrames() {
    const status = nativeStatus();
    const value = status && Number(status.framesPresented);
    return Number.isFinite(value) ? value : 0;
  }

  function refreshViewsBurst() {
    const ggb = window.ggbApplet;
    if (!ggb || typeof ggb.refreshViews !== 'function') return;

    [0, 60, 120, 220, 350, 550, 800, 1150].forEach(function (delay) {
      setTimeout(function () {
        try { ggb.refreshViews(); } catch (_) {}
        try { window.dispatchEvent(new Event('resize')); } catch (_) {}
      }, delay);
    });
  }

  function ensureProjectionPopup() {
    const info = projectionTableInfo();
    if (info) return info;

    const now = performance.now();
    if (now < projectionRetryAt) return null;
    projectionRetryAt = now + 220;

    const launcher = projectionLauncher();
    if (launcher && synthesizeActivation(launcher)) {
      projectionPopupRequested = true;
      log('stable 3D detected -> opening projection selector internally');
    }

    return null;
  }

  function finishWarmRebuild(success) {
    if (warmRebuildTimeout) {
      clearTimeout(warmRebuildTimeout);
      warmRebuildTimeout = 0;
    }

    warmRebuildState = success ? 'settling' : 'fallback';
    cachedProjection = null;
    projectionRetryAt = 0;
    firstCanvasSeenAt = performance.now();
    stableCanvasTicks = 0;
    lastCanvasSignature = '';
    activeCanvas = null;
    setPortalVisible(false);

    if (success) log('Glasses state reloaded -> waiting for rebuilt 3D canvas');
    else log('warm rebuild unavailable -> continuing with live renderer');

    refreshViewsBurst();
  }

  function startWarmRebuild() {
    if (warmRebuildState !== 'idle') return;

    warmRebuildState = 'saving';
    warmRebuildStartedAt = performance.now();
    setPortalVisible(false);
    if (captureEnabled() || stereoRequested) setStereo(false);

    const ggb = window.ggbApplet;
    if (!ggb || typeof ggb.getBase64 !== 'function' || typeof ggb.setBase64 !== 'function') {
      finishWarmRebuild(false);
      return;
    }

    log('Glasses selected -> serializing once to remove cold-start race');

    warmRebuildTimeout = setTimeout(function () {
      if (warmRebuildState === 'saving' || warmRebuildState === 'reloading') {
        finishWarmRebuild(false);
      }
    }, REBUILD_TIMEOUT_MS);

    setTimeout(function () {
      try {
        if (typeof ggb.refreshViews === 'function') ggb.refreshViews();
        ggb.getBase64(function (base64) {
          if (!base64 || warmRebuildState !== 'saving') {
            finishWarmRebuild(false);
            return;
          }

          warmRebuildState = 'reloading';
          log('reloading same construction with Glasses already persisted');

          let callbackFired = false;
          const done = function () {
            if (callbackFired) return;
            callbackFired = true;
            finishWarmRebuild(true);
            setTimeout(scan, 0);
            setTimeout(scan, 120);
            setTimeout(scan, 300);
          };

          try {
            // GeoGebra Web API supports setBase64(base64, callback). This is the
            // same rebuild that happened naturally on the user's successful
            // second launch, but we perform it once inside the first launch.
            ggb.setBase64(base64, done);
          } catch (_) {
            try {
              ggb.setBase64(base64);
              setTimeout(done, 700);
            } catch (_) {
              finishWarmRebuild(false);
            }
          }
        });
      } catch (_) {
        finishWarmRebuild(false);
      }
    }, 180);
  }

  function forceGlassesProjection(info) {
    if (!info || !info.glasses) return false;

    // Do not start capture yet. The cold-start bug was caused by asking the
    // original renderer for stereo while the restored construction was still
    // replacing/rebuilding its WebGL view.
    setPortalVisible(false);
    if (captureEnabled() || stereoRequested) setStereo(false);

    const table = info.table;
    const oldVisibility = table.style.visibility;
    const oldOpacity = table.style.opacity;
    const oldPointerEvents = table.style.pointerEvents;

    table.style.visibility = 'visible';
    table.style.opacity = '0';
    table.style.pointerEvents = 'none';

    const ok = synthesizeActivation(info.glasses);

    table.style.visibility = oldVisibility;
    table.style.opacity = oldOpacity;
    table.style.pointerEvents = oldPointerEvents;

    if (ok) {
      glassesSelected = true;
      projectionPopupRequested = false;
      concealProjectionUi(info);
      log('Glasses projection selected automatically; capture held OFF');
      setTimeout(startWarmRebuild, 180);
      return true;
    }

    return false;
  }

  function markStereoCanvas(canvas) {
    if (activeCanvas && activeCanvas !== canvas) {
      try { activeCanvas.classList.remove('ggq-stereo-canvas'); } catch (_) {}
    }
    if (canvas) {
      try { canvas.classList.add('ggq-stereo-canvas'); } catch (_) {}
    }
  }

  function rectOverlapRatio(a, b) {
    const left = Math.max(a.left, b.left);
    const top = Math.max(a.top, b.top);
    const right = Math.min(a.right, b.right);
    const bottom = Math.min(a.bottom, b.bottom);
    const w = Math.max(0, right - left);
    const h = Math.max(0, bottom - top);
    const intersection = w * h;
    const area = Math.max(1, a.width * a.height);
    return intersection / area;
  }

  function blockingLayerOverlapsCanvas(canvas) {
    if (!canvas) return false;
    const canvasRect = canvas.getBoundingClientRect();
    const selectors = [
      '[role="dialog"]', '.Dialog', '.dialog', '.modalDialog', '.modal',
      '.PropertiesViewW', '.sideSheet', '.popupPanel', '.menuView', '.menuPanel',
      '.openFileView', '.fileView', '.loginDialog', '.signin', '.signIn',
      '.examDialog', '.shareDialog', '.saveDialog'
    ];

    for (const selector of selectors) {
      for (const element of Array.from(document.querySelectorAll(selector))) {
        if (!visible(element)) continue;
        if (element.id && element.id.indexOf('ggq-debug') >= 0) continue;
        if (element.closest && element.closest('.SelectionTable')) continue;

        try {
          const rect = element.getBoundingClientRect();
          if (rectOverlapRatio(canvasRect, rect) > 0.02) return true;
        } catch (_) {}
      }
    }

    return false;
  }

  function resetForNew3D() {
    if (activeCanvas) {
      try { activeCanvas.classList.remove('ggq-stereo-canvas'); } catch (_) {}
    }
    activeCanvas = null;
    glassesSelected = false;
    projectionArmed = false;
    projectionPopupRequested = false;
    stereoRequested = false;
    portalSuppressed = false;
    cachedProjection = null;
    projectionRetryAt = 0;
    firstCanvasSeenAt = 0;
    stableCanvasTicks = 0;
    lastCanvasSignature = '';
    warmRebuildState = 'idle';
    warmRebuildStartedAt = 0;
    rendererKickStartedAt = 0;
    rendererReselectDone = false;
    setPortalVisible(false);
    if (captureEnabled()) setStereo(false);
  }

  function settleWarmRebuild(canvas) {
    updateCanvasStability(canvas);
    if (stableCanvasTicks < MIN_STABLE_TICKS) return false;

    projectionArmed = true;
    warmRebuildState = 'done';
    rendererKickStartedAt = performance.now();
    rendererReselectDone = false;
    markStereoCanvas(canvas);
    setStereo(true);
    refreshViewsBurst();
    log('rebuilt 3D stable -> stereo capture ON; waiting for 3 presented frames');
    return true;
  }

  function kickRendererIfNeeded() {
    const presented = nativePresentedFrames();
    if (presented >= MIN_PRESENTED_FRAMES) return;

    const elapsed = rendererKickStartedAt ? performance.now() - rendererKickStartedAt : 0;
    if (elapsed > 250) {
      try {
        if (window.ggbApplet && typeof window.ggbApplet.refreshViews === 'function') {
          window.ggbApplet.refreshViews();
        }
      } catch (_) {}
    }

    if (elapsed > 1200 && presented === 0 && !rendererReselectDone) {
      const info = projectionTableInfo();
      if (info && info.glasses) {
        rendererReselectDone = true;
        synthesizeActivation(info.glasses);
        refreshViewsBurst();
        log('renderer kick -> reselected Glasses once because no stereo frame was presented');
      }
    }
  }

  function scan() {
    const canvas = visibleWebGlCanvas();

    if (!canvas) {
      // setBase64 temporarily destroys/recreates the 3D canvas. That is expected
      // during the warm rebuild and must not reset the startup state.
      if (warmRebuildState === 'saving' || warmRebuildState === 'reloading' ||
          warmRebuildState === 'settling') {
        setPortalVisible(false);
        return;
      }

      missingTicks += 1;
      if (missingTicks >= 3) resetForNew3D();
      return;
    }

    missingTicks = 0;
    updateCanvasStability(canvas);

    if (activeCanvas !== canvas) {
      markStereoCanvas(canvas);
      activeCanvas = canvas;
      cachedProjection = null;
      projectionRetryAt = 0;

      if (warmRebuildState !== 'settling' && warmRebuildState !== 'fallback' &&
          warmRebuildState !== 'done') {
        firstCanvasSeenAt = performance.now();
        stableCanvasTicks = 1;
        lastCanvasSignature = canvasSignature(canvas);
      }
    }

    if (!glassesSelected) {
      setPortalVisible(false);
      if (!initialCanvasStable()) {
        log('waiting for restored 3D canvas to become stable before Glasses');
        return;
      }

      const info = projectionTableInfo() || ensureProjectionPopup();
      if (info) forceGlassesProjection(info);
      return;
    }

    if (!projectionArmed) {
      setPortalVisible(false);
      if (warmRebuildState === 'settling' || warmRebuildState === 'fallback') {
        settleWarmRebuild(canvas);
      }
      return;
    }

    const info = projectionTableInfo();
    if (info) concealProjectionUi(info);

    markStereoCanvas(canvas);
    if (!captureEnabled()) {
      setStereo(true);
      rendererKickStartedAt = performance.now();
      refreshViewsBurst();
    }

    kickRendererIfNeeded();

    // Do not expose the front stereo portal until several distinct eye pairs
    // have made it all the way through EGL. This prevents the one-frame cold
    // start seen in v0.7.4 from covering the WebView with a stale/blank surface.
    if (nativePresentedFrames() < MIN_PRESENTED_FRAMES) {
      setPortalVisible(false);
      return;
    }

    const blocked = blockingLayerOverlapsCanvas(canvas);
    if (blocked) {
      if (!portalSuppressed) {
        portalSuppressed = true;
        setPortalVisible(false);
        log('GeoGebra UI overlaps 3D -> front stereo portal hidden, capture kept ON');
      }
      return;
    }

    if (portalSuppressed) {
      portalSuppressed = false;
      log('3D uncovered -> front stereo portal restored');
    }
    setPortalVisible(true);
  }

  window.GeoGebraQuestAuto3D = {
    isInstalled: function () { return true; },
    is3DVisible: function () { return !!visibleWebGlCanvas(); },
    is3DExposed: function () { return !!(activeCanvas && !blockingLayerOverlapsCanvas(activeCanvas)); },
    isProjectionArmed: function () { return projectionArmed; },
    isProjectionPopupRequested: function () { return projectionPopupRequested; },
    isStereoRequested: function () { return stereoRequested; },
    isPortalSuppressed: function () { return portalSuppressed; },
    isOverlayActive: function () {
      return !!(activeCanvas && activeCanvas.classList.contains('ggq-stereo-canvas'));
    },
    getStartupState: function () { return warmRebuildState; },
    getStableTicks: function () { return stableCanvasTicks; },
    getPresentedFrames: function () { return nativePresentedFrames(); },
    scanNow: scan
  };

  const observer = new MutationObserver(function () {
    setTimeout(scan, 0);
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'aria-hidden', 'aria-expanded']
  });

  scan();
  setInterval(scan, 100);
})();
