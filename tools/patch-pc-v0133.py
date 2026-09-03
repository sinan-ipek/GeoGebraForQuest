from pathlib import Path
import re


def must_replace(path, old, new, count=1):
    p = Path(path)
    t = p.read_text(encoding='utf-8')
    n = t.count(old)
    if n != count:
        raise SystemExit(f'{path}: expected {count} occurrences, got {n}: {old[:100]!r}')
    p.write_text(t.replace(old, new), encoding='utf-8')

# ---------------------------------------------------------------------------
# 1. Slightly lower final XR resolution and make UI physically easier to read.
# ---------------------------------------------------------------------------
must_replace('pc-xr/main-v13fixed.cpp',
             'constexpr float kRenderQualityScale = 1.08f;',
             'constexpr float kRenderQualityScale = 1.00f;')
must_replace('pc-xr/main-v13fixed.cpp',
             'v0.13.2 eye target = OpenXR recommended x1.08, clamped to Quest3 physical/runtime max',
             'v0.13.3 eye target = OpenXR recommended x1.00, clamped to Quest3 physical/runtime max')

p = Path('pc-xr/v11-shared.hpp')
t = p.read_text(encoding='utf-8')
t = t.replace('constexpr float kScreenWidthMeters = 2.05f;',
              'constexpr float kScreenWidthMeters = 2.15f;', 1)
t = t.replace('constexpr float kScreenHeightMeters = 1.155f;',
              'constexpr float kScreenHeightMeters = 1.210f;', 1)
# v2 input protocol; same 64-byte mapping, new name prevents stale v1 readers.
t = t.replace('GeoGebraForQuestPC_Input_v1', 'GeoGebraForQuestPC_Input_v2')
t = t.replace('constexpr std::int32_t kInputProtocolVersion = 1;',
              'constexpr std::int32_t kInputProtocolVersion = 2;', 1)

# Shared GPU texture must be reopenable after headset visibility/focus transitions.
needle = '''    void Initialize(ID3D11Device* device) {\n        D3D11_QUERY_DESC queryDesc{};\n        queryDesc.Query = D3D11_QUERY_EVENT;\n        CheckHr(device->CreateQuery(&queryDesc, &copyQuery_), "CreateQuery(A GPU copy)");\n    }'''
replacement = needle + '''\n\n    void ResetSharedResources() {\n        sharedMutex_.Reset();\n        sharedTexture_.Reset();\n        localSrv_.Reset();\n        localTexture_.Reset();\n        currentHandle_ = nullptr;\n        localWidth_ = 0;\n        localHeight_ = 0;\n        localFormat_ = DXGI_FORMAT_UNKNOWN;\n    }'''
if needle not in t: raise SystemExit('SharedGpuTextureConsumer Initialize block missing')
t = t.replace(needle, replacement, 1)

