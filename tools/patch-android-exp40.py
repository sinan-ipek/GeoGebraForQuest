#!/usr/bin/env python3
"""Exp40: commit Quest IME password before submit and latch physical Grip.

The accounts page can receive IME_ACTION_GO while the password's composing text
has not yet produced blur/change.  Its submit then observes stale form state.
Exp40 owns password Enter/submit for one turn: commit composition, blur, emit
input/change, then invoke the page's real submit button after the state settles.

Spatial SDK changedButtons is an edge signal and may be consumed before this
system's tick.  Physical Grip is therefore latched from continuous isDown state
aggregated across controller entities.  Trigger remains ordinary panel click.
"""

from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: patch-android-exp40.py <repo-root>")

root = Path(sys.argv[1]).resolve()
panel_path = root / "app/src/main/java/com/sinan/geogebraforquest/GeoGebraWebPanel.kt"
shortcut_path = root / "app/src/main/java/com/sinan/geogebraforquest/QuestControllerShortcutSystem.kt"
panel = panel_path.read_text(encoding="utf-8")
shortcut = shortcut_path.read_text(encoding="utf-8")

for required in (
    "EXP39_DIRECT_LOGIN_OPERATION",
    "EXP39_GRIP_TEMPORARY_MOVE",
    "EXP39_RIGHT_THUMB_2D_3D_ZOOM",
    "EXP35_LOGIN_IME_NEXT_GUARD",
):
    if required not in panel:
        raise RuntimeError(f"exp40 panel baseline missing: {required}")

# Password Enter is not a reliable direct submit on Quest.  It must first end
# IME composition and blur so the account page's controlled state is current.
old_hint = "try { password.setAttribute('enterkeyhint', 'go'); } catch (_) {}"
new_hint = "try { password.setAttribute('enterkeyhint', 'done'); } catch (_) {}"
if old_hint not in panel:
    raise RuntimeError("exp40 password enterkeyhint anchor missing")
panel = panel.replace(old_hint, new_hint, 1)

submit_anchor = """          document.addEventListener('submit', function (event) {
            var password = passwordInput();
            if (!password || String(password.value || '').length !== 0) return;
"""
ime_fix = r'''          // EXP40_PASSWORD_IME_COMMIT: Quest may submit before the final
          // composing password has reached the account page's controlled state.
          var exp40Submitting = false;

          function commitPasswordAndSubmit(password) {
            if (!password || exp40Submitting) return;
            exp40Submitting = true;
            try {
              password.dispatchEvent(new CompositionEvent('compositionend', {
                bubbles: true, cancelable: false, data: String(password.value || '')
              }));
            } catch (_) {}
            try { password.dispatchEvent(new Event('input', {bubbles:true})); } catch (_) {}
            try { password.dispatchEvent(new Event('change', {bubbles:true})); } catch (_) {}
            try { password.blur(); } catch (_) {}
            try {
              var sink = document.querySelector('form') || document.body;
              if (sink && typeof sink.focus === 'function') {
                if (!sink.hasAttribute('tabindex')) sink.setAttribute('tabindex', '-1');
                sink.focus({preventScroll:true});
              }
            } catch (_) {}

            window.setTimeout(function () {
              try {
                var form = password.form || password.closest('form');
                var button = form && form.querySelector(
                  'button[type="submit"],input[type="submit"],button:not([type])'
                );
                window.__ggqExp40SubmitBypass = true;
                if (button && !button.disabled) {
                  button.click();
                } else if (form && typeof form.requestSubmit === 'function') {
                  form.requestSubmit();
                } else if (form) {
                  form.submit();
                }
              } finally {
                window.setTimeout(function () {
                  window.__ggqExp40SubmitBypass = false;
                  exp40Submitting = false;
                }, 500);
              }
            }, 160);
          }

          document.addEventListener('keydown', function (event) {
            if ((event.key !== 'Enter' && event.keyCode !== 13) ||
                event.target !== passwordInput()) return;
            event.preventDefault();
            event.stopPropagation();
            if (event.stopImmediatePropagation) event.stopImmediatePropagation();
            commitPasswordAndSubmit(event.target);
          }, true);

          document.addEventListener('submit', function (event) {
            if (window.__ggqExp40SubmitBypass) return;
            var password = passwordInput();
            if (!password || String(password.value || '').length === 0 ||
                document.activeElement !== password) return;
            event.preventDefault();
            event.stopPropagation();
            if (event.stopImmediatePropagation) event.stopImmediatePropagation();
            commitPasswordAndSubmit(password);
          }, true);

''' + submit_anchor
if submit_anchor not in panel:
    raise RuntimeError("exp40 blank-password submit anchor missing")
