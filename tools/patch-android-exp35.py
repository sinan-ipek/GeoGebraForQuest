#!/usr/bin/env python3
"""Exp35: stabilize Quest login IME flow and right-thumb 3D zoom.

Baseline deliberately preserved:
- Exp34 token-first OAuth/session ownership is unchanged.
- Exp25 MAIN/popup navigation guard is unchanged.
- Exp27 local-file/XR cold-process handoff is unchanged.

Changes:
1) Login IME guard
   On accounts.geogebra.org, Enter/Next from an email/username field must never
   submit a password-empty form. A capture-phase key/submit guard moves focus to
   the password field and sets enterkeyhint=next/go for Quest's IME.

2) Deterministic right-thumb zoom
   Right thumbstick UP/DOWN is read directly from ButtonBits.ButtonThumbRU/RD.
   While the depth pointer is inside the live 3D hole, UP emits one controlled
   GeoGebra wheel step for zoom-in and DOWN emits one controlled wheel step for
   zoom-out, with repeat throttling while held.

   Meta/ISDK also emits panel Scroll for thumbstick motion. During a native
   thumb-zoom burst only, the WebView consumes that duplicate ACTION_SCROLL so
   the same thumb motion cannot sometimes zoom through Meta and sometimes through
   our explicit bridge. Physical mouse wheel remains untouched outside that short
   suppression window.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp35.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
activity_path = root / "app/src/main/java/com/sinan/geogebraforquest/SpatialGeoGebraActivity.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
thumb_state_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestThumbZoomState.kt"

panel = panel_path.read_text(encoding="utf-8")
activity = activity_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")

for required in (
    "EXP34_TOKEN_FIRST_SESSION_OWNER",
    "EXP34_NO_SSID_AUTH",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
    "EXP13_GRIP_ROTATE_BRIDGE",
):
    if required not in panel:
        raise RuntimeError(f"exp35 panel baseline requirement missing: {required}")

for required in (
    "ButtonBits.ButtonSqueezeR",
    "ButtonBits.ButtonA",
    "ButtonBits.ButtonB",
):
    if required not in shortcut:
        raise RuntimeError(f"exp35 shortcut baseline requirement missing: {required}")

# ---------------------------------------------------------------------------
# 1. Login IME guard: email Enter/Next -> password, never blank-password submit.
# ---------------------------------------------------------------------------
if "EXP35_LOGIN_IME_NEXT_GUARD" not in panel:
    anchor = "private fun refreshImeConnection(view: View) {\n"
    helper = r'''// EXP35_LOGIN_IME_NEXT_GUARD: Quest's IME can treat Enter/Next on the
// GeoGebra account email field as a submit/dismiss action instead of moving to
// the password field. Install a capture-phase guard only on accounts.geogebra.org.
private fun installExp35LoginImeGuard(view: WebView) {
    val uri = try { Uri.parse(view.url.orEmpty()) } catch (_: Throwable) { return }
    if (!uri.host.equals("accounts.geogebra.org", ignoreCase = true)) return

    view.evaluateJavascript(
        """
        (function () {
          if (window.__ggqExp35LoginImeGuardInstalled) return 'installed';
          window.__ggqExp35LoginImeGuardInstalled = true;

          function lower(value) {
            return String(value || '').toLowerCase();
          }

          function isEmailOrUser(input) {
            if (!input || !input.tagName || lower(input.tagName) !== 'input') return false;
            var type = lower(input.type);
            var hints = [input.name, input.id, input.autocomplete, input.placeholder,
                         input.getAttribute && input.getAttribute('aria-label')]
                         .map(lower).join(' ');
            return type === 'email' || hints.indexOf('email') >= 0 ||
                   hints.indexOf('e-mail') >= 0 || hints.indexOf('username') >= 0 ||
                   hints.indexOf('user name') >= 0 || hints.indexOf('benutzer') >= 0;
          }

          function passwordInput() {
            return document.querySelector(
              'input[type="password"],input[autocomplete="current-password"],'+
              'input[name*="pass" i],input[id*="pass" i]'
            );
          }

          function prepareHints() {
            var inputs = document.querySelectorAll('input');
            var password = passwordInput();
            for (var i = 0; i < inputs.length; i++) {
              if (isEmailOrUser(inputs[i])) {
                try { inputs[i].setAttribute('enterkeyhint', 'next'); } catch (_) {}
              }
            }
            if (password) {
              try { password.setAttribute('enterkeyhint', 'go'); } catch (_) {}
            }
          }

          function focusPassword() {
            var password = passwordInput();
            if (!password) return false;
            try {
              password.focus({preventScroll:false});
            } catch (_) {
              try { password.focus(); } catch (_) {}
            }
            try { password.click(); } catch (_) {}
            return document.activeElement === password || true;
          }

          document.addEventListener('keydown', function (event) {
            if ((event.key !== 'Enter' && event.keyCode !== 13) ||
                !isEmailOrUser(event.target)) return;
            var password = passwordInput();
            if (!password || String(password.value || '').length !== 0) return;
            event.preventDefault();
            event.stopPropagation();
            if (event.stopImmediatePropagation) event.stopImmediatePropagation();
            setTimeout(focusPassword, 0);
          }, true);

          document.addEventListener('submit', function (event) {
            var password = passwordInput();
            if (!password || String(password.value || '').length !== 0) return;
            var active = document.activeElement;
            var email = document.querySelector('input[type="email"]');
            if (!isEmailOrUser(active) && !(email && String(email.value || '').length > 0)) {
              return;
            }
            event.preventDefault();
            event.stopPropagation();
            if (event.stopImmediatePropagation) event.stopImmediatePropagation();
            setTimeout(focusPassword, 0);
          }, true);

          prepareHints();
          try {
            new MutationObserver(prepareHints).observe(document.documentElement || document.body, {
              childList: true, subtree: true, attributes: true,
              attributeFilter: ['type','name','id','autocomplete','placeholder']
            });
          } catch (_) {}
          return 'ready';
        })();
        """.trimIndent(),
        null,
    )
}

''' + anchor
    if anchor not in panel:
        raise RuntimeError("exp35 refreshImeConnection anchor not found")
    panel = panel.replace(anchor, helper, 1)

    page_anchor = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
'''
    page_insert = '''            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                if (!registerAsMain) {
                    installExp35LoginImeGuard(view)
                }
'''
    if page_anchor not in panel:
        raise RuntimeError("exp35 onPageFinished anchor not found")
    panel = panel.replace(page_anchor, page_insert, 1)

# ---------------------------------------------------------------------------
# 2. Explicit synthetic wheel bridge. Use GeoGebra's own 3D wheel handler.
# ---------------------------------------------------------------------------
if "EXP35_RIGHT_THUMB_ZOOM_BRIDGE" not in panel:
    grip_anchor = '''    // EXP13_GRIP_ROTATE_BRIDGE: right Grip is a momentary modifier, not a permanent tool change.
    fun setGripRotate(active: Boolean): Boolean {
        val main = mainWebView.get() ?: return false
        val jsActive = if (active) "true" else "false"
        main.post {
            main.evaluateJavascript(
                "if(window.__ggqSetGripRotate){window.__ggqSetGripRotate($jsActive);}",
                null,
            )
        }
        return true
    }
'''
    zoom_bridge = grip_anchor + r'''

    // EXP35_RIGHT_THUMB_ZOOM_BRIDGE: deterministic one-step 3D zoom. Negative
    // wheel delta is zoom-in; positive delta is zoom-out in GeoGebra Web.
    fun zoom3DFromRightThumb(zoomIn: Boolean): Boolean {
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
                    var target = document.elementFromPoint(p.x, p.y) || document.body;
                    var event = new WheelEvent('wheel', {
                      bubbles: true,
                      cancelable: true,
                      clientX: p.x,
                      clientY: p.y,
                      deltaY: $delta,
                      deltaMode: 0
                    });
                    target.dispatchEvent(event);
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
    }
'''
    if grip_anchor not in panel:
        raise RuntimeError("exp35 grip bridge anchor not found")
    panel = panel.replace(grip_anchor, zoom_bridge, 1)

# Consume only duplicate Meta panel-scroll generated during our explicit thumb zoom.
if "EXP35_SUPPRESS_DUPLICATE_META_THUMB_SCROLL" not in panel:
    touch_anchor = '''        setOnTouchListener { touchedView, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                refreshImeConnection(touchedView)
            }
            false
        }

'''
    scroll_guard = touch_anchor + '''        // EXP35_SUPPRESS_DUPLICATE_META_THUMB_SCROLL: ISDK also turns right-thumb
        // motion into panel Scroll. Consume only that short duplicate window while
        // the depth pointer is over 3D; normal mouse-wheel input remains available.
        setOnGenericMotionListener { _, event ->
            event.action == MotionEvent.ACTION_SCROLL &&
                spatialMode &&
                QuestThumbZoomState.shouldConsumePanelScroll()
        }

'''
    if touch_anchor not in panel:
        raise RuntimeError("exp35 WebView touch-listener anchor not found")
    panel = panel.replace(touch_anchor, scroll_guard, 1)

# ---------------------------------------------------------------------------
# 3. Shared short suppression window for ISDK's duplicate Scroll event.
# ---------------------------------------------------------------------------
thumb_state = r'''package com.sinan.geogebraforquest

import android.os.SystemClock

/**
 * Exp35 transient state used only to suppress ISDK's duplicate panel Scroll while
 * right-thumb UP/DOWN is being handled explicitly as GeoGebra 3D zoom.
 */
object QuestThumbZoomState {
    private const val DUPLICATE_SCROLL_WINDOW_MS = 220L

    @Volatile
    private var suppressPanelScrollUntilMs = 0L

    fun noteNativeThumbZoom() {
        suppressPanelScrollUntilMs =
            SystemClock.elapsedRealtime() + DUPLICATE_SCROLL_WINDOW_MS
    }

    fun shouldConsumePanelScroll(): Boolean =
        DepthPointerState.active &&
            SystemClock.elapsedRealtime() <= suppressPanelScrollUntilMs

    fun reset() {
        suppressPanelScrollUntilMs = 0L
    }
}
'''
thumb_state_path.write_text(thumb_state, encoding="utf-8")

# ---------------------------------------------------------------------------
# 4. Controller: direct right-thumb RU/RD -> throttled explicit 3D zoom.
# ---------------------------------------------------------------------------
if "EXP35_RIGHT_THUMB_DETERMINISTIC_ZOOM" not in shortcut:
    if "import android.os.SystemClock\n" not in shortcut:
        package_anchor = "package com.sinan.geogebraforquest\n\n"
        if package_anchor not in shortcut:
            raise RuntimeError("exp35 shortcut package anchor not found")
        shortcut = shortcut.replace(
            package_anchor,
            package_anchor + "import android.os.SystemClock\n",
            1,
        )

    field_anchor = "    private var rightGripRotateActive = false\n"
    fields = field_anchor + r'''

    // EXP35_RIGHT_THUMB_DETERMINISTIC_ZOOM
    private var lastThumbZoomAtMs = 0L
    private var lastThumbZoomDirection = 0
    private val thumbZoomRepeatMs = 78L
'''
    if field_anchor not in shortcut:
        raise RuntimeError("exp35 shortcut field anchor not found")
    shortcut = shortcut.replace(field_anchor, fields, 1)

    button_anchor = '''            if (isButtonDown(controller, ButtonBits.ButtonA)) {
                activity.onQuestAButtonPressed()
            }
'''
    thumb_logic = r'''            // EXP35_RIGHT_THUMB_DETERMINISTIC_ZOOM: use the SDK's explicit
            // right-thumb directional bits, but only while the ray is in the live
            // 3D hole. Holding the stick repeats smoothly at a bounded cadence.
            val thumbDirection = when {
                controller.buttonState.and(ButtonBits.ButtonThumbRU) != 0 -> 1
                controller.buttonState.and(ButtonBits.ButtonThumbRD) != 0 -> -1
                else -> 0
            }
            if (thumbDirection != 0 && DepthPointerState.active) {
                QuestThumbZoomState.noteNativeThumbZoom()
                val now = SystemClock.elapsedRealtime()
                if (
                    thumbDirection != lastThumbZoomDirection ||
                    now - lastThumbZoomAtMs >= thumbZoomRepeatMs
                ) {
                    activity.onQuestRightThumbZoom(zoomIn = thumbDirection > 0)
                    lastThumbZoomAtMs = now
                }
            }
            if (thumbDirection == 0) {
                lastThumbZoomDirection = 0
            } else {
                lastThumbZoomDirection = thumbDirection
            }

''' + button_anchor
    if button_anchor not in shortcut:
        raise RuntimeError("exp35 shortcut A-button anchor not found")
    shortcut = shortcut.replace(button_anchor, thumb_logic, 1)

# ---------------------------------------------------------------------------
# 5. Activity: reset transient state and expose one explicit zoom command.
# ---------------------------------------------------------------------------
if "EXP35_RIGHT_THUMB_ZOOM_ACTIVITY" not in activity:
    reset_anchor = '''        StereoDebugState.reset()
        DepthPointerState.reset()
'''
    reset_replacement = '''        StereoDebugState.reset()
        DepthPointerState.reset()
        QuestThumbZoomState.reset()
'''
    if reset_anchor not in activity:
        raise RuntimeError("exp35 activity reset anchor not found")
    activity = activity.replace(reset_anchor, reset_replacement, 1)

    grip_action = '''    internal fun onQuestGripRotateReleased() {
        GeoGebraWebNavigation.setGripRotate(false)
    }
'''
    zoom_action = grip_action + '''

    // EXP35_RIGHT_THUMB_ZOOM_ACTIVITY
    internal fun onQuestRightThumbZoom(zoomIn: Boolean) {
        GeoGebraWebNavigation.zoom3DFromRightThumb(zoomIn)
    }
'''
    if grip_action not in activity:
        raise RuntimeError("exp35 activity grip-release anchor not found")
    activity = activity.replace(grip_action, zoom_action, 1)

# ---------------------------------------------------------------------------
# 6. Guards: auth/XR baselines frozen, new behavior present.
# ---------------------------------------------------------------------------
for required in (
    "EXP34_TOKEN_FIRST_SESSION_OWNER",
    "EXP34_NO_SSID_AUTH",
    "EXP35_LOGIN_IME_NEXT_GUARD",
    "enterkeyhint', 'next'",
    "EXP35_RIGHT_THUMB_ZOOM_BRIDGE",
    "EXP35_SUPPRESS_DUPLICATE_META_THUMB_SCROLL",
    "QuestThumbZoomState.shouldConsumePanelScroll()",
    "EXP25_STRICT_POPUP_WHITELIST",
    "EXP27_COLD_PROCESS_PICKER",
):
    if required not in panel:
        raise RuntimeError(f"exp35 final panel requirement missing: {required}")

for forbidden in (
    "deliverLoginCookie(",
    'put("action", "logincookie")',
    "EXP33_COOKIE_LOGIN_DELIVERY",
):
    if forbidden in panel:
        raise RuntimeError(f"exp35 forbidden cookie-auth residue: {forbidden}")

for required in (
    "EXP35_RIGHT_THUMB_DETERMINISTIC_ZOOM",
    "ButtonBits.ButtonThumbRU",
    "ButtonBits.ButtonThumbRD",
    "QuestThumbZoomState.noteNativeThumbZoom()",
    "activity.onQuestRightThumbZoom",
):
    if required not in shortcut:
        raise RuntimeError(f"exp35 shortcut requirement missing: {required}")

for required in (
    "EXP35_RIGHT_THUMB_ZOOM_ACTIVITY",
    "QuestThumbZoomState.reset()",
    "GeoGebraWebNavigation.zoom3DFromRightThumb(zoomIn)",
):
    if required not in activity:
        raise RuntimeError(f"exp35 activity requirement missing: {required}")

# Keep the post-Exp27 controller-repair experiments out of the active runtime.
for forbidden in (
    "requestControllerPresentationRecovery(",
    "entity.setComponent(controller)",
    "controller.laserEnabled =",
):
    if forbidden in shortcut:
        raise RuntimeError(f"exp35 controller mutation residue remains: {forbidden}")

panel_path.write_text(panel, encoding="utf-8")
activity_path.write_text(activity, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "login_ime=exp35 accounts email Enter/Next guarded until password focus; "
        "password-empty submit blocked\n"
        "right_thumb_zoom=exp35 ButtonThumbRU/RD -> explicit GeoGebra 3D wheel zoom; "
        "duplicate ISDK panel Scroll suppressed only during native thumb zoom\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp35 login IME guard + deterministic right-thumb 3D zoom installed")
