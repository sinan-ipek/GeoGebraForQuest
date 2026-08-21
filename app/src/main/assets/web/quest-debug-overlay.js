(function () {
  'use strict';

  if (window.__ggqDebugOverlayV074) return;
  window.__ggqDebugOverlayV074 = true;

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
      recentLogs.push(text.replace(/\s+/g, ' ').slice(0, 180));
      while (recentLogs.length > 7) recentLogs.shift();
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
    panel.id = 'ggq-debug-overlay-v074';
    panel.style.cssText = [
      'position:fixed','right:10px','top:10px','z-index:2147483647',
      'width:365px','max-width:48vw','box-sizing:border-box','padding:9px 10px',
      'border-radius:8px','background:rgba(0,0,0,.82)','color:#b8ffbd',
      'font:11px/1.35 monospace','white-space:pre-wrap','pointer-events:none',
      'box-shadow:0 2px 12px rgba(0,0,0,.35)'
    ].join(';');
    const title = document.createElement('div');
    title.textContent = 'GGQ v0.7.4 FRONT-PORTAL DEBUG';
    title.style.cssText = 'font-weight:bold;color:#fff;margin-bottom:5px;font-size:12px';
    panel.appendChild(title);
    body = document.createElement('div');
    panel.appendChild(body);
    (document.body || document.documentElement).appendChild(panel);
  }

  function largestWebGlCanvas() {
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
        if (area > bestArea) {
          bestArea = area;
          best = { canvas: canvas, gl: gl, rect: rect };
        }
      } catch (_) {}
    }
    return best;
  }

  function yes(value) { return value ? 'YES' : 'no'; }

  function nativeStatus() {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge.getStereoDebugStatus !== 'function') return null;
      const raw = window.QuestBridge.getStereoDebugStatus();
      return raw ? JSON.parse(String(raw)) : null;
    } catch (_) { return null; }
  }

  function update() {
    ensurePanel();

    let captureEnabled = false;
    try {
      captureEnabled = !!(window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled());
    } catch (_) {}

    const auto = window.GeoGebraQuestAuto3D;
    let autoInstalled = false;
    let view3D = false;
    let viewExposed = false;
    let projectionArmed = false;
    let popupRequested = false;
    let stereoRequested = false;
    let portalSuppressed = false;
    let overlayActive = false;
    try {
      autoInstalled = !!(auto && auto.isInstalled && auto.isInstalled());
      view3D = !!(auto && auto.is3DVisible && auto.is3DVisible());
      viewExposed = !!(auto && auto.is3DExposed && auto.is3DExposed());
      projectionArmed = !!(auto && auto.isProjectionArmed && auto.isProjectionArmed());
      popupRequested = !!(auto && auto.isProjectionPopupRequested && auto.isProjectionPopupRequested());
      stereoRequested = !!(auto && auto.isStereoRequested && auto.isStereoRequested());
      portalSuppressed = !!(auto && auto.isPortalSuppressed && auto.isPortalSuppressed());
      overlayActive = !!(auto && auto.isOverlayActive && auto.isOverlayActive());
    } catch (_) {}

    const color = window.GeoGebraQuestColorPatch;
    let colorInstalled = false;
    let colorConfigured = false;
    let colorFailed = false;
    let colorState = 'loading';
    try {
      colorInstalled = !!(color && color.isInstalled && color.isInstalled());
      colorConfigured = !!(color && color.isConfigured && color.isConfigured());
      colorFailed = !!(color && color.hasFailed && color.hasFailed());
      colorState = color && color.getState ? String(color.getState()) : 'loading';
    } catch (_) {}

    let getContextHook = false;
    try {
      getContextHook = !!(HTMLCanvasElement.prototype.getContext &&
        HTMLCanvasElement.prototype.getContext.__ggqStereoGetContextHookV6);
    } catch (_) {}

    const item = largestWebGlCanvas();
    let glHook = false;
    let clearHook = false;
    let glSize = 'none';
    let cssSize = 'none';
    if (item) {
      try {
        glHook = !!(item.gl.colorMask && item.gl.colorMask.__ggqStereoMaskHookV6);
        clearHook = !!(item.gl.clear && item.gl.clear.__ggqStereoClearHookV6);
        glSize = item.gl.drawingBufferWidth + 'x' + item.gl.drawingBufferHeight;
        cssSize = Math.round(item.rect.width) + 'x' + Math.round(item.rect.height);
      } catch (_) {}
    }

    const native = nativeStatus();
    const lines = [];
    lines.push('auto 3D ctl:      ' + yes(autoInstalled));
    lines.push('3D visible:       ' + yes(view3D));
    lines.push('3D exposed:       ' + yes(viewExposed));
    lines.push('glasses forced:   ' + yes(projectionArmed));
    lines.push('front overlay:    ' + yes(overlayActive));
    lines.push('popup requested:  ' + yes(popupRequested));
    lines.push('portal suppressed:' + yes(portalSuppressed));
    lines.push('full colour:      ' + (colorConfigured ? 'YES' : colorFailed ? 'FAILED' : colorState));
    lines.push('color patch:      ' + yes(colorInstalled));
    lines.push('stereo requested: ' + yes(stereoRequested));
    lines.push('stereo JS:        ' + (captureEnabled ? 'ON' : 'off'));
    lines.push('getContext hook:  ' + yes(getContextHook));
    lines.push('GL mask/clear:    ' + yes(glHook) + ' / ' + yes(clearHook));
    lines.push('canvas GL/CSS:    ' + glSize + ' / ' + cssSize);

    if (native) {
      lines.push('native stereo:    ' + (native.stereoEnabled ? 'ON' : 'off'));
      lines.push('surface/entity:   ' + yes(native.surfaceAttached) + ' / ' + yes(native.portalEntityReady));
      lines.push('portal allowed:   ' + yes(native.portalPresentationAllowed));
      lines.push('portal nonhit:    ' + yes(native.portalNonHittable));
      lines.push('portal rects:     ' + native.portalRects + ' visible=' + yes(native.portalVisible));
      lines.push('frames R/A/P:     ' + native.framesReceived + '/' + native.framesAccepted + '/' + native.framesPresented);
      lines.push('busy/reject:      ' + native.framesDroppedBusy + '/' + native.framesRejected);
      lines.push('last eye size:    ' + native.lastEyeWidth + 'x' + native.lastEyeHeight);
    } else {
      lines.push('native status:    unavailable');
    }

    lines.push('--- last GGQ logs ---');
    if (recentLogs.length) recentLogs.forEach(function (line) { lines.push(line); });
    else lines.push('(none captured yet)');
    body.textContent = lines.join('\n');
  }

  ensurePanel();
  update();
  setInterval(update, 350);
})();
