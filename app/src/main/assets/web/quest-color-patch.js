(function () {
  'use strict';

  if (window.__ggqColorPatchV071) return;
  window.__ggqColorPatchV071 = true;

  // GeoGebra's Glasses projection intentionally defaults to grayscale. Quest
  // stereo does not need anaglyph colour filtering, so v0.7.1 silently opens the
  // 3D settings once, turns the Glasses GrayScale checkbox off, then closes the
  // settings again. This changes GeoGebra's own EuclidianSettings3D before the
  // direct-eye WebGL capture, so object colours are preserved at their source.

  const MAX_CONFIG_MS = 5000;
  const TICK_MS = 80;

  let state = 'waiting-3d';
  let startedAt = 0;
  let menuOpenedByUs = false;
  let settingsOpenedByUs = false;
  let completed = false;
  let failed = false;

  function log(message) {
    console.log('[GGQ Color v0.7.1] ' + message);
  }

  function normalize(value) {
    return String(value || '')
      .trim()
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[\s_\-–—]+/g, ' ');
  }

  function visible(element) {
    if (!element || !element.isConnected) return false;
    try {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        Number(style.opacity || 1) !== 0 && rect.width > 2 && rect.height > 2 &&
        rect.bottom > 0 && rect.right > 0 && rect.left < innerWidth && rect.top < innerHeight;
    } catch (_) {
      return false;
    }
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

  function clickableCandidates() {
    return Array.from(document.querySelectorAll(
      'button,[role="button"],[role="menuitem"],.menuItem,.menuItemView,.settingsBtn,.headerButton,.standardButton'
    )).filter(visible);
  }

  function clickElement(element) {
    if (!element) return false;
    try {
      if (typeof element.click === 'function') {
        element.click();
        return true;
      }
      element.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window
      }));
      return true;
    } catch (_) {
      return false;
    }
  }

  function findGrayCheckbox() {
    const checkboxes = Array.from(document.querySelectorAll('.checkboxPanel,[role="checkbox"]'));
    const needles = [
      'gri olcek', 'gri ölçek', 'gray scale', 'grayscale',
      'graustufen', 'echelle de gris', 'escala de grises'
    ].map(normalize);

    for (const checkbox of checkboxes) {
      if (!visible(checkbox)) continue;
      if (hasAnyText(checkbox, needles)) return checkbox;
    }
    return null;
  }

  function isChecked(checkbox) {
    if (!checkbox) return false;
    const aria = String(checkbox.getAttribute('aria-checked') || '').toLowerCase();
    if (aria === 'true') return true;
    if (aria === 'false') return false;
    return !!checkbox.querySelector('.checkbox.selected');
  }

  function findSettingsAction() {
    const needles = ['ayarlar', 'settings', 'einstellungen', 'parametres', 'ajustes'].map(normalize);
    for (const element of clickableCandidates()) {
      if (hasAnyText(element, needles)) return element;
    }
    return null;
  }

  function findMenuLauncher() {
    const needles = ['menu', 'menü', 'ana menu', 'main menu', 'open menu'].map(normalize);
    for (const element of clickableCandidates()) {
      if (element.closest && element.closest('.SelectionTable')) continue;
      if (hasAnyText(element, needles)) return element;
    }

    // Constrained hamburger fallback: do not mistake a 3D stylebar popup for the
    // main menu merely because both contain "menu" in a CSS class.
    for (const element of clickableCandidates()) {
      const cls = normalize(element.className);
      if (cls.indexOf('menu') < 0 || cls.indexOf('item') >= 0) continue;
      const rect = element.getBoundingClientRect();
      if (rect.top < 100 && rect.left > innerWidth * 0.70) return element;
    }
    return null;
  }

  function settingsPanel() {
    // ComponentSideSheet receives the PropertiesViewW class when it is actually
    // GeoGebra Settings. The hamburger menu may also be a side sheet, so never
    // treat a generic .sideSheet as Settings here.
    const panels = Array.from(document.querySelectorAll('.PropertiesViewW'));
    for (const panel of panels) {
      if (visible(panel)) return panel;
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
      const candidates = Array.from(stillOpen.querySelectorAll(
        'button,[role="button"],.headerButton,.closeButton,.backButton'
      )).filter(visible);
      const needles = ['close', 'kapat', 'back', 'geri', 'schliessen', 'schließen'].map(normalize);
      for (const element of candidates) {
        if (hasAnyText(element, needles)) {
          clickElement(element);
          return;
        }
      }
    }, 80);
  }

  function finish(success, message) {
    if (success) completed = true;
    else failed = true;
    state = success ? 'done' : 'failed';
    document.documentElement.dataset.ggqColorConfig = success ? 'done' : 'failed';
    if (settingsOpenedByUs) closeSettings();
    log(message);
  }

  function auto3DReady() {
    try {
      const auto = window.GeoGebraQuestAuto3D;
      return !!(auto && auto.isProjectionArmed && auto.isProjectionArmed());
    } catch (_) {
      return false;
    }
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
      state = 'search-checkbox';
      log('Glasses projection active -> disabling GeoGebra grayscale');
    }

    if (performance.now() - startedAt > MAX_CONFIG_MS) {
      finish(false, 'Could not reach GrayScale setting automatically');
      return;
    }

    const checkbox = findGrayCheckbox();
    if (checkbox) {
      if (isChecked(checkbox)) {
        clickElement(checkbox);
        setTimeout(function () {
          const current = findGrayCheckbox();
          if (!current || !isChecked(current)) {
            finish(true, 'GeoGebra Glasses grayscale OFF -> full colour enabled');
          }
        }, 100);
      } else {
        finish(true, 'GeoGebra Glasses grayscale already OFF');
      }
      return;
    }

    const panel = settingsPanel();
    if (panel) {
      settingsOpenedByUs = true;
      state = 'settings-open';
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
    retry: function () {
      completed = false;
      failed = false;
      startedAt = 0;
      menuOpenedByUs = false;
      settingsOpenedByUs = false;
      state = 'waiting-3d';
      delete document.documentElement.dataset.ggqColorConfig;
    }
  };

  setInterval(tick, TICK_MS);
  tick();
})();
