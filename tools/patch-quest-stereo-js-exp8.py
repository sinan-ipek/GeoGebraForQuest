#!/usr/bin/env python3
"""Patch quest-stereo-layout.js for exp8 demand-driven pair delivery.

The checked-in layout script remains the proven exp7 baseline. This build-time
patch changes only the capture scheduler: request a LEFT/RIGHT pair from the
GeoGebra renderer, wait for its serial to advance, encode each serial once,
and use 540px eye captures while the user is actively manipulating the scene.
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
        raise SystemExit("usage: patch-quest-stereo-js-exp8.py <quest-stereo-layout.js>")

    path = Path(sys.argv[1]).resolve()
    text = path.read_text(encoding="utf-8")

    if "CAPTURE_ACTIVE_EYE_WIDTH = 540" in text:
        print("[GGQ] exp8 JS capture scheduler already patched")
        return

    text = replace_once(
        text,
        "  var CAPTURE_INTERVAL_MS = 50;\n"
        "  var CAPTURE_MAX_EYE_WIDTH = 720;\n"
        "  var CAPTURE_JPEG_QUALITY = 0.78;\n"
        "  var lastCaptureAt = 0;\n"
        "  var hasSeenActive3D = false;\n"
        "  var inactiveReported = false;\n",
        "  // Exp8: 20 fps is a maximum stereo-pair request cadence, not a demand\n"
        "  // to render LEFT_EYE on every ordinary GeoGebra repaint.\n"
        "  var CAPTURE_INTERVAL_MS = 50;\n"
        "  var CAPTURE_ACTIVE_EYE_WIDTH = 540;\n"
        "  var CAPTURE_IDLE_EYE_WIDTH = 720;\n"
        "  var CAPTURE_IDLE_DELAY_MS = 300;\n"
        "  var CAPTURE_JPEG_QUALITY = 0.78;\n"
        "  var pendingStereoSerial = null;\n"
        "  var pendingStereoRequestedAt = 0;\n"
        "  var lastDeliveredStereoSerial = -1;\n"
        "  var nextStereoRequestAt = 0;\n"
        "  var lastStereoMotionAt = -100000;\n"
        "  var hasSeenActive3D = false;\n"
        "  var inactiveReported = false;\n",
        "replace fixed capture scheduler state",
    )

    text = replace_once(
        text,
        "  function reportStereoInactive() {\n"
        "    if (!hasSeenActive3D || inactiveReported) return;\n"
        "    inactiveReported = true;",
        "  function reportStereoInactive() {\n"
        "    pendingStereoSerial = null;\n"
        "    pendingStereoRequestedAt = 0;\n"
        "    lastDeliveredStereoSerial = -1;\n"
        "    nextStereoRequestAt = 0;\n"
        "    if (!hasSeenActive3D || inactiveReported) return;\n"
        "    inactiveReported = true;",
        "reset stereo request state when 3D becomes inactive",
    )

    replacement = r'''  function markStereoMotion() {
    try {
      lastStereoMotionAt = performance.now();
    } catch (_) {
      lastStereoMotionAt = Date.now();
    }
  }

  function markPointerMotion(event) {
    if (!event || event.buttons || Number(event.pressure || 0) > 0) {
      markStereoMotion();
    }
  }

  function captureEyeWidth(now) {
    return now - lastStereoMotionAt < CAPTURE_IDLE_DELAY_MS
      ? CAPTURE_ACTIVE_EYE_WIDTH
      : CAPTURE_IDLE_EYE_WIDTH;
  }

  function readStereoFrameSerial() {
    try {
      if (typeof window.ggqGetStereoFrameSerial !== 'function') return -1;
      var serial = Number(window.ggqGetStereoFrameSerial());
      return isFinite(serial) ? serial : -1;
    } catch (_) {
      return -1;
    }
  }

  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') return false;
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) return false;
      pendingStereoSerial = baseline;
      pendingStereoRequestedAt = now;
      return true;
    } catch (_) {
      return false;
    }
  }

  function captureStereoEyes(serial, now) {
    if (!leftCaptureContext || !rightCaptureContext) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    // Read-only delivery path: the renderer has already completed the requested LEFT/RIGHT pair.
    var visible3DCanvas = findVisible3DCanvas();
    if (!visible3DCanvas) {
      reportStereoInactive();
      return false;
    }
    reportStereoActive();

    var eyes = getRendererEyeCanvases();
    if (!eyes) return false;

    try {
      var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
      var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
      if (sourceWidth < 2 || sourceHeight < 2) return false;

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

      var leftDataUrl = leftCaptureCanvas.toDataURL(
        'image/jpeg',
        CAPTURE_JPEG_QUALITY
      );
      var rightDataUrl = rightCaptureCanvas.toDataURL(
        'image/jpeg',
        CAPTURE_JPEG_QUALITY
      );

      if (
        leftDataUrl && leftDataUrl.length > 64 &&
        rightDataUrl && rightDataUrl.length > 64
      ) {
        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        lastDeliveredStereoSerial = serial;
        return true;
      }
    } catch (_) {}
    return false;
  }

  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null) return false;

    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;
    if (!captureStereoEyes(serial, now)) return false;

    var requestedAt = pendingStereoRequestedAt;
    var renderLatency = Math.max(0, now - requestedAt);
    pendingStereoSerial = null;
    pendingStereoRequestedAt = 0;

    // Fast scenes retain a 20 fps maximum. If a requested pair itself already took
    // longer than 50 ms, leave one short right-only breathing window before asking
    // for another LEFT_EYE render so complex files can recover interaction frames.
    nextStereoRequestAt = renderLatency >= CAPTURE_INTERVAL_MS
      ? now + 16
      : requestedAt + CAPTURE_INTERVAL_MS;
    return true;
  }

  function captureLoop(now) {
    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }

    if (now < nextStereoRequestAt) {
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
        r"  function captureStereoEyes\(\) \{.*?"
        r"  function captureLoop\(now\) \{.*?\n  \}\n",
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(
            f"replace capture scheduler: expected exactly one match, found {count}"
        )

    text = replace_once(
        text,
        "  addEventListener('resize', schedule, { passive: true });\n"
        "  addEventListener('scroll', schedule, true);\n",
        "  addEventListener('resize', schedule, { passive: true });\n"
        "  addEventListener('scroll', schedule, true);\n\n"
        "  // Dynamic capture resolution: keep full 720px quality at rest, but reduce\n"
        "  // JPEG/decode traffic to 540px during active manipulation and for 300ms after.\n"
        "  document.addEventListener('pointerdown', markStereoMotion, true);\n"
        "  document.addEventListener('pointermove', markPointerMotion, true);\n"
        "  document.addEventListener('pointerup', markStereoMotion, true);\n"
        "  document.addEventListener('mousedown', markStereoMotion, true);\n"
        "  document.addEventListener('mousemove', markPointerMotion, true);\n"
        "  document.addEventListener('mouseup', markStereoMotion, true);\n"
        "  document.addEventListener('touchstart', markStereoMotion, { capture: true, passive: true });\n"
        "  document.addEventListener('touchmove', markStereoMotion, { capture: true, passive: true });\n"
        "  document.addEventListener('touchend', markStereoMotion, { capture: true, passive: true });\n"
        "  document.addEventListener('wheel', markStereoMotion, { capture: true, passive: true });\n"
        "  document.addEventListener('keydown', markStereoMotion, true);\n",
        "add dynamic-resolution interaction tracking",
    )

    path.write_text(text, encoding="utf-8")
    print("[GGQ] patched exp8 serial-gated demand capture + 540/720 dynamic resolution")


if __name__ == "__main__":
    main()
