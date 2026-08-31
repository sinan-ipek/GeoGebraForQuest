#!/usr/bin/env python3
"""Exp39: direct OAuth login plus cross-view temporary Move and zoom.

Login:
- Replace Exp38's repeated eight-second MessageEvent dispatch with the direct
  LoginOperationW JsInterop entrypoint exported by source patch v0935.
- One transaction calls performTokenLogin once and waits up to 45 seconds for
  the exact SUCCESS marker. A popup-owned native loop may then start a fresh
  transaction; it never restarts an in-flight validation every few seconds.
- Keep the popup-lifetime OAuth probe and SUCCESS-only native persistence.

Controller:
- Right Grip temporarily selects GeoGebra Move (mode 0), synthesizes the
  corresponding mouse drag on the graph canvas under the ray, and restores the
  exact prior tool on release. This works in both 2D Graphics and 3D Graphics.
- Right-thumb UP/DOWN targets the graph canvas under the ray, so deterministic
  wheel zoom works in both 2D and 3D instead of being gated by the stereo hole.
"""

from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp39.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
thumb_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestThumbZoomState.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")
thumb = thumb_path.read_text(encoding="utf-8")

for required in (
    "EXP38_ACK_DRIVEN_TOKEN_DELIVERY",
    "EXP38_LIFETIME_OAUTH_PROBE",
    "EXP38_TRUSTED_CALLBACK_RETRY",
    "EXP35_LOGIN_IME_NEXT_GUARD",
    "EXP35_RIGHT_THUMB_ZOOM_BRIDGE",
    "EXP13_GRIP_ROTATE_BRIDGE",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in panel:
        raise RuntimeError(f"exp39 panel baseline missing: {required}")


def replace_function(source: str, signature: str, replacement: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"exp39 function not found: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise RuntimeError(f"exp39 opening brace missing: {signature}")
    depth = 0
    for index in range(brace, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[:start] + replacement + source[index + 1 :]
    raise RuntimeError(f"exp39 closing brace missing: {signature}")


# ---------------------------------------------------------------------------
# 1. Direct LoginOperationW call: exactly one performTokenLogin per transaction.
# ---------------------------------------------------------------------------
delivery = r'''    // EXP39_DIRECT_LOGIN_OPERATION: call the local GeoGebra login
    // operation directly. Do not repeatedly restart it with MessageEvents.
    fun deliverLoginToken(token: String): Boolean {
        val main = mainWebView.get() ?: return false
        if (token.isBlank()) return false
        val jsToken = JSONObject.quote(token)

        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var token = $jsToken;
                  var existing = window.__ggqExp39LoginDelivery;
                  if (existing && existing.token === token &&
                      !existing.cancelled && !existing.acked) {
                    return 'active';
                  }

                  var state = {
                    token: token,
                    cancelled: false,
                    acked: false,
                    dispatched: false,
                    dispatchedAt: 0
                  };
                  window.__ggqExp39LoginDelivery = state;

                  function acknowledgeSuccess() {
                    if (state.acked) return;
                    state.acked = true;
                    try {
                      if (window.QuestBridge &&
                          typeof window.QuestBridge.loginTokenAck === 'function') {
                        window.QuestBridge.loginTokenAck(state.token);
                      }
                    } catch (_) {}
                  }

                  function tick() {
                    if (window.__ggqExp39LoginDelivery !== state ||
                        state.cancelled || state.acked) return;

                    if (window.__ggqLoginSuccessToken === state.token) {
                      acknowledgeSuccess();
                      return;
                    }

                    if (!state.dispatched &&
                        window.__ggqLoginReady === true &&
                        typeof window.ggqLoginWithOAuthToken === 'function') {
                      try { window.__ggqLoginSuccessToken = null; } catch (_) {}
                      try {
                        state.dispatched =
                          window.ggqLoginWithOAuthToken(state.token) === true;
                      } catch (_) {
                        state.dispatched = false;
                      }
                      if (state.dispatched) state.dispatchedAt = Date.now();
                    }

                    if (state.dispatched &&
                        Date.now() - state.dispatchedAt >= 45000) {
                      // The popup-owned native loop may now install one fresh
                      // transaction. Never restart an in-flight validation.
                      state.cancelled = true;
                      return;
                    }
                    window.setTimeout(tick, state.dispatched ? 250 : 100);
                  }

                  tick();
                  return 'started';
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }'''
panel = replace_function(panel, "    fun deliverLoginToken(token: String): Boolean {", delivery)

cancel = r'''    fun cancelLoginTokenDelivery(token: String) {
        val main = mainWebView.get() ?: return
        if (token.isBlank()) return
        val jsToken = JSONObject.quote(token)
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  var state = window.__ggqExp39LoginDelivery;
                  if (state && state.token === $jsToken) {
                    state.cancelled = true;
                    window.__ggqExp39LoginDelivery = null;
                  }
                })();
                """.trimIndent(),
                null,
            )
        }
    }'''
panel = replace_function(panel, "    fun cancelLoginTokenDelivery(token: String) {", cancel)

old_token_check = '''    private fun looksLikeOAuthToken(token: String): Boolean =
        token.length >= 16 && token.length <= 4096 && token.none { it.isWhitespace() }
'''
new_token_check = '''    // EXP39_TOKEN_SHAPE: the callback is trusted by host/path; do not reject a
    // real GeoGebra token merely because its server-selected length changed.
    private fun looksLikeOAuthToken(token: String): Boolean =
        token.isNotBlank() && token.length <= 4096 && token.none { it.isWhitespace() }
'''
if old_token_check not in panel:
    raise RuntimeError("exp39 OAuth token-shape anchor missing")
panel = panel.replace(old_token_check, new_token_check, 1)
panel = panel.replace(
    '"Exp38 OAuth token observed; starting delivery until SUCCESS ACK"',
    '"Exp39 OAuth token observed; direct LoginOperationW delivery armed"',
    1,
)


# ---------------------------------------------------------------------------
# 2. Right Grip: temporary GeoGebra Move tool plus synthetic drag on either
# Euclidian canvas. Release restores the exact mode captured before Grip.
# ---------------------------------------------------------------------------
move_bridge = r'''    // EXP39_GRIP_TEMPORARY_MOVE: right Grip temporarily selects Move in
    // either 2D or 3D and restores the exact prior tool on release.
    fun setGripMove(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        val jsActive = if (active) "true" else "false"
        main.post {
            main.evaluateJavascript(
                "if(window.__ggqSetGripMove){window.__ggqSetGripMove($jsActive);}",
                null,
            )
        }
        return true
    }'''
panel = replace_function(panel, "    fun setGripRotate(active: Boolean): Boolean {", move_bridge)

old_state = "          window.__ggqGripRotateActive = false;\n"
new_state = (
    "          window.__ggqGripMoveState = null;\n"
    "          window.__ggqGripMoveDispatching = false;\n"
)
if old_state not in panel:
    raise RuntimeError("exp39 grip JS state anchor missing")
panel = panel.replace(old_state, new_state, 1)

js_start = panel.find("          // EXP13_GRIP_ROTATE_BRIDGE: route hover motion")
js_end_marker = "          document.addEventListener('pointermove', updateGripRotate, true);\n"
js_end = panel.find(js_end_marker, js_start)
if js_start < 0 or js_end < 0:
    raise RuntimeError("exp39 grip rotate JS block missing")
js_end += len(js_end_marker)
move_js = r'''          // EXP39_GRIP_MOVE_DOM_DRAG: identify the smallest visible graph
          // canvas under the ray. This works for both Graphics and 3D Graphics.
          function ggqGraphCanvasAt(p) {
            var target = document.elementFromPoint(p.x, p.y);
            if (target && target.tagName &&
                target.tagName.toLowerCase() === 'canvas') return target;
            var canvases = document.querySelectorAll('canvas');
            var best = null;
            var bestArea = Number.POSITIVE_INFINITY;
            for (var i = 0; i < canvases.length; i++) {
              var candidate = canvases[i];
              var style = window.getComputedStyle(candidate);
              if (style.display === 'none' || style.visibility === 'hidden' ||
                  parseFloat(style.opacity || '1') === 0) continue;
              var r = candidate.getBoundingClientRect();
              if (r.width < 40 || r.height < 40) continue;
              if (p.x < r.left || p.x > r.right ||
                  p.y < r.top || p.y > r.bottom) continue;
              var area = r.width * r.height;
              if (area < bestArea) {
                best = candidate;
                bestArea = area;
              }
            }
            return best;
          }

          function dispatchGripMouse(type, canvas, p, buttons) {
            if (!canvas) return false;
            try {
              window.__ggqGripMoveDispatching = true;
              canvas.dispatchEvent(new MouseEvent(type, {
                bubbles: true, cancelable: true, view: window,
                clientX: p.x, clientY: p.y,
                button: 0, buttons: buttons
              }));
              return true;
            } catch (_) {
              return false;
            } finally {
              window.__ggqGripMoveDispatching = false;
            }
          }

          window.__ggqSetGripMove = function (active) {
            var state = window.__ggqGripMoveState;
            var p = window.__ggqLastPointer || { x: 1, y: 1 };
            if (active) {
              if (state) return true;
              var canvas = ggqGraphCanvasAt(p);
              if (!canvas || !window.ggbApplet ||
                  typeof window.ggbApplet.setMode !== 'function' ||
                  typeof window.ggbApplet.getMode !== 'function') return false;
              var oldMode = Number(window.ggbApplet.getMode());
              try { window.ggbApplet.setMode(0); } catch (_) { return false; }
              state = { canvas: canvas, oldMode: oldMode };
              window.__ggqGripMoveState = state;
              return dispatchGripMouse('mousedown', canvas, p, 1);
            }

            if (!state) return false;
            dispatchGripMouse('mouseup', state.canvas, p, 0);
            try {
              if (isFinite(state.oldMode)) {
                window.ggbApplet.setMode(state.oldMode);
              }
            } catch (_) {}
            window.__ggqGripMoveState = null;
            return true;
          };

          function updateGripMove(event) {
            if (window.__ggqGripMoveDispatching || !window.__ggqGripMoveState) return;
            setPointer(event.clientX, event.clientY);
            var p = window.__ggqLastPointer;
            dispatchGripMouse(
              'mousemove', window.__ggqGripMoveState.canvas, p, 1
            );
          }
          document.addEventListener('pointermove', updateGripMove, true);
'''
panel = panel[:js_start] + move_js + panel[js_end:]


# ---------------------------------------------------------------------------
# 3. Right thumb: wheel the graph canvas under the ray in 2D or 3D.
# ---------------------------------------------------------------------------
zoom = r'''    // EXP39_RIGHT_THUMB_2D_3D_ZOOM: deterministic wheel zoom on the
    // graph canvas under the ray, regardless of 2D/3D view type.
    fun zoomEuclidianFromRightThumb(zoomIn: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        val delta = if (zoomIn) -96 else 96
        main.post {
            main.evaluateJavascript(
                """
                (function () {
                  try {
                    var p = window.__ggqLastPointer || {
                      x: Math.max(1, Math.round(window.innerWidth / 2)),
                      y: Math.max(1, Math.round(window.innerHeight / 2))
                    };
                    var target = null;
                    var direct = document.elementFromPoint(p.x, p.y);
                    if (direct && direct.tagName &&
                        direct.tagName.toLowerCase() === 'canvas') target = direct;
                    if (!target) {
                      var canvases = document.querySelectorAll('canvas');
                      var bestArea = Number.POSITIVE_INFINITY;
                      for (var i = 0; i < canvases.length; i++) {
                        var candidate = canvases[i];
                        var style = window.getComputedStyle(candidate);
                        if (style.display === 'none' || style.visibility === 'hidden' ||
                            parseFloat(style.opacity || '1') === 0) continue;
                        var r = candidate.getBoundingClientRect();
                        if (r.width < 40 || r.height < 40) continue;
                        if (p.x < r.left || p.x > r.right ||
                            p.y < r.top || p.y > r.bottom) continue;
                        var area = r.width * r.height;
                        if (area < bestArea) {
                          target = candidate;
                          bestArea = area;
                        }
                      }
                    }
                    if (!target) return false;
                    target.dispatchEvent(new WheelEvent('wheel', {
                      bubbles: true, cancelable: true,
                      clientX: p.x, clientY: p.y,
                      deltaY: $delta, deltaMode: 0
                    }));
                    return true;
                  } catch (_) {
                    return false;
                  }
                })();
                """.trimIndent(),
                null,
            )
        }
        return true
    }'''
panel = replace_function(panel, "    fun zoom3DFromRightThumb(zoomIn: Boolean): Boolean {", zoom)


# Activity bridge names and behavior.
old_activity = '''    // EXP14_RUNTIME_HOTFIX: keep Grip bridge, but never look up GrabbableSystem in onVRReady.
    // EXP13_RIGHT_GRIP_ROTATE: momentary rotate modifier; release restores the old tool natively.
    internal fun onQuestGripRotatePressed(): Boolean =
        GeoGebraWebNavigation.setGripRotate(true)

    internal fun onQuestGripRotateReleased() {
        GeoGebraWebNavigation.setGripRotate(false)
    }


    // EXP35_RIGHT_THUMB_ZOOM_ACTIVITY
    internal fun onQuestRightThumbZoom(zoomIn: Boolean) {
        GeoGebraWebNavigation.zoom3DFromRightThumb(zoomIn)
    }
'''
new_activity = '''    // EXP39_RIGHT_GRIP_TEMPORARY_MOVE: Move is active only while Grip is held;
    // release restores the exact tool selected before the press.
    internal fun onQuestGripMovePressed(): Boolean =
        GeoGebraWebNavigation.setGripMove(true)

    internal fun onQuestGripMoveReleased() {
        GeoGebraWebNavigation.setGripMove(false)
    }

    // EXP39_RIGHT_THUMB_2D_3D_ZOOM_ACTIVITY
    internal fun onQuestRightThumbZoom(zoomIn: Boolean) {
        GeoGebraWebNavigation.zoomEuclidianFromRightThumb(zoomIn)
    }
'''
if old_activity not in activity:
    raise RuntimeError("exp39 Activity Grip/zoom block missing")
activity = activity.replace(old_activity, new_activity, 1)


# Controller button routing: no stereo-hole gate for Move or zoom.
shortcut = shortcut.replace(
    "    private var rightGripRotateActive = false\n",
    "    private var rightGripMoveActive = false\n",
    1,
)
old_grip = '''            if (controller.isPressed(ButtonBits.ButtonSqueezeR)) {
                if (DepthPointerState.active && !rightGripRotateActive) {
                    rightGripRotateActive = activity.onQuestGripRotatePressed()
                }
            }

            if (
                rightGripRotateActive &&
                controller.isReleased(ButtonBits.ButtonSqueezeR)
            ) {
                activity.onQuestGripRotateReleased()
                rightGripRotateActive = false
            }
'''
new_grip = '''            // EXP39_RIGHT_GRIP_GLOBAL_MOVE: allow either 2D or 3D graph.
            if (controller.isPressed(ButtonBits.ButtonSqueezeR)) {
                if (!rightGripMoveActive) {
                    rightGripMoveActive = activity.onQuestGripMovePressed()
                }
            }

            if (
                rightGripMoveActive &&
                controller.isReleased(ButtonBits.ButtonSqueezeR)
            ) {
                activity.onQuestGripMoveReleased()
                rightGripMoveActive = false
            }
'''
if old_grip not in shortcut:
    raise RuntimeError("exp39 shortcut Grip block missing")
shortcut = shortcut.replace(old_grip, new_grip, 1)
shortcut = shortcut.replace(
    "            // right-thumb directional bits, but only while the ray is in the live\n"
    "            // 3D hole. Holding the stick repeats smoothly at a bounded cadence.\n",
    "            // right-thumb directional bits over either 2D or 3D Graphics.\n"
    "            // Holding the stick repeats smoothly at a bounded cadence.\n",
    1,
)
old_thumb_gate = "            if (thumbDirection != 0 && DepthPointerState.active) {\n"
new_thumb_gate = "            if (thumbDirection != 0) {\n"
if old_thumb_gate not in shortcut:
    raise RuntimeError("exp39 shortcut thumb 3D gate missing")
shortcut = shortcut.replace(old_thumb_gate, new_thumb_gate, 1)
shortcut = shortcut.replace(
    " * Right Grip is an exp13 momentary 3D-view rotate modifier while the pointer is over the live 3D\n"
    " * hole. Releasing Grip restores the exact GeoGebra tool that was active before the press.\n",
    " * Right Grip is an Exp39 temporary Move drag over either 2D or 3D Graphics.\n"
    " * Releasing Grip restores the exact GeoGebra tool active before the press.\n",
    1,
)


# Duplicate Meta Scroll suppression now follows our explicit thumb handling in
# either graph view; it is no longer tied to the stereo depth-pointer flag.
thumb = thumb.replace(
    " * right-thumb UP/DOWN is being handled explicitly as GeoGebra 3D zoom.\n",
    " * right-thumb UP/DOWN is handled explicitly as GeoGebra 2D/3D zoom.\n",
    1,
)
old_should = '''    fun shouldConsumePanelScroll(): Boolean =
        DepthPointerState.active &&
            SystemClock.elapsedRealtime() <= suppressPanelScrollUntilMs
'''
new_should = '''    fun shouldConsumePanelScroll(): Boolean =
        SystemClock.elapsedRealtime() <= suppressPanelScrollUntilMs
'''
if old_should not in thumb:
    raise RuntimeError("exp39 thumb suppression gate missing")
thumb = thumb.replace(old_should, new_should, 1)


for required in (
    "EXP39_DIRECT_LOGIN_OPERATION",
    "window.ggqLoginWithOAuthToken(state.token)",
    "Date.now() - state.dispatchedAt >= 45000",
    "EXP39_TOKEN_SHAPE",
    "EXP39_GRIP_TEMPORARY_MOVE",
    "EXP39_GRIP_MOVE_DOM_DRAG",
    "window.ggbApplet.setMode(0)",
    "window.ggbApplet.setMode(state.oldMode)",
    "EXP39_RIGHT_THUMB_2D_3D_ZOOM",
    "EXP38_LIFETIME_OAUTH_PROBE",
    "EXP34_NO_SSID_AUTH",
    "EXP35_LOGIN_IME_NEXT_GUARD",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in panel:
        raise RuntimeError(f"exp39 final panel requirement missing: {required}")

for forbidden in (
    "__ggqExp38LoginDelivery",
    "state.nextDispatchAt = now + 8000",
    "setGripRotate(",
    "__ggqSetGripRotate",
    "zoom3DFromRightThumb",
    "deliverLoginCookie(",
    'put("action", "logincookie")',
):
    if forbidden in panel:
        raise RuntimeError(f"exp39 forbidden panel residue: {forbidden}")

for required in (
    "EXP39_RIGHT_GRIP_TEMPORARY_MOVE",
    "onQuestGripMovePressed",
    "onQuestGripMoveReleased",
    "zoomEuclidianFromRightThumb",
):
    if required not in activity:
        raise RuntimeError(f"exp39 Activity requirement missing: {required}")

for required in (
    "EXP39_RIGHT_GRIP_GLOBAL_MOVE",
    "rightGripMoveActive",
    "activity.onQuestGripMovePressed()",
    "if (thumbDirection != 0)",
):
    if required not in shortcut:
        raise RuntimeError(f"exp39 shortcut requirement missing: {required}")

for forbidden in (
    "rightGripRotateActive",
    "onQuestGripRotate",
    "thumbDirection != 0 && DepthPointerState.active",
):
    if forbidden in shortcut:
        raise RuntimeError(f"exp39 forbidden shortcut residue: {forbidden}")

if "DepthPointerState.active &&" in thumb:
    raise RuntimeError("exp39 thumb suppression still 3D-only")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")
thumb_path.write_text(thumb, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "login_transport=exp39 direct LoginOperationW OAuth call; one validation "
        "per 45-second ACK transaction; no repeated MessageEvent restart\n"
        "right_grip=exp39 temporary Move mode and DOM drag in 2D/3D; exact prior "
        "tool restored on release\n"
        "right_thumb_zoom=exp39 explicit graph-canvas wheel zoom in both 2D/3D\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp39 direct login + temporary Move + 2D/3D thumb zoom installed")
