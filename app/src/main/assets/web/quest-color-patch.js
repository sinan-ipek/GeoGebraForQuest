(function () {
  'use strict';

  if (window.__ggqColorPatchV072) return;
  window.__ggqColorPatchV072 = true;

  const MAX_CONFIG_MS = 9000;
  const TICK_MS = 100;

  let state = 'waiting-3d';
  let startedAt = 0;
  let menuOpenedByUs = false;
  let settingsOpenedByUs = false;
  let projectionExpandedByUs = false;
  let completed = false;
  let failed = false;

  function log(message) {
    console.log('[GGQ Color v0.7.2] ' + message);
  }

  function normalize(value) {
    return String(value || '')
      .trim()
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[\s_\-–—]+/g, ' ');
  }

  function automationVisible(element) {
    if (!element || !element.isConnected) return false;
    try {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        rect.width > 2 && rect.height > 2 && rect.bottom > 0 && rect.right > 0 &&
        rect.left < innerWidth && rect.top < innerHeight;
    } catch (_) { return false; }
  }

  function stringsOf(element) {
    if (!element) return [];
    return [
      element.getAttribute && element.getAttribute('aria-label'),
      element.getAttribute && element.getAttribute('title'),
      element.getAttribute && element.getAttribute('data-title'),
      element.textContent
    ].map(normalize).filter(Boolean);
  }

  function hasAnyText(element, needles) {
    const values = stringsOf(element);
    return values.some(function (value) {
      return needles.some(function (needle) {
        return value === needle || value.indexOf(needle) >= 0;
      });
    });
  }

  function clickElement(element) {
    if (!element) return false;
    try {
      if (typeof element.click === 'function') {
        element.click();
        return true;
      }
      element.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window
      }));
      return true;
    } catch (_) { return false; }
  }

  function clickableCandidates(root) {
    return Array.from((root || document).querySelectorAll(
      'button,[role="button"],[role="menuitem"],.menuItem,.menuItemView,.settingsBtn,.headerButton,.standardButton,.header'
    )).filter(automationVisible);
  }

  function settingsPanel() {
    const panels = Array.from(document.querySelectorAll('.PropertiesViewW,.sideSheet'));
    for (const panel of panels) {
      if (automationVisible(panel) && !panel.closest('#ggq-debug-overlay-v072')) return panel;
    }
    return null;
  }

  function findMenuLauncher() {
    const needles = ['menu', 'menuyu ac', 'ana menu', 'main menu', 'open menu']
      .map(normalize);
    for (const element of clickableCandidates(document)) {
      if (element.closest && element.closest('.SelectionTable')) continue;
      if (hasAnyText(element, needles)) return element;
    }

    // GeoGebra hamburger buttons are not always labelled. Prefer compact header
    // buttons whose class name explicitly contains menu but not menu item.
    for (const element of clickableCandidates(document)) {
      const cls = normalize(element.className);
      if (cls.indexOf('menu') >= 0 && cls.indexOf('item') < 0) return element;
    }
    return null;
  }

  function findSettingsAction() {
    const needles = ['ayarlar', 'settings', 'einstellungen', 'parametres', 'ajustes', 'impostazioni']
      .map(normalize);
    for (const element of clickableCandidates(document)) {
      if (hasAnyText(element, needles)) return element;
    }
    return null;
  }

  function findProjectionSection(panel) {
    if (!panel) return null;
    const needles = ['izdusum', 'projection', 'projektion', 'proyeccion', 'proiezione']
      .map(normalize);

    // Current GeoGebra properties UI uses ComponentExpandableList.
    for (const list of Array.from(panel.querySelectorAll('.expandableList'))) {
      const title = list.querySelector('.title') || list;
      if (hasAnyText(title, needles)) return list;
    }

    // Fallback for a future UI where the projection collection is rendered by a
    // different wrapper: locate its title and climb to a reasonably small block.
    const candidates = Array.from(panel.querySelectorAll('.title,label,div,span'));
    for (const element of candidates) {
      if (!hasAnyText(element, needles)) continue;
      let node = element;
      for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {
        if (!node || node === panel) break;
        if (node.querySelector && node.querySelector('.checkboxPanel,[role="checkbox"]')) return node;
        if (node.classList && node.classList.contains('expandableList')) return node;
      }
    }
    return null;
  }

  function ensureProjectionExpanded(section) {
    if (!section) return false;
    if (section.getAttribute('aria-expanded') === 'true' || section.classList.contains('extended')) return true;
    const header = section.querySelector('.header') || section;
    if (clickElement(header)) {
      projectionExpandedByUs = true;
      state = 'expanding-projection';
      return false;
    }
    return false;
  }

  function checkboxChecked(checkbox) {
    const aria = String(checkbox.getAttribute('aria-checked') || '').toLowerCase();
    if (aria === 'true') return true;
    if (aria === 'false') return false;
    return !!checkbox.querySelector('.checkbox.selected');
  }

  function findGrayScaleCheckbox(section) {
    if (!section) return null;
    const boxes = Array.from(section.querySelectorAll('.checkboxPanel,[role="checkbox"]'))
      .filter(automationVisible);
    const grayWords = ['gray', 'grey', 'grayscale', 'gray scale', 'gri', 'grau', 'gris', 'grigio']
      .map(normalize);

    for (const box of boxes) {
      if (hasAnyText(box, grayWords)) return box;
    }

    // In ProjectionPropertyCollection the order is projection selector, eye
    // distances, GrayScale, OmitGreen. With Glasses active the default state is
    // GrayScale=true and OmitGreen=false, so the first checked checkbox inside
    // this section is a safe structural fallback independent of localization.
    for (const box of boxes) {
      if (checkboxChecked(box)) return box;
    }
    return null;
  }

  function closeSettings() {
    const panel = settingsPanel();
    if (!panel) return;
    try {
      panel.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Escape', code: 'Escape', keyCode: 27, which: 27,
        bubbles: true, cancelable: true
      }));
    } catch (_) {}

    setTimeout(function () {
      const stillOpen = settingsPanel();
      if (!stillOpen) return;
      const needles = ['close', 'kapat', 'back', 'geri', 'schliessen', 'schließen', 'fermer']
        .map(normalize);
      for (const element of clickableCandidates(stillOpen)) {
        if (hasAnyText(element, needles)) {
          clickElement(element);
          return;
        }
      }
    }, 100);
  }

  function finish(success, message) {
    completed = !!success;
    failed = !success;
    state = success ? 'done' : 'failed';
    document.documentElement.dataset.ggqColorConfig = success ? 'done' : 'failed';
    if (settingsOpenedByUs) closeSettings();
    log(message);
  }

  function auto3DReady() {
    try {
      const auto = window.GeoGebraQuestAuto3D;
      return !!(auto && auto.isProjectionArmed && auto.isProjectionArmed());
    } catch (_) { return false; }
  }

  function tick() {
    if (completed || failed) return;

    if (!auto3DReady()) {
      state = 'waiting-3d';
      return;
    }

    if (!startedAt) {
      startedAt = performance.now();
      document.documentElement.dataset.ggqColorConfig = 'working';
      state = 'opening-settings';
      log('Glasses projection active -> opening 3D Projection settings');
    }

    if (performance.now() - startedAt > MAX_CONFIG_MS) {
      finish(false, 'Could not disable GeoGebra GrayScale automatically');
      return;
    }

    const panel = settingsPanel();
    if (panel) {
      settingsOpenedByUs = true;
      const section = findProjectionSection(panel);
      if (!section) {
        state = 'searching-projection';
        return;
      }

      if (!ensureProjectionExpanded(section)) return;

      const checkbox = findGrayScaleCheckbox(section);
      if (!checkbox) {
        state = 'searching-grayscale';
        return;
      }

      if (checkboxChecked(checkbox)) {
        state = 'disabling-grayscale';
        clickElement(checkbox);
        setTimeout(function () {
          const p = settingsPanel();
          const s = p && findProjectionSection(p);
          const current = s && findGrayScaleCheckbox(s);
          if (!current || !checkboxChecked(current)) {
            finish(true, 'GeoGebra GrayScale OFF -> full colour source frames');
          }
        }, 180);
      } else {
        finish(true, 'GeoGebra GrayScale already OFF');
      }
      return;
    }

    const settings = findSettingsAction();
    if (settings) {
      settingsOpenedByUs = true;
      state = 'opening-settings';
      clickElement(settings);
      return;
    }

    if (!menuOpenedByUs) {
      const menu = findMenuLauncher();
      if (menu) {
        menuOpenedByUs = true;
        state = 'opening-menu';
        clickElement(menu);
      }
    }
  }

  window.GeoGebraQuestColorPatch = {
    isInstalled: function () { return true; },
    isConfigured: function () { return completed; },
    hasFailed: function () { return failed; },
    getState: function () { return state; },
    projectionExpandedByUs: function () { return projectionExpandedByUs; },
    retry: function () {
      completed = false;
      failed = false;
      startedAt = 0;
      menuOpenedByUs = false;
      settingsOpenedByUs = false;
      projectionExpandedByUs = false;
      state = 'waiting-3d';
      delete document.documentElement.dataset.ggqColorConfig;
    }
  };

  setInterval(tick, TICK_MS);
  tick();
})();
