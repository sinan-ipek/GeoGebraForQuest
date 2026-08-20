(function () {
  'use strict';

  if (window.__ggqDebugOverlayV068) return;
  window.__ggqDebugOverlayV068 = true;

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
      while (recentLogs.length > 4) recentLogs.shift();
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
    panel.id = 'ggq-debug-overlay-v068';
    panel.style.cssText = [
      'position:fixed',
      'right:10px',
      'top:10px',
      'z-index:2147483647',
      'width:320px',
      'max-width:42vw',
      'box-sizing:border-box',
      'padding:9px 10px',
      'border-radius:8px',
      'background:rgba(0,0,0,.82)',
      'color:#b8ffbd',
      'font:11px/1.35 monospace',
      'white-space:pre-wrap',
      'pointer-events:none',
      'box-shadow:0 2px 12px rgba(0,0,0,.35)'
    ].join(';');

    const title = document.createElement('div');
    title.textContent = 'GGQ v0.6.8 DEBUG';
    title.style.cssText = 'font-weight:bold;color:#fff;margin-bottom:5px;font-size:12px';
    panel.appendChild(title);

    body = document.createElement('div');
    body.textContent = 'waiting for GeoGebra…';
    panel.appendChild(body);

    (document.body || document.documentElement).appendChild(panel);
  }

  function largestWebGlCanvas() {
    const root = document.getElementById('ggb-element') || document;
    const canvases = Array.from(root.querySelectorAll('canvas'));
    let best = null;
    let bestArea = 0;

    for (const canvas of canvases) {
      try {
        const rect = canvas.getBoundingClientRect();
        if (rect.width < 100 || rect.height < 100) continue;
        const gl = canvas.getContext('webgl2') ||
          canvas.getContext('webgl') ||
          canvas.getContext('experimental-webgl');
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

  function yes(value) {
    return value ? 'YES' : 'no';
  }

  function nativeStatus() {
    try {
      if (!window.QuestBridge || typeof window.QuestBridge.getStereoDebugStatus !== 'function') {
        return null;
      }
      const raw = window.QuestBridge.getStereoDebugStatus();
      if (!raw) return null;
      return JSON.parse(String(raw));
    } catch (_) {
      return null;
    }
  }

  function update() {
    ensurePanel();

    let captureEnabled = false;
    try {
      captureEnabled = !!(
        window.GeoGebraQuestStereoCapture &&
        typeof window.GeoGebraQuestStereoCapture.isEnabled === 'function' &&
        window.GeoGebraQuestStereoCapture.isEnabled()
      );
    } catch (_) {}

    let getContextHook = false;
    try {
      getContextHook = !!(
        window.HTMLCanvasElement &&
        HTMLCanvasElement.prototype &&
        HTMLCanvasElement.prototype.getContext &&
        HTMLCanvasElement.prototype.getContext.__ggqStereoGetContextHookV6
      );
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
    lines.push('stereo JS:       ' + (captureEnabled ? 'ON' : 'off'));
    lines.push('getContext hook: ' + yes(getContextHook));
    lines.push('GL mask hook:    ' + yes(glHook));
    lines.push('GL clear hook:   ' + yes(clearHook));
    lines.push('canvas GL/CSS:   ' + glSize + ' / ' + cssSize);

    if (native) {
      lines.push('native stereo:   ' + (native.stereoEnabled ? 'ON' : 'off'));
      lines.push('surface/entity:  ' + yes(native.surfaceAttached) + ' / ' + yes(native.portalEntityReady));
      lines.push('portal rects:    ' + native.portalRects + ' visible=' + yes(native.portalVisible));
      lines.push(
        'frames R/A/P:   ' + native.framesReceived + '/' +
        native.framesAccepted + '/' + native.framesPresented
      );
      lines.push(
        'busy/reject:    ' + native.framesDroppedBusy + '/' + native.framesRejected
      );
      lines.push('last eye size:   ' + native.lastEyeWidth + 'x' + native.lastEyeHeight);
    } else {
      lines.push('native status:   unavailable');
    }

    lines.push('--- last GGQ logs ---');
    if (recentLogs.length) {
      recentLogs.forEach(function (line) { lines.push(line); });
    } else {
      lines.push('(none captured yet)');
    }

    body.textContent = lines.join('\n');
  }

  ensurePanel();
  update();
  setInterval(update, 400);
})();
