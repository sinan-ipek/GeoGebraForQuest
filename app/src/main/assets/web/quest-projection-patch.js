(function () {
  'use strict';

  if (window.__ggqAuto3DV070) return;
  window.__ggqAuto3DV070 = true;

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  let activeCanvas = null;
  let projectionArmed = false;
  let stereoRequested = false;
  let missingTicks = 0;
  let lastLog = '';
  let cachedProjection = null;

  function log(message) {
    if (message === lastLog) return;
    lastLog = message;
    console.log('[GGQ Auto3D v0.7.0] ' + message);
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
    if (element.dataset && element.dataset.ggqStereoIcon === '1') return 'glasses';
    const source = decodeBackground(cssBackground(element))
      .replace(/\s+/g, '').replace(/%20/gi, '').toLowerCase();
    if (!source) return '';
    if (source.includes('projection_orthographic') || source.includes(SIG.orthographic.toLowerCase())) return 'orthographic';
    if (source.includes('projection_perspective') || source.includes(SIG.perspective.toLowerCase())) return 'perspective';
    if (source.includes('projection_glasses') || source.includes(SIG.glasses.toLowerCase())) return 'glasses';
    if (source.includes('projection_oblique') || source.includes(SIG.oblique.toLowerCase())) return 'oblique';
    return '';
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

    for (const table of Array.from(document.querySelectorAll('.SelectionTable'))) {
      const icons = Array.from(table.querySelectorAll('.stylebarButton'))
        .filter(function (element) { return !!cssBackground(element); });
      if (icons.length !== 4) continue;
      const kinds = icons.map(kindOf);
      if (kinds[0] === 'orthographic' && kinds[1] === 'perspective' &&
          kinds[2] === 'glasses' && kinds[3] === 'oblique') {
        cachedProjection = { table: table, glasses: icons[2] };
        return cachedProjection;
      }
    }
    return null;
  }

  function stripLegacyMarkers(root) {
    if (!root) return;
    const nodes = [root].concat(Array.from(root.querySelectorAll ? root.querySelectorAll('*') : []));
    for (const node of nodes) {
      if (!node || !node.dataset) continue;
      delete node.dataset.ggqStereoTarget;
      delete node.dataset.ggqStereoIcon;
      delete node.dataset.ggqProjectionContainer;
    }
    let parent = root.parentElement;
    for (let i = 0; parent && i < 4; i += 1, parent = parent.parentElement) {
      if (!parent.dataset) continue;
      delete parent.dataset.ggqStereoTarget;
      delete parent.dataset.ggqStereoIcon;
      delete parent.dataset.ggqProjectionContainer;
    }
  }

  function hideProjectionControls() {
    const info = projectionTableInfo();
    if (!info) return null;
    stripLegacyMarkers(info.table);
    info.table.style.setProperty('display', 'none', 'important');
    info.table.setAttribute('aria-hidden', 'true');
    return info;
  }

  function captureEnabled() {
    try {
      return !!(window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled());
    } catch (_) { return false; }
  }

  function requestStereoOn() {
    try {
      if (window.GeoGebraQuestStereoCapture && typeof window.GeoGebraQuestStereoCapture.enable === 'function') {
        window.GeoGebraQuestStereoCapture.enable();
        stereoRequested = true;
        log('3D visible -> stereo ON');
        return true;
      }
      if (window.GeoGebraForQuest && typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
        window.GeoGebraForQuest.setStereoEnabled(true, true);
        stereoRequested = true;
        log('3D visible -> stereo ON via API');
        return true;
      }
    } catch (error) {
      console.error('[GGQ Auto3D v0.7.0 enable]', error);
    }
    return false;
  }

  function requestStereoOff() {
    try {
      if (window.GeoGebraForQuest && typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
        window.GeoGebraForQuest.setStereoEnabled(false, true);
      }
    } catch (_) {}
    stereoRequested = false;
    log('3D not visible -> stereo OFF');
  }

  function forceGlassesProjection(info) {
    if (!info || !info.glasses) return false;
    stripLegacyMarkers(info.table);

    // Arm capture BEFORE the programmatic Glasses click so GeoGebra's very first
    // RED/RIGHT render pass is captured even if a static scene does not redraw later.
    if (!captureEnabled() && !requestStereoOn()) return false;

    try {
      info.glasses.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window
      }));
      projectionArmed = true;
      log('3D detected -> Glasses selected automatically; no user click');
      return true;
    } catch (error) {
      console.error('[GGQ Auto3D v0.7.0 projection]', error);
      return false;
    }
  }

  function scan() {
    const info = hideProjectionControls();
    const canvas = visibleWebGlCanvas();

    if (!canvas) {
      missingTicks += 1;
      if (missingTicks >= 4) {
        activeCanvas = null;
        projectionArmed = false;
        if (stereoRequested || captureEnabled()) requestStereoOff();
      }
      return;
    }

    missingTicks = 0;
    if (activeCanvas !== canvas) {
      activeCanvas = canvas;
      projectionArmed = false;
    }

    if (!projectionArmed) {
      if (info) forceGlassesProjection(info);
      return;
    }

    if (!captureEnabled()) requestStereoOn();
  }

  window.GeoGebraQuestAuto3D = {
    isInstalled: function () { return true; },
    is3DVisible: function () { return !!visibleWebGlCanvas(); },
    isProjectionArmed: function () { return projectionArmed; },
    isStereoRequested: function () { return stereoRequested; },
    scanNow: scan
  };

  const observer = new MutationObserver(function () { setTimeout(scan, 0); });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  scan();
  setInterval(scan, 250);
})();
