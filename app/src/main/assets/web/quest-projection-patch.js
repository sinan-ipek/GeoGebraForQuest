(function () {
  'use strict';

  if (window.__ggqAuto3DV076) return;
  window.__ggqAuto3DV076 = true;

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  const CONSTRUCTION_QUIET_MS = 1200;
  const CANVAS_STABLE_TICKS = 5;
  const PRESENT_GATE = 2;

  let activeCanvas = null;
  let projectionArmed = false;
  let projectionPopupRequested = false;
  let stereoRequested = false;
  let portalSuppressed = false;
  let cachedProjection = null;
  let projectionRetryAt = 0;
  let stableTicks = 0;
  let lastCanvasSignature = '';
  let presentedBaseline = 0;
  let armStartedAt = 0;
  let rendererKickCount = 0;
  let resetGeneration = 0;
  let lastResetReason = 'startup';
  let lastLog = '';

  function log(message) {
    if (message === lastLog) return;
    lastLog = message;
    console.log('[GGQ Auto3D v0.7.6] ' + message);
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
        rect.width > 2 && rect.height > 2 && rect.bottom > 0 && rect.right > 0 &&
        rect.left < innerWidth && rect.top < innerHeight;
    } catch (_) { return false; }
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
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
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
      return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height),
        gl ? gl.drawingBufferWidth : 0, gl ? gl.drawingBufferHeight : 0].join(':');
    } catch (_) { return ''; }
  }

  function updateStability(canvas) {
    const sig = canvasSignature(canvas);
    if (sig && sig === lastCanvasSignature) stableTicks += 1;
    else {
      lastCanvasSignature = sig;
      stableTicks = 1;
    }
  }

  function constructionQuiet() {
    try {
      const helper = window.GeoGebraQuestStartupReset;
      if (helper && typeof helper.isQuiet === 'function') {
        return !!helper.isQuiet(CONSTRUCTION_QUIET_MS);
      }
    } catch (_) {}
    return true;
  }

  function projectionTableInfo() {
    if (cachedProjection && cachedProjection.table && cachedProjection.table.isConnected &&
        cachedProjection.glasses && cachedProjection.glasses.isConnected) return cachedProjection;
    cachedProjection = null;
    for (const table of Array.from(document.querySelectorAll('.SelectionTable'))) {
      const icons = Array.from(table.querySelectorAll('.stylebarButton'))
        .filter(function (element) { return !!cssBackground(element); });
      if (icons.length !== 4) continue;
      const kinds = icons.map(kindOf);
      if (kinds[0] === 'orthographic' && kinds[1] === 'perspective' &&
          kinds[2] === 'glasses' && kinds[3] === 'oblique') {
        cachedProjection = { table: table, glasses: icons[2], icons: icons };
        return cachedProjection;
      }
    }
    return null;
  }

  function projectionLauncher() {
    const tagged = document.querySelector('[data-ggq-projection-launcher="1"]');
    if (tagged && tagged.isConnected) return tagged;

    const candidates = Array.from(document.querySelectorAll(
      '.stylebarButton,button,[role="button"],[style*="background-image"]'
    ));
    for (const element of candidates) {
      if (element.closest && element.closest('.SelectionTable')) continue;
      if (!kindOf(element)) continue;
      if (!visible(element)) continue;
      element.setAttribute('data-ggq-projection-launcher', '1');
      return element;
    }
    return null;
  }

  function synthesizeActivation(target) {
    if (!target) return false;
    try {
      const mouse = function (type) {
        target.dispatchEvent(new MouseEvent(type, {
          bubbles: true, cancelable: true, view: window,
          button: 0, buttons: type === 'mousedown' ? 1 : 0
        }));
      };
      mouse('mousedown');
      mouse('mouseup');
      if (typeof target.click === 'function') target.click();
      else mouse('click');
      return true;
    } catch (_) { return false; }
  }

  function concealProjectionUi(info) {
    if (info && info.table) {
      info.table.style.setProperty('opacity', '0', 'important');
      info.table.style.setProperty('pointer-events', 'none', 'important');
      info.table.style.setProperty('visibility', 'hidden', 'important');
      info.table.setAttribute('aria-hidden', 'true');
    }

    // Important: do NOT display:none this launcher. v0.7.4 did that, so after
    // opening a new construction the same hidden DOM button could never be found
    // and Glasses could not be selected again until the whole app restarted.
    const launcher = projectionLauncher();
    if (launcher) {
      launcher.setAttribute('data-ggq-projection-launcher', '1');
      launcher.style.setProperty('opacity', '0', 'important');
      launcher.style.setProperty('pointer-events', 'none', 'important');
      launcher.setAttribute('aria-hidden', 'true');
    }
  }

  function captureEnabled() {
    try {
      return !!(window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled());
    } catch (_) { return false; }
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
      console.error('[GGQ Auto3D v0.7.6 stereo]', error);
    }
    return false;
  }

  function setPortalVisible(value) {
    try {
      if (window.QuestBridge && typeof window.QuestBridge.setPortalVisible === 'function') {
        window.QuestBridge.setPortalVisible(!!value);
      }
    } catch (_) {}
  }

  function nativeStatus() {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge.getStereoDebugStatus !== 'function') return null;
      const raw = window.QuestBridge.getStereoDebugStatus();
      return raw ? JSON.parse(String(raw)) : null;
    } catch (_) { return null; }
  }

  function presentedFrames() {
    const status = nativeStatus();
    const value = status && Number(status.framesPresented);
    return Number.isFinite(value) ? value : 0;
  }

  function refreshViewsBurst() {
    const api = window.ggbApplet;
    [0, 80, 180, 320, 520, 800].forEach(function (delay) {
      setTimeout(function () {
        try { if (api && typeof api.refreshViews === 'function') api.refreshViews(); } catch (_) {}
        try { window.dispatchEvent(new Event('resize')); } catch (_) {}
      }, delay);
    });
  }

  function ensureProjectionPopup() {
    const info = projectionTableInfo();
    if (info) return info;
    const now = performance.now();
    if (now < projectionRetryAt) return null;
    projectionRetryAt = now + 250;
    const launcher = projectionLauncher();
    if (launcher && synthesizeActivation(launcher)) {
      projectionPopupRequested = true;
      log('projection selector opened internally');
    }
    return null;
  }

  function forceGlassesProjection(info) {
    if (!info || !info.glasses) return false;
    setPortalVisible(false);

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

    if (!ok) return false;

    projectionArmed = true;
    projectionPopupRequested = false;
    presentedBaseline = presentedFrames();
    armStartedAt = performance.now();
    rendererKickCount = 0;
    concealProjectionUi(info);
    if (!captureEnabled()) setStereo(true);
    refreshViewsBurst();
    log('Glasses selected after construction became quiet -> stereo ON');
    return true;
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
    return (w * h) / Math.max(1, a.width * a.height);
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
          if (rectOverlapRatio(canvasRect, element.getBoundingClientRect()) > 0.02) return true;
        } catch (_) {}
      }
    }
    return false;
  }

  function resetForConstructionChange(reason) {
    resetGeneration += 1;
    lastResetReason = String(reason || 'construction-change');
    projectionArmed = false;
    projectionPopupRequested = false;
    portalSuppressed = false;
    cachedProjection = null;
    projectionRetryAt = 0;
    stableTicks = 0;
    lastCanvasSignature = '';
    presentedBaseline = presentedFrames();
    armStartedAt = 0;
    rendererKickCount = 0;
    setPortalVisible(false);
    if (captureEnabled() || stereoRequested) setStereo(false);
    log('stereo disarmed for new construction: ' + lastResetReason);
  }

  function kickRendererIfNeeded() {
    if (!projectionArmed || !armStartedAt) return;
    const delta = presentedFrames() - presentedBaseline;
    if (delta >= PRESENT_GATE) return;
    const elapsed = performance.now() - armStartedAt;

    if (elapsed > 1400 && rendererKickCount === 0) {
      rendererKickCount = 1;
      const info = projectionTableInfo() || ensureProjectionPopup();
      if (info && info.glasses) synthesizeActivation(info.glasses);
      refreshViewsBurst();
      log('no fresh stereo pair yet -> reselected Glasses once');
    } else if (elapsed > 2800 && rendererKickCount === 1) {
      rendererKickCount = 2;
      setStereo(false);
      setTimeout(function () {
        setStereo(true);
        const info = projectionTableInfo() || ensureProjectionPopup();
        if (info && info.glasses) synthesizeActivation(info.glasses);
        refreshViewsBurst();
      }, 120);
      log('stereo capture restarted once because presentation gate stayed at zero');
    }
  }

  function scan() {
    const canvas = visibleWebGlCanvas();
    if (!canvas) {
      setPortalVisible(false);
      return;
    }

    if (activeCanvas !== canvas) {
      markStereoCanvas(canvas);
      activeCanvas = canvas;
      cachedProjection = null;
      projectionRetryAt = 0;
      stableTicks = 0;
      lastCanvasSignature = '';
      if (projectionArmed) resetForConstructionChange('3D-canvas-replaced');
    }

    updateStability(canvas);
    markStereoCanvas(canvas);

    if (!projectionArmed) {
      setPortalVisible(false);
      if (!constructionQuiet()) return;
      if (stableTicks < CANVAS_STABLE_TICKS) return;
      const info = projectionTableInfo() || ensureProjectionPopup();
      if (info) forceGlassesProjection(info);
      return;
    }

    const info = projectionTableInfo();
    if (info) concealProjectionUi(info);
    if (!captureEnabled()) setStereo(true);

    kickRendererIfNeeded();

    const blocked = blockingLayerOverlapsCanvas(canvas);
    if (blocked) {
      portalSuppressed = true;
      setPortalVisible(false);
      return;
    }
    portalSuppressed = false;

    const freshPresented = presentedFrames() - presentedBaseline;
    setPortalVisible(freshPresented >= PRESENT_GATE);
  }

  window.GeoGebraQuestAuto3D = {
    isInstalled: function () { return true; },
    is3DVisible: function () { return !!visibleWebGlCanvas(); },
    is3DExposed: function () { return !!(activeCanvas && !blockingLayerOverlapsCanvas(activeCanvas)); },
    isProjectionArmed: function () { return projectionArmed; },
    isProjectionPopupRequested: function () { return projectionPopupRequested; },
    isStereoRequested: function () { return stereoRequested; },
    isPortalSuppressed: function () { return portalSuppressed; },
    isOverlayActive: function () { return !!(activeCanvas && activeCanvas.classList.contains('ggq-stereo-canvas')); },
    resetForConstructionChange: resetForConstructionChange,
    getStableTicks: function () { return stableTicks; },
    getPresentedDelta: function () { return Math.max(0, presentedFrames() - presentedBaseline); },
    getResetGeneration: function () { return resetGeneration; },
    getLastResetReason: function () { return lastResetReason; },
    scanNow: scan
  };

  const observer = new MutationObserver(function () { setTimeout(scan, 0); });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'aria-hidden', 'aria-expanded']
  });

  scan();
  setInterval(scan, 100);
})();