panel = panel.replace(submit_anchor, ime_fix, 1)

# Aggregate continuous Grip state across controller entities.  This avoids a
# missed one-frame edge and avoids one idle controller releasing the other.
loop_anchor = """        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }

        for (entity in controllers) {
"""
loop_replacement = """        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        var physicalGripDown = false

        for (entity in controllers) {
"""
if loop_anchor not in shortcut:
    raise RuntimeError("exp40 controller loop anchor missing")
shortcut = shortcut.replace(loop_anchor, loop_replacement, 1)

old_grip = """            // EXP39_RIGHT_GRIP_GLOBAL_MOVE: allow either 2D or 3D graph.
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

"""
new_grip = """            // EXP40_PHYSICAL_GRIP_LATCH: continuous side-Grip state.  Do not
            // alias Trigger; it remains the normal panel pointer click.
            physicalGripDown = physicalGripDown ||
                controller.isDown(ButtonBits.ButtonSqueezeR) ||
                controller.isDown(ButtonBits.ButtonSqueezeL)

"""
if old_grip not in shortcut:
    raise RuntimeError("exp40 Exp39 Grip edge block missing")
shortcut = shortcut.replace(old_grip, new_grip, 1)

method_end_anchor = """        }
    }

    private fun isButtonDown(controller: Controller, buttonMask: Int): Boolean {
"""
latched_action = """        }

        if (physicalGripDown && !rightGripMoveActive) {
            rightGripMoveActive = activity.onQuestGripMovePressed()
        } else if (!physicalGripDown && rightGripMoveActive) {
            activity.onQuestGripMoveReleased()
            rightGripMoveActive = false
        }
    }

    private fun isButtonDown(controller: Controller, buttonMask: Int): Boolean {
"""
if method_end_anchor not in shortcut:
    raise RuntimeError("exp40 controller execute-end anchor missing")
shortcut = shortcut.replace(method_end_anchor, latched_action, 1)

for required in (
    "EXP40_PASSWORD_IME_COMMIT",
    "enterkeyhint', 'done'",
    "commitPasswordAndSubmit",
    "window.__ggqExp40SubmitBypass",
):
    if required not in panel:
        raise RuntimeError(f"exp40 final panel requirement missing: {required}")

for required in (
    "EXP40_PHYSICAL_GRIP_LATCH",
    "controller.isDown(ButtonBits.ButtonSqueezeR)",
    "controller.isDown(ButtonBits.ButtonSqueezeL)",
    "if (physicalGripDown && !rightGripMoveActive)",
):
    if required not in shortcut:
        raise RuntimeError(f"exp40 shortcut requirement missing: {required}")

for forbidden in (
    "controller.isPressed(ButtonBits.ButtonSqueezeR)",
    "controller.isReleased(ButtonBits.ButtonSqueezeR)",
):
    if forbidden in shortcut:
        raise RuntimeError(f"exp40 forbidden Grip edge remains: {forbidden}")

panel_path.write_text(panel, encoding="utf-8")
shortcut_path.write_text(shortcut, encoding="utf-8")

meta = root / "app/src/main/assets/web/GeoGebra/GGQ_SOURCE_BUILD.txt"
if meta.exists():
    value = meta.read_text(encoding="utf-8")
    value += (
        "login_ime=exp40 password composition committed, blurred, then real form submit\n"
        "right_grip=exp40 continuous physical squeeze latch; Trigger remains panel click\n"
    )
    meta.write_text(value, encoding="utf-8")

print("[GGQ] exp40 password IME commit + physical Grip latch installed")
