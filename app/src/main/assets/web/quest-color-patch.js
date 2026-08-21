(function () {
  'use strict';

  if (window.__ggqColorPatchV077) return;
  window.__ggqColorPatchV077 = true;

  // v0.7.7 intentionally disables the automatic GeoGebra Settings/GrayScale
  // manipulation. The v0.7.6 screenshots proved that the stereo portal was
  // deadlocking before the colour path mattered. Keeping Settings closed makes
  // this build a clean depth-only test. Colour will be re-enabled after the
  // first-frame portal handshake is stable.
  window.GeoGebraQuestColorPatch = {
    isInstalled: function () { return true; },
    isConfigured: function () { return false; },
    hasFailed: function () { return false; },
    getState: function () { return 'disabled-depth-test'; },
    retry: function () {}
  };

  console.log('[GGQ Color v0.7.7] disabled temporarily for depth handshake test');
})();
