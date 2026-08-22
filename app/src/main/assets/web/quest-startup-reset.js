(function () {
  'use strict';

  if (window.__ggqConstructionResetV076) return;
  window.__ggqConstructionResetV076 = true;

  let lastSignature = null;
  let lastChangeAt = performance.now();
  let stableSince = 0;
  let generation = 0;

  function currentSignature() {
    try {
      const api = window.ggbApplet;
      if (!api || typeof api.getAllObjectNames !== 'function') return null;
      const names = Array.from(api.getAllObjectNames() || []);
      // Object names are a cheap construction identity. Slider motion and ordinary
      // 3D interaction do not change this signature, while opening/replacing a
      // construction normally does.
      return names.join('\u001f');
    } catch (_) {
      return null;
    }
  }

  function notifyChange(reason) {
    generation += 1;
    lastChangeAt = performance.now();
    stableSince = 0;
    try {
      if (window.GeoGebraQuestAuto3D &&
          typeof window.GeoGebraQuestAuto3D.resetForConstructionChange === 'function') {
        window.GeoGebraQuestAuto3D.resetForConstructionChange(reason || 'construction-change');
      }
    } catch (_) {}
    console.log('[GGQ Startup v0.7.6] construction generation ' + generation + ' -> ' + (reason || 'changed'));
  }

  function poll() {
    const signature = currentSignature();
    if (signature == null) return;

    if (lastSignature == null) {
      lastSignature = signature;
      lastChangeAt = performance.now();
      stableSince = performance.now();
      return;
    }

    if (signature !== lastSignature) {
      lastSignature = signature;
      notifyChange('object-set-changed');
      return;
    }

    if (!stableSince) stableSince = performance.now();
  }

  window.GeoGebraQuestStartupReset = {
    isInstalled: function () { return true; },
    getGeneration: function () { return generation; },
    getQuietMs: function () { return Math.max(0, performance.now() - lastChangeAt); },
    isQuiet: function (minimumMs) {
      return performance.now() - lastChangeAt >= Number(minimumMs || 0);
    },
    forceReset: function (reason) { notifyChange(reason || 'forced'); }
  };

  setInterval(poll, 150);
  poll();
})();
