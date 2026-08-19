(function () {
  'use strict';

  if (window.__ggqProjectionPatchV2) return;
  window.__ggqProjectionPatchV2 = true;

  // GeoGebra renders its projection icons as CSS background-image values on
  // Label elements (ImageOrText.applyToLabel), not as inline <svg> nodes.
  // This patch identifies the real four-item projection table and replaces
  // only the third item (Glasses/Anaglyph) with the Quest headset control.

  const HEADSET_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><path d="M4.2 7.5h15.6c1.2 0 2.2 1 2.2 2.2v6.1c0 1.2-1 2.2-2.2 2.2h-4.3l-2.1-2.6h-2.8L8.5 18H4.2C3 18 2 17 2 15.8V9.7c0-1.2 1-2.2 2.2-2.2zm.3 2v6.5h3.1l2.1-2.6h4.6l2.1 2.6h3.1V9.5H4.5z"/><path d="M7 11.2h3v2H7zm7 0h3v2h-3z"/></svg>';
  const HEADSET_BG = 'url("data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(HEADSET_SVG) + '")';

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  let patchQueued = false;

  function cssBackground(element) {
    if (!element || element.nodeType !== 1) return '';
    try {
      return element.style.backgroundImage || getComputedStyle(element).backgroundImage || '';
    } catch (_) {
      return element.style ? element.style.backgroundImage || '' : '';
    }
  }

  function extractUrl(background) {
    const text = String(background || '').trim();
    const match = text.match(/^url\((.*)\)$/i);
    if (!match) return text;
    let value = match[1].trim();
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    return value;
  }

  function decodeBackground(background) {
    const url = extractUrl(background);
    if (!url) return '';

    if (/projection_(orthographic|perspective|glasses|oblique)/i.test(url)) {
      return url;
    }

    try {
      if (/^data:image\/svg\+xml;base64,/i.test(url)) {
        return atob(url.slice(url.indexOf(',') + 1));
      }
      if (/^data:image\/svg\+xml/i.test(url)) {
        return decodeURIComponent(url.slice(url.indexOf(',') + 1));
      }
    } catch (_) {
      // Fall through to the original CSS URL string.
    }

    return url;
  }

  function normalizedIconSource(element) {
    return decodeBackground(cssBackground(element))
      .replace(/\s+/g, '')
      .replace(/%20/gi, '')
      .toLowerCase();
  }

  function kindOf(element) {
    const source = normalizedIconSource(element);
    if (!source) return '';

    if (source.includes('projection_orthographic') || source.includes(SIG.orthographic.toLowerCase())) {
      return 'orthographic';
    }
    if (source.includes('projection_perspective') || source.includes(SIG.perspective.toLowerCase())) {
      return 'perspective';
    }
    if (source.includes('projection_glasses') || source.includes(SIG.glasses.toLowerCase())) {
      return 'glasses';
    }
    if (source.includes('projection_oblique') || source.includes(SIG.oblique.toLowerCase())) {
      return 'oblique';
    }
    return '';
  }

  function markProjectionContainer(element) {
    const table = element && element.closest ? element.closest('.SelectionTable') : null;
    if (table) table.dataset.ggqProjectionContainer = '1';
  }

  function replaceWithHeadset(element) {
    if (!element || element.dataset.ggqStereoTarget === '1') return;

    element.dataset.ggqStereoTarget = '1';
    element.dataset.ggqStereoIcon = '1';
    element.setAttribute('title', 'Stereo 3D (Quest)');
    element.setAttribute('aria-label', 'Stereo 3D (Quest)');
    element.style.backgroundImage = HEADSET_BG;
    element.style.backgroundSize = '24px 24px';
    element.style.backgroundRepeat = 'no-repeat';
    element.style.backgroundPosition = 'center';

    const cell = element.closest ? element.closest('td') : null;
    if (cell) {
      cell.dataset.ggqStereoTarget = '1';
      cell.setAttribute('title', 'Stereo 3D (Quest)');
      cell.setAttribute('aria-label', 'Stereo 3D (Quest)');
    }

    markProjectionContainer(element);
  }

  function patchDirectGlassesIcons() {
    const candidates = Array.from(document.querySelectorAll(
      '.stylebarButton, [style*="background-image"], [style*="backgroundImage"]'
    ));

    for (const element of candidates) {
      if (element.dataset.ggqStereoTarget === '1') continue;
      if (kindOf(element) === 'glasses') replaceWithHeadset(element);
    }
  }

  function patchProjectionTables() {
    const tables = Array.from(document.querySelectorAll('.SelectionTable'));

    for (const table of tables) {
      const icons = Array.from(table.querySelectorAll('.stylebarButton'))
        .filter(element => cssBackground(element));

      if (icons.length !== 4) continue;

      const kinds = icons.map(kindOf);
      const isProjectionTable =
        kinds[0] === 'orthographic' &&
        kinds[1] === 'perspective' &&
        (kinds[2] === 'glasses' || icons[2].dataset.ggqStereoTarget === '1') &&
        kinds[3] === 'oblique';

      if (!isProjectionTable) continue;

      table.dataset.ggqProjectionContainer = '1';
      replaceWithHeadset(icons[2]);
    }
  }

  function patchNow() {
    patchDirectGlassesIcons();
    patchProjectionTables();
  }

  function queuePatch() {
    if (patchQueued) return;
    patchQueued = true;
    requestAnimationFrame(function () {
      patchQueued = false;
      patchNow();
    });
  }

  // Capture events before GeoGebra's SelectionTable handler. This is a second
  // safety layer; the existing index.html interceptor recognizes the same data
  // attributes, but this makes the repair self-contained.
  function eventPath(event) {
    return typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
  }

  function isStereoEvent(event) {
    return eventPath(event).some(node =>
      node && node.nodeType === 1 && node.dataset && node.dataset.ggqStereoTarget === '1'
    );
  }

  let lastActivation = 0;
  function intercept(event) {
    if (!isStereoEvent(event)) return;

    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();

    const activate = event.type === 'pointerup' || event.type === 'mouseup' ||
      event.type === 'touchend' || event.type === 'click';
    if (!activate) return;

    const now = performance.now();
    if (now - lastActivation < 350) return;
    lastActivation = now;

    try {
      if (window.GeoGebraForQuest &&
          typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
        const currentlyOn = document.documentElement.dataset.ggqStereo === 'on';
        window.GeoGebraForQuest.setStereoEnabled(!currentlyOn);
      }
    } catch (error) {
      console.error('[GeoGebraForQuest projection patch]', error);
    }
  }

  ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'click']
    .forEach(type => document.addEventListener(type, intercept, true));

  const observer = new MutationObserver(queuePatch);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class', 'title', 'aria-label']
  });

  patchNow();
  setInterval(patchNow, 750);
})();