old_writer = '''    void Publish(bool valid, float u, float v, bool triggerDown) {\n        if (!view_) {\n            return;\n        }\n        sequence_ += 2;\n        WriteI64(view_, 8, sequence_ - 1);\n        WriteI32(view_, 16, valid ? 1 : 0);\n        WriteF32(view_, 20, u);\n        WriteF32(view_, 24, v);\n        WriteI32(view_, 28, triggerDown ? 1 : 0);\n        MemoryBarrier();\n        WriteI64(view_, 8, sequence_);\n    }'''
new_writer = '''    void Publish(\n        bool valid, float u, float v, bool triggerDown,\n        bool aDown = false, bool gripDown = false,\n        float stickX = 0.0f, float stickY = 0.0f) {\n        if (!view_) return;\n        sequence_ += 2;\n        WriteI64(view_, 8, sequence_ - 1);\n        WriteI32(view_, 16, valid ? 1 : 0);\n        WriteF32(view_, 20, u);\n        WriteF32(view_, 24, v);\n        WriteI32(view_, 28, triggerDown ? 1 : 0);\n        WriteI32(view_, 32, aDown ? 1 : 0);\n        WriteI32(view_, 36, gripDown ? 1 : 0);\n        WriteF32(view_, 40, stickX);\n        WriteF32(view_, 44, stickY);\n        MemoryBarrier();\n        WriteI64(view_, 8, sequence_);\n    }'''
if old_writer not in t: raise SystemExit('XrInputWriter Publish block missing')
t = t.replace(old_writer, new_writer, 1)
# initialize extra slots
init_marker = '''        WriteI32(view_, 28, 0);\n        FlushViewOfFile(view_, kInputMappingSize);'''
t = t.replace(init_marker, '''        WriteI32(view_, 28, 0);\n        WriteI32(view_, 32, 0);\n        WriteI32(view_, 36, 0);\n        WriteF32(view_, 40, 0.0f);\n        WriteF32(view_, 44, 0.0f);\n        FlushViewOfFile(view_, kInputMappingSize);''', 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 2. OpenXR: A, grip/squeeze and thumbstick actions + focus-resume recovery.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')

fields = '''    XrAction triggerAction_{XR_NULL_HANDLE};\n    XrSpace aimSpace_{XR_NULL_HANDLE};'''
fields_new = '''    XrAction triggerAction_{XR_NULL_HANDLE};\n    XrAction aAction_{XR_NULL_HANDLE};\n    XrAction gripAction_{XR_NULL_HANDLE};\n    XrAction thumbstickAction_{XR_NULL_HANDLE};\n    XrSpace aimSpace_{XR_NULL_HANDLE};'''
if fields not in t: raise SystemExit('XR action field marker missing')
t = t.replace(fields, fields_new, 1)
t = t.replace('    bool triggerDown_{};', '''    bool triggerDown_{};\n    bool aDown_{};\n    bool gripDown_{};\n    bool wasVisibleOrFocused_{};''', 1)

# Create new actions after trigger.
after_trigger = '''        CheckXr(xrCreateAction(actionSet_, &triggerInfo, &triggerAction_),\n            "xrCreateAction(trigger)");'''
action_code = after_trigger + '''\n\n        XrActionCreateInfo aInfo{XR_TYPE_ACTION_CREATE_INFO};\n        aInfo.actionType = XR_ACTION_TYPE_BOOLEAN_INPUT;\n        std::strcpy(aInfo.actionName, "right_a");\n        std::strcpy(aInfo.localizedActionName, "Right A");\n        aInfo.countSubactionPaths = 1;\n        aInfo.subactionPaths = &rightHandPath_;\n        CheckXr(xrCreateAction(actionSet_, &aInfo, &aAction_), "xrCreateAction(A)");\n\n        XrActionCreateInfo gripInfo{XR_TYPE_ACTION_CREATE_INFO};\n        gripInfo.actionType = XR_ACTION_TYPE_FLOAT_INPUT;\n        std::strcpy(gripInfo.actionName, "right_grip");\n        std::strcpy(gripInfo.localizedActionName, "Right Grip");\n        gripInfo.countSubactionPaths = 1;\n        gripInfo.subactionPaths = &rightHandPath_;\n        CheckXr(xrCreateAction(actionSet_, &gripInfo, &gripAction_), "xrCreateAction(grip)");\n\n        XrActionCreateInfo stickInfo{XR_TYPE_ACTION_CREATE_INFO};\n        stickInfo.actionType = XR_ACTION_TYPE_VECTOR2F_INPUT;\n        std::strcpy(stickInfo.actionName, "right_thumbstick");\n        std::strcpy(stickInfo.localizedActionName, "Right Thumbstick");\n        stickInfo.countSubactionPaths = 1;\n        stickInfo.subactionPaths = &rightHandPath_;\n        CheckXr(xrCreateAction(actionSet_, &stickInfo, &thumbstickAction_),\n            "xrCreateAction(thumbstick)");'''
if after_trigger not in t: raise SystemExit('trigger action create marker missing')
t = t.replace(after_trigger, action_code, 1)

binding_marker = '''        const XrPath triggerBinding =\n            Path("/user/hand/right/input/trigger/value");\n\n        const XrActionSuggestedBinding bindings[] = {\n            {aimAction_, aimBinding},\n            {triggerAction_, triggerBinding}\n        };'''
binding_new = '''        const XrPath triggerBinding =\n            Path("/user/hand/right/input/trigger/value");\n        const XrPath aBinding =\n            Path("/user/hand/right/input/a/click");\n        const XrPath gripBinding =\n            Path("/user/hand/right/input/squeeze/value");\n        const XrPath thumbstickBinding =\n            Path("/user/hand/right/input/thumbstick");\n\n        const XrActionSuggestedBinding bindings[] = {\n            {aimAction_, aimBinding},\n            {triggerAction_, triggerBinding},\n            {aAction_, aBinding},\n            {gripAction_, gripBinding},\n            {thumbstickAction_, thumbstickBinding}\n        };'''
if binding_marker not in t: raise SystemExit('binding marker missing')
t = t.replace(binding_marker, binding_new, 1)

# Session visibility transition: reopen current shared texture on return.
state_log = '''                    Log(std::string("sessionState=") +\n                        SessionStateName(sessionState_));'''
state_new = state_log + '''\n\n                    const bool visibleNow =\n                        sessionState_ == XR_SESSION_STATE_VISIBLE ||\n                        sessionState_ == XR_SESSION_STATE_FOCUSED;\n                    if (visibleNow && !wasVisibleOrFocused_) {\n                        baseTexture_.ResetSharedResources();\n                        gpuSequence_ = 0;\n                        Log("XR became visible/focused: A texture consumer reset");\n                    }\n                    wasVisibleOrFocused_ = visibleNow;'''
if state_log not in t: raise SystemExit('session state log marker missing')
t = t.replace(state_log, state_new, 1)

# Read controller states.
trigger_read = '''        XrActionStateFloat triggerState{XR_TYPE_ACTION_STATE_FLOAT};\n        CheckXr(xrGetActionStateFloat(session_, &triggerGet, &triggerState),\n            "xrGetActionStateFloat");'''
extra_read = trigger_read + '''\n\n        XrActionStateGetInfo aGet{XR_TYPE_ACTION_STATE_GET_INFO};\n        aGet.action = aAction_;\n        aGet.subactionPath = rightHandPath_;\n        XrActionStateBoolean aState{XR_TYPE_ACTION_STATE_BOOLEAN};\n        CheckXr(xrGetActionStateBoolean(session_, &aGet, &aState),\n            "xrGetActionStateBoolean(A)");\n\n        XrActionStateGetInfo gripGet{XR_TYPE_ACTION_STATE_GET_INFO};\n        gripGet.action = gripAction_;\n        gripGet.subactionPath = rightHandPath_;\n        XrActionStateFloat gripState{XR_TYPE_ACTION_STATE_FLOAT};\n        CheckXr(xrGetActionStateFloat(session_, &gripGet, &gripState),\n            "xrGetActionStateFloat(grip)");\n\n        XrActionStateGetInfo stickGet{XR_TYPE_ACTION_STATE_GET_INFO};\n        stickGet.action = thumbstickAction_;\n        stickGet.subactionPath = rightHandPath_;\n        XrActionStateVector2f stickState{XR_TYPE_ACTION_STATE_VECTOR2F};\n        CheckXr(xrGetActionStateVector2f(session_, &stickGet, &stickState),\n            "xrGetActionStateVector2f(thumbstick)");'''
if trigger_read not in t: raise SystemExit('trigger state read missing')
t = t.replace(trigger_read, extra_read, 1)

publish_marker = '''        inputWriter_.Publish(true, u, v, triggerDown_);'''
publish_new = '''        aDown_ = aState.isActive && aState.currentState == XR_TRUE;\n        if (gripState.isActive) {\n            if (!gripDown_ && gripState.currentState >= 0.55f) gripDown_ = true;\n            else if (gripDown_ && gripState.currentState <= 0.35f) gripDown_ = false;\n        } else {\n            gripDown_ = false;\n        }\n        const float stickX = stickState.isActive ? stickState.currentState.x : 0.0f;\n        const float stickY = stickState.isActive ? stickState.currentState.y : 0.0f;\n        inputWriter_.Publish(true, u, v, triggerDown_, aDown_, gripDown_, stickX, stickY);'''
if publish_marker not in t: raise SystemExit('pointer publish marker missing')
t = t.replace(publish_marker, publish_new, 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 3. C# input protocol v2 and controller behaviors.
# ---------------------------------------------------------------------------
p = Path('pc/XrInputSharedReader.cs')
t = p.read_text(encoding='utf-8')
t = t.replace('GeoGebraForQuestPC_Input_v1', 'GeoGebraForQuestPC_Input_v2')
t = t.replace('public const int ProtocolVersion = 1;', 'public const int ProtocolVersion = 2;', 1)
old_read = '''            var trigger = _view.ReadInt32(28) != 0;'''
new_read = '''            var trigger = _view.ReadInt32(28) != 0;\n            var a = _view.ReadInt32(32) != 0;\n            var grip = _view.ReadInt32(36) != 0;\n            var stickX = _view.ReadSingle(40);\n            var stickY = _view.ReadSingle(44);'''
if old_read not in t: raise SystemExit('reader trigger marker missing')
t = t.replace(old_read, new_read, 1)
t = t.replace('sample = new XrPointerSample(valid, u, v, trigger);',
              'sample = new XrPointerSample(valid, u, v, trigger, a, grip, stickX, stickY);', 1)
t = t.replace('internal readonly record struct XrPointerSample(bool Valid, float U, float V, bool TriggerDown);',
              '''internal readonly record struct XrPointerSample(\n    bool Valid, float U, float V, bool TriggerDown,\n    bool ADown, bool GripDown, float StickX, float StickY);''', 1)
p.write_text(t, encoding='utf-8')

# Add controller state fields and extend PumpXrPointer after all previous patches.
p = Path('pc/MainFormV11.InputStereo.cs')
t = p.read_text(encoding='utf-8')
class_marker = '''internal sealed partial class MainForm\n{\n    private volatile bool _stereoUiSuspended;'''
class_new = '''internal sealed partial class MainForm\n{\n    private volatile bool _stereoUiSuspended;\n    private bool _xrADown;\n    private bool _xrGripDown;\n    private long _xrLastWheelMs;\n    private long _xrLastValidMs;'''
if class_marker not in t: raise SystemExit('MainForm InputStereo class marker missing')
t = t.replace(class_marker, class_new, 1)

# When a valid ray returns after headset sleep, ask CEF for a fresh frame.
valid_hook = '''        if (!ShouldRouteXrPointer(sample.U, sample.V, sample.TriggerDown)) return;'''
valid_new = '''        var nowMs = Environment.TickCount64;\n        if (nowMs - _xrLastValidMs > 350)\n        {\n            try { host.Invalidate(PaintElementType.View); } catch { }\n        }\n        _xrLastValidMs = nowMs;\n\n        if (!ShouldRouteXrPointer(sample.U, sample.V, sample.TriggerDown)) return;'''
if valid_hook not in t: raise SystemExit('ShouldRouteXrPointer hook missing; v0.13 base patch changed')
t = t.replace(valid_hook, valid_new, 1)

# Insert controller shortcuts after normal trigger handling.
trigger_block = '''            _xrTriggerDown = sample.TriggerDown;\n        }\n    }'''
controls = '''            _xrTriggerDown = sample.TriggerDown;\n        }\n\n        // A = right click at the current XR cursor.\n        if (sample.ADown != _xrADown)\n        {\n            host.SendMouseClickEvent(\n                x, y, MouseButtonType.Right, mouseUp: !sample.ADown,\n                clickCount: 1, modifiers: CefEventFlags.None);\n            _xrADown = sample.ADown;\n        }\n\n        // Grip = left-drag (GeoGebra 3D rotate). While grip is held, thumbstick\n        // turns the same drag into Shift+drag, which GeoGebra uses for moving/panning.\n        if (sample.GripDown != _xrGripDown)\n        {\n            host.SendMouseClickEvent(\n                x, y, MouseButtonType.Left, mouseUp: !sample.GripDown,\n                clickCount: 1, modifiers: CefEventFlags.None);\n            _xrGripDown = sample.GripDown;\n        }\n\n        var stickDead = Math.Abs(sample.StickX) < 0.18f && Math.Abs(sample.StickY) < 0.18f;\n        if (_xrGripDown)\n        {\n            var modifiers = CefEventFlags.LeftMouseButton;\n            var dragX = x;\n            var dragY = y;\n            if (!stickDead)\n            {\n                modifiers |= CefEventFlags.ShiftDown;\n                dragX = Math.Clamp(x + (int)Math.Round(sample.StickX * 28.0), 0, size.Width - 1);\n                dragY = Math.Clamp(y - (int)Math.Round(sample.StickY * 28.0), 0, size.Height - 1);\n            }\n            host.SendMouseMoveEvent(dragX, dragY, false, modifiers);\n        }\n        else if (Math.Abs(sample.StickY) >= 0.22f && nowMs - _xrLastWheelMs >= 55)\n        {\n            // Thumbstick forward/back = zoom in/out via wheel.\n            var delta = sample.StickY > 0 ? 120 : -120;\n            host.SendMouseWheelEvent(new MouseEvent(x, y, CefEventFlags.None), 0, delta);\n            _xrLastWheelMs = nowMs;\n        }\n    }'''
if trigger_block not in t: raise SystemExit('PumpXrPointer end marker missing')
t = t.replace(trigger_block, controls, 1)

# Lower CEF logical source a little more; keep enough pixels for text/lines.
t = t.replace('const int xrSourceWidth = 2048;', 'const int xrSourceWidth = 1856;', 1)
p.write_text(t, encoding='utf-8')

p = Path('pc/MainFormV11.Graphics.cs')
t = p.read_text(encoding='utf-8')
t = t.replace('return 1.25F;', 'return 1.20F;', 1)
p.write_text(t, encoding='utf-8')

# Protect the main browser from auth window.close(), and recover a blank close request.
p = Path('pc/SameSurfaceLifeSpanHandler.cs')
t = p.read_text(encoding='utf-8')
insert = '''\n    protected override bool DoClose(IWebBrowser chromiumWebBrowser, IBrowser browser)\n    {\n        // Login is deliberately redirected into our one XR browser. OAuth pages\n        // often call window.close(); never allow that to destroy the main surface.\n        if (!browser.IsPopup)\n        {\n            try\n            {\n                if (string.IsNullOrWhiteSpace(browser.MainFrame.Url) ||\n                    browser.MainFrame.Url == "about:blank")\n                {\n                    browser.GoBack();\n                }\n            }\n            catch { }\n            return true;\n        }\n        return base.DoClose(chromiumWebBrowser, browser);\n    }\n'''
idx = t.rfind('}')
if idx < 0: raise SystemExit('LifeSpanHandler class end missing')
t = t[:idx] + insert + t[idx:]
p.write_text(t, encoding='utf-8')

# Version and inherited build guards.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.13.2-popup-clarity', '0.13.3-resume-controls')
    t = t.replace(r'0\.13\.2-popup-clarity', r'0\.13\.3-resume-controls')
    t = t.replace('v0.13.2 ·', 'v0.13.3 ·')
    t = t.replace('[GGQ-PC v0.13.2]', '[GGQ-PC v0.13.3]')
    if file.endswith('.csproj'):
        t = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.3</Version>', t, count=1)
        t = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.3.0</FileVersion>', t, count=1)
        t = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.3.0</AssemblyVersion>', t, count=1)
    if file.endswith('build.ps1'):
        for a,b in [
            ('1\\.08f','1\\.00f'), ('1.08f','1.00f'),
            ('2\\.05f','2\\.15f'), ('2.05f','2.15f'),
            ('1\\.155f','1\\.210f'), ('1.155f','1.210f'),
            ('xrSourceWidth = 2048','xrSourceWidth = 1856'),
            ('return 1\\.25F','return 1\\.20F'), ('return 1.25F','return 1.20F')]:
            t = t.replace(a,b)
    p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.3 resume/controls patch applied')
