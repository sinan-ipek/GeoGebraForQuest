(function () {
  'use strict';

  if (window.__ggqProjectionPatchV6) return;
  window.__ggqProjectionPatchV6 = true;

  const HEADSET_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><path d="M4.2 7.5h15.6c1.2 0 2.2 1 2.2 2.2v6.1c0 1.2-1 2.2-2.2 2.2h-4.3l-2.1-2.6h-2.8L8.5 18H4.2C3 18 2 17 2 15.8V9.7c0-1.2 1-2.2 2.2-2.2zm.3 2v6.5h3.1l2.1-2.6h4.6l2.1 2.6h3.1V9.5H4.5z"/><path d="M7 11.2h3v2H7zm7 0h3v2h-3z"/></svg>';
  const HEADSET_BG = 'url("data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(HEADSET_SVG) + '")';

  const SIG = {
    orthographic: 'M2117.4l-.86.6M3.6220.44L220M194.77l2.55',
    perspective: 'M9.312.77L24.79v12.36l13.154.08L2216.78V4',
    glasses: 'M1010h4v2h-4z',
    oblique: 'M72L27v15h15l5-5V2'
  };

  let patchQueued = false;
  let lastArmAt = 0;

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
    if (/projection_(orthographic|perspective|glasses|oblique)/i.test(url)) return url;
    try {
      if (/^data:image\/svg\+xml;base64,/i.test(url)) {
        return atob(url.slice(url.indexOf(',') + 1));
      }
      if (/^data:image\/svg\+xml/i.test(url)) {
        return decodeURIComponent(url.slice(url.indexOf(',') + 1));
      }
    } catch (_) {}
    return url;
  }

  function normalizedIconSource(element) {
    return decodeBackground(cssBackground(element))
      .replace(/\s+/g, '')
      .replace(/%20/gi, '')
      .toLowerCase();
  }

  function kindOf(element) {
    if (!element) return '';
    if (element.dataset && element.dataset.ggqStereoIcon === '1') return 'glasses';
    const source = normalizedIconSource(element);
    if (!source) return '';
    if (source.includes('projection_orthographic') || source.includes(SIG.orthographic.toLowerCase())) return 'orthographic';
    if (source.includes('projection_perspective') || source.includes(SIG.perspective.toLowerCase())) return 'perspective';
    if (source.includes('projection_glasses') || source.includes(SIG.glasses.toLowerCase())) return 'glasses';
    if (source.includes('projection_oblique') || source.includes(SIG.oblique.toLowerCase())) return 'oblique';
    return '';
  }

  function replaceWithHeadset(element) {
    if (!element) return;
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
  }

  function patchProjectionTables() {
    const tables = Array.from(document.querySelectorAll('.SelectionTable'));
    for (const table of tables) {
      const icons = Array.from(table.querySelectorAll('.stylebarButton'))
        .filter(function (element) { return !!cssBackground(element); });
      if (icons.length !== 4) continue;
      const kinds = icons.map(kindOf);
      if (kinds[0] !== 'orthographic' || kinds[1] !== 'perspective' ||
          kinds[2] !== 'glasses' || kinds[3] !== 'oblique') {
        continue;
      }
      table.dataset.ggqProjectionContainer = '1';
      replaceWithHeadset(icons[2]);
    }
  }

  function patchDirectGlassesIcons() {
    const candidates = Array.from(document.querySelectorAll(
      '.stylebarButton, [style*="background-image"], [style*="backgroundImage"]'
    ));
    for (const element of candidates) {
      if (kindOf(element) !== 'glasses') continue;
      replaceWithHeadset(element);
      const table = element.closest ? element.closest('.SelectionTable') : null;
      if (table) table.dataset.ggqProjectionContainer = '1';
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

  function eventPath(event) {
    return typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
  }

  function stereoTargetInEvent(event) {
    return eventPath(event).some(function (node) {
      return node && node.nodeType === 1 && node.dataset &&
        (node.dataset.ggqStereoTarget === '1' || node.dataset.ggqStereoIcon === '1');
    });
  }

  function projectionTableInEvent(event) {
    const path = eventPath(event);
    for (const node of path) {
      if (node && node.nodeType === 1 && node.dataset &&
          node.dataset.ggqProjectionContainer === '1') {
        return node;
      }
    }
    return null;
  }

  function armStereoCapture() {
    const now = performance.now();
    if (now - lastArmAt < 250) return;
    lastArmAt = now;
    try {
      if (window.GeoGebraForQuest &&
          typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
        window.GeoGebraForQuest.setStereoEnabled(true, false);
      }
    } catch (error) {
      console.error('[GeoGebraForQuest arm stereo]', error);
    }
  }

  /**
   * v0.6.6: let GeoGebra receive the REAL Glasses button gesture.
   *
   * There are two old marker checks in index.html:
   *   data-ggq-stereo-target
   *   data-ggq-stereo-icon
   *
   * Earlier versions temporarily removed only the first marker. The old
   * capture-phase handler could therefore still recognize the headset button
   * through data-ggq-stereo-icon and stop propagation before GeoGebra's own
   * SelectionTable received the click. That left GeoGebra in a normal flat
   * projection, so the RED/RIGHT Glasses eye passes never started.
   *
   * During each real headset input event we now temporarily remove BOTH markers
   * from every element in the event path. No default action or propagation is
   * cancelled. GeoGebra therefore receives the original user gesture and can
   * genuinely enter PROJECTION_GLASSES. Markers are restored immediately after
   * the event dispatch finishes.
   */
  function passHeadsetEventThrough(event) {
    if (!stereoTargetInEvent(event)) return;

    if (event.type === 'pointerup' || event.type === 'touchend' || event.type === 'click') {
      armStereoCapture();
    }

    const changed = [];
    for (const node of eventPath(event)) {
      if (!node || node.nodeType !== 1 || !node.dataset) continue;

      const hadTarget = node.dataset.ggqStereoTarget === '1';
      const hadIcon = node.dataset.ggqStereoIcon === '1';
      if (!hadTarget && !hadIcon) continue;

      changed.push({
        node: node,
        target: hadTarget,
        icon: hadIcon
      });

      if (hadTarget) delete node.dataset.ggqStereoTarget;
      if (hadIcon) delete node.dataset.ggqStereoIcon;
    }

    // Intentionally do NOT call preventDefault(), stopPropagation(), or
    // stopImmediatePropagation(). GeoGebra must receive this exact gesture.
    setTimeout(function () {
      for (const item of changed) {
        const node = item.node;
        if (!node || !node.dataset) continue;
        if (item.target) node.dataset.ggqStereoTarget = '1';
        if (item.icon) node.dataset.ggqStereoIcon = '1';
      }
      patchNow();
    }, 0);
  }

  ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'click']
    .forEach(function (type) {
      window.addEventListener(type, passHeadsetEventThrough, true);
    });

  // Let other projection buttons behave normally. After GeoGebra has processed
  // the user's choice, only hide Quest stereo output; preserve the newly chosen
  // GeoGebra projection.
  document.addEventListener('click', function (event) {
    const table = projectionTableInEvent(event);
    if (!table || stereoTargetInEvent(event)) return;
    if (document.documentElement.dataset.ggqStereo !== 'on') return;
    setTimeout(function () {
      try {
        if (window.GeoGebraForQuest &&
            typeof window.GeoGebraForQuest.setStereoEnabled === 'function') {
          window.GeoGebraForQuest.setStereoEnabled(false, true);
        }
      } catch (_) {}
    }, 0);
  }, false);

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
