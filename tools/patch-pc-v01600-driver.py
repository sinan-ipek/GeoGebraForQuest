#!/usr/bin/env python3
"""GeoGebraForQuest PC v0.16.0 integration driver.

Runs on top of the proven v0.14.1 GPU metadata/XR plumbing, but does NOT apply
v0.14.2's old full-SBS host state machine. Instead it ports only the safety
contracts that still matter to the new v0.16 two-paint eye-pair architecture:

* pause GPU stereo capture while native/popup/auth UI is active,
* immediately mark GPU-B inactive on stereo/UI suspension,
* never publish B until a clean A GPU publication succeeded,
* preserve popup-first accelerated-paint ordering,
* keep the Quest virtual keyboard disabled,
* forward the stage-hidden acknowledgement to the new host state machine.

Then it executes the complete v0.16 transport patch and adds the small host/UI
helpers required by MainFormV11.InputStereo.cs.
"""

from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# A) Prepare the v0.14.1 JS runtime for the v0.16 replacement.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

field = '  var gpuStageLayout = null;\n'
req(s, field, 'v0.16 driver: gpu stage field marker missing')
if '  var gpuExternallySuspended = false;\n' not in s:
    s = s.replace(
        field,
        field +
        '  var gpuExternallySuspended = false;\n'
        '  var gpuReleaseOk = false;\n',
        1,
    )

loop = '''  function captureLoop(now) {
    if (gpuInFlight) {'''
req(s, loop, 'v0.16 driver: captureLoop marker missing')
if '    if (gpuExternallySuspended) {' not in s:
    s = s.replace(
        loop,
        '''  function captureLoop(now) {
    if (gpuExternallySuspended) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (gpuInFlight) {''',
        1,
    )
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# B) Add stage-hidden bridge/switch and disable the Quest virtual keyboard.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
main = p.read_text(encoding='utf-8')

bridge_marker = '''                gpuStereoStagePresented: function (payload) {
                  post({ type: 'gpuStereoStagePresented', payload: String(payload || '') });
                },'''
req(main, bridge_marker, 'v0.16 driver: gpuStereoStagePresented bridge missing')
if 'gpuStereoStageHidden: function (payload)' not in main:
    main = main.replace(
        bridge_marker,
        bridge_marker + '''
                gpuStereoStageHidden: function (payload) {
                  post({ type: 'gpuStereoStageHidden', payload: String(payload || '') });
                },''',
        1,
    )

switch_marker = '''                case "gpuStereoStagePresented":
                    HandleGpuStereoV141StagePresented(root);
                    break;'''
req(main, switch_marker, 'v0.16 driver: gpuStereoStagePresented switch missing')
if 'case "gpuStereoStageHidden":' not in main:
    main = main.replace(
        switch_marker,
        switch_marker + '''
                case "gpuStereoStageHidden":
                    HandleGpuStereoV141StageHidden(root);
                    break;''',
        1,
    )

keyboard_marker = '              window.__ggqVrKeyboardInstalled = true;\n'
req(main, keyboard_marker, 'v0.16 driver: Quest keyboard install marker missing')
if 'Quest virtual keyboard disabled' not in main:
    main = main.replace(
        keyboard_marker,
        keyboard_marker +
        "              try { var oldKeyboard=document.getElementById('ggq-vr-keyboard'); if(oldKeyboard) oldKeyboard.remove(); } catch (_) {}\n"
        "              return; // v0.16.0: Quest virtual keyboard disabled; use the physical PC keyboard.\n",
        1,
    )
p.write_text(main, encoding='utf-8')


# ---------------------------------------------------------------------------
# C) Make the accelerated A path report whether clean A was really published.
#    Do this structurally so generated formatting changes do not matter.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.Graphics.cs')
g = p.read_text(encoding='utf-8')
req(g, 'TryConsumeGpuStereoV141PaintLocked(cefTexture)',
    'v0.16 driver: GPU stereo paint hook missing')

paint_start = g.find('    public void OnAcceleratedPaint(')
paint_end = g.find('\n    private void EnsurePcTextureLocked', paint_start)
if paint_start < 0 or paint_end < 0:
    raise SystemExit('v0.16 driver: OnAcceleratedPaint boundaries missing')
paint = g[paint_start:paint_end]

if 'var aGpuPublishedV142 = false;' not in paint:
    target_re = re.compile(
        r'(?P<indent>^[ \t]*)var target = _pcTextures\[next\];\s*\n'
        r'(?P=indent)if \(target is null\) return;',
        re.MULTILINE,
    )
    m = target_re.search(paint)
    if not m:
        raise SystemExit('v0.16 driver: A target allocation block missing')
    indent = m.group('indent')
    replacement = m.group(0) + '\n' + indent + 'var aGpuPublishedV142 = false;'
    paint = paint[:m.start()] + replacement + paint[m.end():]

