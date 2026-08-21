(function () {
  'use strict';

  if (window.__ggqDebugOverlayV076) return;
  window.__ggqDebugOverlayV076 = true;

  const recentLogs = [];
  let panel = null;
  let body = null;

  function rememberLog(args) {
    try {
      const text = Array.prototype.slice.call(args).map(function (value) {
        if (typeof value === 'string') return value;
        try { return JSON.stringify(value); } catch (_) { return String(value); }
      }).join(' ');
      if (text.indexOf('GGQ') < 0 && text.indexOf('GeoGebraForQuest') < 0) return;
      recentLogs.push(text.replace(/\s+/g, ' ').slice(0, 190));
      while (recentLogs.length > 8) recentLogs.shift();
    } catch (_) {}
  }

  ['log', 'warn', 'error'].forEach(function (name) {
    try {
      const original = console[name];
      if (typeof original !== 'function' || original.__ggqDebugWrapped) return;
      const wrapped = function () {
        rememberLog(arguments);
        return original.apply(console, arguments);
      };
      wrapped.__ggqDebugWrapped = true;
      console[name] = wrapped;
    } catch (_) {}
  });

  function ensurePanel() {
    if (panel && panel.isConnected) return;
    panel = document.createElement('div');
    panel.id = 'ggq-debug-overlay-v076';
    panel.style.cssText = [
      'position:fixed','right:10px','top:10px','z-index:2147483647',
      'width:390px','max-width:49vw','box-sizing:border-box','padding:9px 10px',
      'border-radius:8px','background:rgba(0,0,0,.82)','color:#b8ffbd',
      'font:11px/1.35 monospace','white-space:pre-wrap','pointer-events:none',
      'box-shadow:0 2px 12px rgba(0,0,0,.35)'
    ].join(';');
    const title = document.createElement('div');
    title.textContent = 'GGQ v0.7.6 CONSTRUCTION-REARM DEBUG';
    title.style.cssText = 'font-weight:bold;color:#fff;margin-bottom:5px;font-size:12px';
    panel.appendChild(title);
    body = document.createElement('div');
    panel.appendChild(body);
    (document.body || document.documentElement).appendChild(panel);
  }

  function yes(value) { return value ? 'YES' : 'no'; }

  function nativeStatus() {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge.getStereoDebugStatus !== 'function') return null;
      const raw = window.QuestBridge.getStereoDebugStatus();
      return raw ? JSON.parse(String(raw)) : null;
    } catch (_) { return null; }
  }

  function captureEnabled() {
    try {
      return !!(window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled());
    } catch (_) { return false; }
  }

  function canvasInfo() {
    const root = document.getElementById('ggb-element') || document;
    let best = null;
    let bestArea = 0;
    for (const canvas of Array.from(root.querySelectorAll('canvas'))) {
      try {
        const rect = canvas.getBoundingClientRect();
        if (rect.width < 100 || rect.height < 100) continue;
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) continue;
        const area = rect.width * rect.height;
        if (area > bestArea) best = { gl: gl, rect: rect }, bestArea = area;
      } catch (_) {}
    }
    return best;
  }

  function update() {
    ensurePanel();
    const auto = window.GeoGebraQuestAuto3D;
    const reset = window.GeoGebraQuestStartupReset;
    const color = window.GeoGebraQuestColorPatch;
    const native = nativeStatus();
    const item = canvasInfo();

    let colorText = 'loading';
    try {
      if (color && color.isConfigured && color.isConfigured()) colorText = 'YES';
      else if (color && color.hasFailed && color.hasFailed()) colorText = 'FAILED';
      else if (color && color.getState) colorText = String(color.getState());
    } catch (_) {}

    let glHook = false, clearHook = false, glSize = 'none', cssSize = 'none';
    if (item) {
      try {
        glHook = !!(item.gl.colorMask && item.gl.colorMask.__ggqStereoMaskHookV6);
        clearHook = !!(item.gl.clear && item.gl.clear.__ggqStereoClearHookV6);
        glSize = item.gl.drawingBufferWidth + 'x' + item.gl.drawingBufferHeight;
        cssSize = Math.round(item.rect.width) + 'x' + Math.round(item.rect.height);
      } catch (_) {}
    }

    function call(name, fallback) {
      try { return auto && typeof auto[name] === 'function' ? auto[name]() : fallback; }
      catch (_) { return fallback; }
    }

    let quietMs = 0, constructionGeneration = 0;
    try {
      quietMs = reset && reset.getQuietMs ? Math.round(reset.getQuietMs()) : 0;
      constructionGeneration = reset && reset.getGeneration ? Number(reset.getGeneration()) || 0 : 0;
    } catch (_) {}

    const lines = [];
    lines.push('auto 3D ctl:       ' + yes(call('isInstalled', false)));
    lines.push('construction gen:  ' + constructionGeneration);
    lines.push('construction quiet:' + quietMs + ' ms');
    lines.push('rearm resets:      ' + Number(call('getResetGeneration', 0)));
    lines.push('last reset:        ' + String(call('getLastResetReason', '-')));
    lines.push('stable ticks:      ' + Number(call('getStableTicks', 0)));
    lines.push('3D visible:        ' + yes(call('is3DVisible', false)));
    lines.push('3D exposed:        ' + yes(call('is3DExposed', false)));
    lines.push('glasses armed:     ' + yes(call('isProjectionArmed', false)));
    lines.push('front overlay:     ' + yes(call('isOverlayActive', false)));
    lines.push('fresh presented:   ' + Number(call('getPresentedDelta', 0)) + ' / 2');
    lines.push('portal suppressed: ' + yes(call('isPortalSuppressed', false)));
    lines.push('full colour:       ' + colorText);
    lines.push('stereo requested:  ' + yes(call('isStereoRequested', false)));
    lines.push('stereo JS:         ' + (captureEnabled() ? 'ON' : 'off'));
    lines.push('GL mask/clear:     ' + yes(glHook) + ' / ' + yes(clearHook));
    lines.push('canvas GL/CSS:     ' + glSize + ' / ' + cssSize);

    if (native) {
      lines.push('native stereo:     ' + (native.stereoEnabled ? 'ON' : 'off'));
      lines.push('surface/entity:    ' + yes(native.surfaceAttached) + ' / ' + yes(native.portalEntityReady));
      lines.push('portal allowed:    ' + yes(native.portalPresentationAllowed));
      lines.push('portal nonhit:     ' + yes(native.portalNonHittable));
      lines.push('portal visible:    ' + yes(native.portalVisible));
      lines.push('frames R/A/P:      ' + native.framesReceived + '/' + native.framesAccepted + '/' + native.framesPresented);
      lines.push('busy/reject:       ' + native.framesDroppedBusy + '/' + native.framesRejected);
      lines.push('last eye size:     ' + native.lastEyeWidth + 'x' + native.lastEyeHeight);
    }

    lines.push('--- last GGQ logs ---');
    if (recentLogs.length) recentLogs.forEach(function (line) { lines.push(line); });
    else lines.push('(none captured yet)');
    body.textContent = lines.join('\n');
  }

  ensurePanel();
  update();
  setInterval(update, 300);
})();
