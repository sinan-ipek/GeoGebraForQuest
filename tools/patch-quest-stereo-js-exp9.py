#!/usr/bin/env python3
"""Patch exp8 stereo scheduler for UI-priority delivery.

Exp9 keeps demand-driven LEFT_EYE rendering, but prevents capture from starving
GeoGebra's DOM/UI thread:
- JPEG encoding uses canvas.toBlob() + FileReader asynchronously.
- Slow stereo pairs use adaptive backoff instead of a fixed 16 ms retry.
- Visible GeoGebra popup/menu UI temporarily pauses new stereo-pair requests.
- A-button/context-menu code can explicitly request a short UI-priority window.
The last delivered stereo frame remains visible while capture is paused.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-quest-stereo-js-exp9.py <quest-stereo-layout.js>")

    path = Path(sys.argv[1]).resolve()
    text = path.read_text(encoding="utf-8")

    if "EXP9_UI_PRIORITY" in text:
        print("[GGQ] exp9 UI-priority scheduler already patched")
        return

    text = replace_once(
        text,
        "  var lastStereoMotionAt = -100000;\n"
        "  var hasSeenActive3D = false;\n",
        "  var lastStereoMotionAt = -100000;\n"
        "  var stereoEncodeInFlight = false;\n"
        "  var uiPriorityUntil = 0;\n"
        "  var EXP9_UI_PRIORITY = true;\n"
        "  var hasSeenActive3D = false;\n",
        "add exp9 UI-priority state",
    )

    marker = "  function markStereoMotion() {\n"
    if marker not in text:
        raise RuntimeError("markStereoMotion anchor not found")

    helpers = r'''  function exp9Now() {
    try { return performance.now(); } catch (_) { return Date.now(); }
  }

  function prioritizeGeoGebraUi(durationMs) {
    var now = exp9Now();
    var duration = Math.max(0, Number(durationMs || 0));
    uiPriorityUntil = Math.max(uiPriorityUntil, now + duration);
  }

  window.__ggqPrioritizeUi = prioritizeGeoGebraUi;

  function isVisibleGeoGebraPopup() {
    var selectors = [
      '.gwt-PopupPanel',
      '.contextMenu',
      '.selectionMenu',
      '.menuPanel',
      '.matMenu',
      '.propertiesPanel',
      '[role="menu"]',
      '[role="dialog"]',
      '[aria-modal="true"]'
    ];
    for (var s = 0; s < selectors.length; s++) {
      var nodes;
      try { nodes = document.querySelectorAll(selectors[s]); } catch (_) { continue; }
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (!node || !node.isConnected) continue;
        var style;
        try { style = getComputedStyle(node); } catch (_) { continue; }
        if (!style || style.display === 'none' || style.visibility === 'hidden' ||
            Number(style.opacity || 1) === 0) continue;
        var rect;
        try { rect = node.getBoundingClientRect(); } catch (_) { continue; }
        if (rect && rect.width > 2 && rect.height > 2) return true;
      }
    }
    return false;
  }

  function adaptiveStereoDelay(renderLatency) {
    // Keep 20 fps for genuinely light scenes, but deliberately leave increasingly
    // large RIGHT-only/UI windows as a requested stereo pair becomes expensive.
    if (renderLatency <= 55) return 0;
    if (renderLatency <= 90) return 30;
    if (renderLatency <= 150) return 60;
    if (renderLatency <= 250) return 100;
    return 150;
  }

  function canvasToDataUrlAsync(canvas, callback) {
    try {
      if (!canvas || typeof canvas.toBlob !== 'function') {
        callback(null);
        return;
      }
      canvas.toBlob(function (blob) {
        if (!blob) {
          callback(null);
          return;
        }
        try {
          var reader = new FileReader();
          reader.onloadend = function () {
            callback(typeof reader.result === 'string' ? reader.result : null);
          };
          reader.onerror = function () { callback(null); };
          reader.readAsDataURL(blob);
        } catch (_) {
          callback(null);
        }
      }, 'image/jpeg', CAPTURE_JPEG_QUALITY);
    } catch (_) {
      callback(null);
    }
  }

'''
    text = text.replace(marker, helpers + marker, 1)

    replacement = r'''  function captureStereoEyes(serial, now, onComplete) {
    if (!leftCaptureContext || !rightCaptureContext) {
      onComplete(false);
      return;
    }
    if (serial === lastDeliveredStereoSerial) {
      onComplete(true);
      return;
    }

    // The requested LEFT/RIGHT pair is complete; only copy/encode it here.
    var visible3DCanvas = findVisible3DCanvas();
    if (!visible3DCanvas) {
      reportStereoInactive();
      onComplete(false);
      return;
    }
    reportStereoActive();

    var eyes = getRendererEyeCanvases();
    if (!eyes) {
      onComplete(false);
      return;
    }

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) {
        onComplete(false);
        return;
      }

      var maxEyeWidth = captureEyeWidth(now);
      var scale = Math.min(1, maxEyeWidth / sourceWidth);
      var eyeWidth = Math.max(2, Math.round(sourceWidth * scale));
      var eyeHeight = Math.max(2, Math.round(sourceHeight * scale));
      ensureCaptureCanvasSize(eyeWidth, eyeHeight);

      leftCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      rightCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );

      // Exp9: JPEG work is asynchronous so toolbar/menu DOM work is not held up
      // by two synchronous JPEG data-URL encodes on every stereo delivery.
      stereoEncodeInFlight = true;
      var leftDataUrl = null;
      var rightDataUrl = null;
      var completed = 0;

      function finishOne() {
        completed++;
        if (completed < 2) return;
        stereoEncodeInFlight = false;
        if (
          leftDataUrl && leftDataUrl.length > 64 &&
          rightDataUrl && rightDataUrl.length > 64
        ) {
          bridgeStereoEyes(leftDataUrl, rightDataUrl);
          lastDeliveredStereoSerial = serial;
          onComplete(true);
        } else {
          onComplete(false);
        }
      }

      canvasToDataUrlAsync(leftCaptureCanvas, function (value) {
        leftDataUrl = value;
        finishOne();
      });
      canvasToDataUrlAsync(rightCaptureCanvas, function (value) {
        rightDataUrl = value;
        finishOne();
      });
    } catch (_) {
      stereoEncodeInFlight = false;
      onComplete(false);
    }
  }

  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null || stereoEncodeInFlight) return false;

    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    captureStereoEyes(serial, now, function (success) {
      var completedAt = exp9Now();
      var renderLatency = Math.max(0, completedAt - requestedAt);
      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;

      if (!success) {
        nextStereoRequestAt = completedAt + CAPTURE_INTERVAL_MS;
        return;
      }

      var delay = adaptiveStereoDelay(renderLatency);
      nextStereoRequestAt = renderLatency <= 55
        ? Math.max(completedAt, requestedAt + CAPTURE_INTERVAL_MS)
        : completedAt + delay;
    });
    return true;
  }

  function captureLoop(now) {
    if (stereoEncodeInFlight) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
      requestAnimationFrame(captureLoop);
      return;
    }

    // UI always wins over a fresh stereo request. Keep the last delivered VideoSurface
    // frame visible while menus/dialogs are open or an A-button action is settling.
    if (now < uiPriorityUntil || isVisibleGeoGebraPopup()) {
      nextStereoRequestAt = now + 100;
      requestAnimationFrame(captureLoop);
      return;
    }

    var visible3DCanvas = findVisible3DCanvas();
    if (!visible3DCanvas) {
      reportStereoInactive();
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
      requestAnimationFrame(captureLoop);
      return;
    }
    reportStereoActive();

    if (!requestStereoPair(now)) {
      nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }
    requestAnimationFrame(captureLoop);
  }
'''

    text, count = re.subn(
        r"  function captureStereoEyes\(serial, now\) \{.*?"
        r"  function captureLoop\(now\) \{.*?\n  \}\n",
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(
            f"replace exp8 capture scheduler: expected exactly one match, found {count}"
        )

    # The old fixed 16 ms breathing-window policy must not survive exp9.
    if "now + 16" in text:
        raise RuntimeError("exp9 patch left the old 16 ms slow-frame retry in place")
    if ".toDataURL(" in text:
        raise RuntimeError("exp9 patch left synchronous toDataURL JPEG encoding in place")

    path.write_text(text, encoding="utf-8")
    print("[GGQ] patched exp9 async JPEG + adaptive backoff + popup/UI priority")


if __name__ == "__main__":
    main()