if 'aGpuPublishedV142 = true;' not in paint:
    m = re.search(
        r'(?P<indent>^[ \t]*)CompleteGpuPublishLocked\((?P<args>.*?)\);',
        paint,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise SystemExit('v0.16 driver: A GPU publish completion call missing')
    indent = m.group('indent')
    replacement = m.group(0) + '\n' + indent + 'aGpuPublishedV142 = true;'
    paint = paint[:m.start()] + replacement + paint[m.end():]

if 'CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142);' not in paint:
    frame = re.search(
        r'(?P<indent>^[ \t]*)var frame = Interlocked\.Increment\(ref _gpuFrameNumber\);',
        paint,
        re.MULTILINE,
    )
    if not frame:
        raise SystemExit('v0.16 driver: A frame publication marker missing')
    indent = frame.group('indent')
    replacement = (
        indent + 'CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142);\n' +
        frame.group(0)
    )
    paint = paint[:frame.start()] + replacement + paint[frame.end():]

g = g[:paint_start] + paint + g[paint_end:]

popup_pos = g.find('PaintElementType.Popup')
hook_pos = g.find('TryConsumeGpuStereoV141PaintLocked(cefTexture)')
if popup_pos < 0 or hook_pos < 0 or popup_pos > hook_pos:
    raise SystemExit('v0.16 driver: popup-first accelerated-paint ordering lost')
p.write_text(g, encoding='utf-8')


# ---------------------------------------------------------------------------
# D) Execute the complete v0.16 eye-pair transport patch.
# ---------------------------------------------------------------------------
transport = Path('tools/patch-pc-v01600-gpu-eye-pair.py')
code = compile(transport.read_text(encoding='utf-8'), str(transport), 'exec')
exec(code, {'__name__': '__main__'})


# ---------------------------------------------------------------------------
# E) Add v0.16-specific suspend/deactivate helpers to the newly generated host.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV141.GpuStereo.cs')
h = p.read_text(encoding='utf-8')

insert_marker = '''    private void EnsureStereoGpuPairTexturesLocked(int eyeWidth, int eyeHeight, Format format)
    {'''
req(h, insert_marker, 'v0.16 driver: host helper insertion marker missing')
if 'private void DeactivateGpuStereoV141()' not in h:
    helpers = r'''    private void DeactivateGpuStereoV141()
    {
        _stereoGpuPublisher.SetInactive();

        long serial;
        bool abort;
        lock (_d3dLock)
        {
            serial = _gpuStereoV141Serial;
            abort = _gpuStereoV141State != GpuStereoV141State.Idle && serial >= 0;
        }
        if (abort)
        {
            AbortGpuStereoV160(serial, "stereo-inactive");
        }
    }

    private void SetGpuStereoV141UiSuspended(bool suspended)
    {
        ExecuteGpuStereoV141Script(
            $"window.ggqGpuSetSuspended && window.ggqGpuSetSuspended({(suspended ? "true" : "false")});");

        if (!suspended) return;

        _stereoGpuPublisher.SetInactive();
        long serial;
        bool abort;
        lock (_d3dLock)
        {
            serial = _gpuStereoV141Serial;
            abort = _gpuStereoV141State != GpuStereoV141State.Idle && serial >= 0;
        }
        if (abort)
        {
            AbortGpuStereoV160(serial, "ui-suspended");
        }
    }

'''
    h = h.replace(insert_marker, helpers + insert_marker, 1)
p.write_text(h, encoding='utf-8')


# ---------------------------------------------------------------------------
# F) Wire normal stereo/UI lifecycle into the new GPU-B helpers.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.InputStereo.cs')
i = p.read_text(encoding='utf-8')

inactive_marker = '''        _sharedStereoFrames.SetInactive(rect, size);
    }

    private void SetStereoUiSuspended(bool suspended)'''
req(i, inactive_marker, 'v0.16 driver: SetStereoInactive marker missing')
if 'DeactivateGpuStereoV141();' not in i:
    i = i.replace(
        inactive_marker,
        '''        _sharedStereoFrames.SetInactive(rect, size);
        DeactivateGpuStereoV141();
    }

    private void SetStereoUiSuspended(bool suspended)''',
        1,
    )

suspend_marker = '''    private void SetStereoUiSuspended(bool suspended)
    {
        _stereoUiSuspended = suspended;
        if (!suspended) return;'''
req(i, suspend_marker, 'v0.16 driver: SetStereoUiSuspended marker missing')
if 'SetGpuStereoV141UiSuspended(suspended);' not in i:
    i = i.replace(
        suspend_marker,
        '''    private void SetStereoUiSuspended(bool suspended)
    {
        _stereoUiSuspended = suspended;
        SetGpuStereoV141UiSuspended(suspended);
        if (!suspended) return;''',
        1,
    )
p.write_text(i, encoding='utf-8')


# ---------------------------------------------------------------------------
# G) Final integration invariants.
# ---------------------------------------------------------------------------
runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
main = Path('pc/MainFormV11.cs').read_text(encoding='utf-8')
graphics = Path('pc/MainFormV11.Graphics.cs').read_text(encoding='utf-8')
host = Path('pc/MainFormV141.GpuStereo.cs').read_text(encoding='utf-8')
input_stereo = Path('pc/MainFormV11.InputStereo.cs').read_text(encoding='utf-8')

for text, needle in (
    (runtime, 'gpuExternallySuspended'),
    (runtime, 'window.ggqGpuResumeAfterCleanA'),
    (runtime, 'window.ggqGpuSetSuspended'),
    (runtime, "bridge('gpuStereoStageHidden'"),
    (main, 'case "gpuStereoStageHidden":'),
    (main, 'Quest virtual keyboard disabled'),
    (graphics, 'CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142)'),
    (host, 'private void DeactivateGpuStereoV141()'),
    (host, 'private void SetGpuStereoV141UiSuspended(bool suspended)'),
    (input_stereo, 'DeactivateGpuStereoV141();'),
    (input_stereo, 'SetGpuStereoV141UiSuspended(suspended);'),
):
    if needle not in text:
        raise SystemExit('v0.16 driver invariant missing: ' + needle)

for forbidden in ('getImageData(', 'readPixels(', 'stereoRawPair', 'ggqRawStereoAck', 'ggq-gpu-stereo-stage-v0141'):
    if forbidden in runtime:
        raise SystemExit('v0.16 driver forbidden runtime path remains: ' + forbidden)

print('[GGQ] v0.16.0 integration driver completed')
