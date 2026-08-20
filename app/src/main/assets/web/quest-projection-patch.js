(function () {
  'use strict';

  if (window.__ggqAuto3DV071) return;
  window.__ggqAuto3DV071 = true;

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
    console.log('[GGQ Auto3D v0.7.1] ' + message);
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

  function elementIsVisible(element) {
    if (!element || !element.isConnected) return false;
    try {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        rect.width > 2 && rect.height > 2 && rect.bottom > 0 && rect.right > 0;
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
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) continue;
        const area = rect.width * rect.height;
        if (area > bestArea) { best = canvas; bestArea = area; }
      } catch (_) {}
    }
    return best;
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
    const candidates = Array.from(document.querySelectorAll(
      '.stylebarButton,button,[role="button"],[style*="background-image"]'
    ));
    for (const element of candidates) {
      if (element.closest && element.closest('.SelectionTable')) continue;
      const kind = kindOf(element);
      if (!kind) continue;
      if (!elementIsVisible(element)) continue;
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
    } catch (error) {
      console.warn('[GGQ Auto3D v0.7.1] synthetic activation failed', error);
      return false;
    }
  }

  function concealProjectionUi(info) {
    if (info && info.table) {
      // Keep the popup technically laid out so GeoGebra/GWT event handlers stay valid,
      // but make it completely invisible and non-interactive to the user.
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
      console.error('[GGQ Auto3D v0.7.1 stereo]', error);
    }
    return false;
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

    // Start capture before Glasses is selected so the very first left/right pass
    // is eligible for capture. Do not depend on a user gesture.
    if (!captureEnabled()) setStereo(true);

    // Temporarily keep the table visible to layout/event code while activating.
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

  function canvasHost(canvas) {
    if (!canvas) return null;
    let host = canvas;
    const r = canvas.getBoundingClientRect();
    let node = canvas.parentElement;
    for (let i = 0; node && i < 6; i += 1, node = node.parentElement) {
      try {
        const nr = node.getBoundingClientRect();
        if (nr.width <= r.width * 1.35 && nr.height <= r.height * 1.35) host = node;
        else break;
      } catch (_) { break; }
    }
    return host;
  }

  function canvasIsExposed(canvas) {
    if (!canvas || !elementIsVisible(canvas)) return false;
    const rect = canvas.getBoundingClientRect();
    const host = canvasHost(canvas) || canvas;
    const points = [
      [rect.left + rect.width * 0.50, rect.top + rect.height * 0.50],
      [rect.left + rect.width * 0.25, rect.top + rect.height * 0.25],
      [rect.left + rect.width * 0.75, rect.top + rect.height * 0.25],
      [rect.left + rect.width * 0.25, rect.top + rect.height * 0.75],
      [rect.left + rect.width * 0.75, rect.top + rect.height * 0.75]
    ];

    let exposed = 0;
    for (const pair of points) {
      const x = Math.max(0, Math.min(innerWidth - 1, pair[0]));
      const y = Math.max(0, Math.min(innerHeight - 1, pair[1]));
      let stack = [];
      try { stack = document.elementsFromPoint(x, y); } catch (_) {}
      let top = null;
      for (const element of stack) {
        if (!element || element.id === 'ggq-debug-overlay-v071') continue;
        if (element.closest && element.closest('#ggq-debug-overlay-v071')) continue;
        top = element;
        break;
      }
      if (!top) continue;
      if (top === canvas || host.contains(top) || top.contains(host)) exposed += 1;
    }
    return exposed >= 3;
  }

  function scan() {
    const canvas = visibleWebGlCanvas();

    if (!canvas) {
      missingTicks += 1;
      if (missingTicks >= 3) {
        activeCanvas = null;
        projectionArmed = false;
        projectionPopupRequested = false;
        portalSuppressed = false;
        if (stereoRequested || captureEnabled()) setStereo(false);
      }
      return;
    }

    missingTicks = 0;
    if (activeCanvas !== canvas) {
      activeCanvas = canvas;
      projectionArmed = false;
      projectionPopupRequested = false;
      portalSuppressed = false;
      cachedProjection = null;
      projectionRetryAt = 0;
    }

    if (!projectionArmed) {
      const info = projectionTableInfo() || ensureProjectionPopup();
      if (info) forceGlassesProjection(info);
      return;
    }

    const info = projectionTableInfo();
    if (info) concealProjectionUi(info);

    const exposed = canvasIsExposed(canvas);
    if (!exposed) {
      if (!portalSuppressed) {
        portalSuppressed = true;
        if (captureEnabled() || stereoRequested) setStereo(false);
        log('3D covered by another GeoGebra layer -> stereo portal hidden');
      }
      return;
    }

    if (portalSuppressed) {
      portalSuppressed = false;
      setStereo(true);
      log('3D visible again -> stereo portal restored');
      return;
    }

    if (!captureEnabled()) setStereo(true);
  }

  window.GeoGebraQuestAuto3D = {
    isInstalled: function () { return true; },
    is3DVisible: function () { return !!visibleWebGlCanvas(); },
    is3DExposed: function () { return !!(activeCanvas && canvasIsExposed(activeCanvas)); },
    isProjectionArmed: function () { return projectionArmed; },
    isProjectionPopupRequested: function () { return projectionPopupRequested; },
    isStereoRequested: function () { return stereoRequested; },
    isPortalSuppressed: function () { return portalSuppressed; },
    scanNow: scan
  };

  const observer = new MutationObserver(function () { setTimeout(scan, 0); });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'aria-hidden']
  });

  scan();
  setInterval(scan, 100);
})();
