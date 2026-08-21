(function () {
  'use strict';

  if (window.__ggqAuto3DV074) return;
  window.__ggqAuto3DV074 = true;

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  let activeCanvas = null;
  let projectionArmed = false;
  let projectionPopupRequested = false;
  let stereoRequested = false;
  let portalSuppressed = false;
  let missingTicks = 0;
  let lastLog = '';
  let cachedProjection = null;
  let projectionRetryAt = 0;

  function log(message) {
    if (message === lastLog) return;
    lastLog = message;
    console.log('[GGQ Auto3D v0.7.4] ' + message);
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
      console.error('[GGQ Auto3D v0.7.4 stereo]', error);
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

  function ensureProjectionPopup() {
    const info = projectionTableInfo();
    if (info) return info;

    const now = performance.now();
    if (now < projectionRetryAt) return null;
    projectionRetryAt = now + 220;

    const launcher = projectionLauncher();
    if (launcher && synthesizeActivation(launcher)) {
      projectionPopupRequested = true;
      log('3D detected -> opening projection selector internally');
    }

    return null;
  }

  function forceGlassesProjection(info) {
    if (!info || !info.glasses) return false;

    if (!captureEnabled()) setStereo(true);

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
      projectionArmed = true;
      projectionPopupRequested = false;
      concealProjectionUi(info);
      log('Glasses projection selected automatically');
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

  function scan() {
    const canvas = visibleWebGlCanvas();

    if (!canvas) {
      missingTicks += 1;
      if (missingTicks >= 3) {
        if (activeCanvas) {
          try { activeCanvas.classList.remove('ggq-stereo-canvas'); } catch (_) {}
        }
        activeCanvas = null;
        projectionArmed = false;
        projectionPopupRequested = false;
        portalSuppressed = false;
        setPortalVisible(false);
        if (stereoRequested || captureEnabled()) setStereo(false);
      }
      return;
    }

    missingTicks = 0;

    if (activeCanvas !== canvas) {
      markStereoCanvas(canvas);
      activeCanvas = canvas;
      projectionArmed = false;
      projectionPopupRequested = false;
      portalSuppressed = false;
      cachedProjection = null;
      projectionRetryAt = 0;
    }

    if (!projectionArmed) {
      setPortalVisible(false);
      const info = projectionTableInfo() || ensureProjectionPopup();
      if (info) forceGlassesProjection(info);
      return;
    }

    const info = projectionTableInfo();
    if (info) concealProjectionUi(info);

    markStereoCanvas(canvas);
    if (!captureEnabled()) setStereo(true);

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
