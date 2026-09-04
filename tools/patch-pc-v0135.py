from pathlib import Path
import re

# This patch runs after v0.13.4. CI trigger revision 2.

# ---------------------------------------------------------------------------
# 1. Robust VR keyboard editing for controlled/react login inputs.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

new_emit = """              function nativeSetValue(el, value) {\n                try {\n                  var proto = el.tagName && el.tagName.toLowerCase()==='textarea'\n                    ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;\n                  var desc = Object.getOwnPropertyDescriptor(proto, 'value');\n                  if (desc && desc.set) desc.set.call(el, value); else el.value=value;\n                } catch (_) { el.value=value; }\n              }\n              function emitInput(el, inputType, data) {\n                try {\n                  el.dispatchEvent(new InputEvent('input',{\n                    bubbles:true, inputType:inputType, data:data==null?null:data\n                  }));\n                } catch (_) { el.dispatchEvent(new Event('input',{bubbles:true})); }\n              }\n              function replaceRange(text, inputType) {\n                if (!active) return;\n                active.focus();\n                if (active.isContentEditable) {\n                  document.execCommand(inputType==='deleteContentBackward'?'delete':'insertText', false, text||'');\n                  return;\n                }\n                var value=String(active.value||'');\n                var a=typeof active.selectionStart==='number'?active.selectionStart:value.length;\n                var b=typeof active.selectionEnd==='number'?active.selectionEnd:a;\n                if (inputType==='deleteContentBackward' && a===b && a>0) a--;\n                var next=value.slice(0,a)+(text||'')+value.slice(b);\n                nativeSetValue(active,next);\n                var caret=a+(text?text.length:0);\n                try { active.setSelectionRange(caret,caret); } catch (_) {}\n                emitInput(active,inputType,text||null);\n                try { active.dispatchEvent(new Event('change',{bubbles:true})); } catch (_) {}\n              }\n              function insertText(text) { replaceRange(text,'insertText'); }\n              function backspace() { replaceRange('', 'deleteContentBackward'); }\n"""
keyboard_pattern = re.compile(
    r"              function emitInput\(el\) \{.*?              function pressEnter\(\) \{",
    re.S)
m = keyboard_pattern.search(t)
if not m:
    raise SystemExit('v0.13.4 keyboard editing functions not found')
t = t[:m.start()] + new_emit + "              function pressEnter() {" + t[m.end():]
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 2. One Quest cursor only. XR ray wins; otherwise PC mouse drives the same cursor.
#    Rotate the cyan triangle 45 degrees counter-clockwise.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

old_shape = """        // 40x40 right-pointing cyan triangle with a dark outline. Transparent\n        // background + alpha blending keeps it visible on both white and dark UI.\n        constexpr int s = 40;\n        std::array<std::uint32_t, s * s> pixels{};\n        constexpr std::uint32_t transparent = 0x00000000u;\n        constexpr std::uint32_t outline = 0xFF101820u;\n        constexpr std::uint32_t fill = 0xFF00DDF5u;\n        pixels.fill(transparent);\n        for (int y = 0; y < s; ++y) {\n            for (int x = 0; x < s; ++x) {\n                const float dx = static_cast<float>(x - 5);\n                const float dy = std::abs(static_cast<float>(y) - 19.5f);\n                const bool inside = dx >= 0.0f && dx <= 30.0f &&\n                    dy <= dx * 0.58f + 1.0f;\n                if (!inside) continue;\n                const bool edge = dx < 3.0f ||\n                    std::abs(dy - (dx * 0.58f + 1.0f)) < 2.2f ||\n                    x >= 33;\n                pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;\n            }\n        }"""
new_shape = """        // 40x40 cyan triangle, rotated 45 degrees counter-clockwise. Dark\n        // outline + transparent background keeps one cursor visible on any UI.\n        constexpr int s = 40;\n        std::array<std::uint32_t, s * s> pixels{};\n        constexpr std::uint32_t transparent = 0x00000000u;\n        constexpr std::uint32_t outline = 0xFF101820u;\n        constexpr std::uint32_t fill = 0xFF00DDF5u;\n        constexpr float c = 0.70710678f;\n        pixels.fill(transparent);\n        for (int y = 0; y < s; ++y) {\n            for (int x = 0; x < s; ++x) {\n                const float px = static_cast<float>(x) - 19.5f;\n                const float py = static_cast<float>(y) - 19.5f;\n                const float sx = c * px - c * py + 19.5f;\n                const float sy = c * px + c * py + 19.5f;\n                const float dx = sx - 5.0f;\n                const float dy = std::abs(sy - 19.5f);\n                const bool inside = dx >= 0.0f && dx <= 30.0f &&\n                    dy <= dx * 0.58f + 1.0f;\n                if (!inside) continue;\n                const bool edge = dx < 3.0f ||\n                    std::abs(dy - (dx * 0.58f + 1.0f)) < 2.2f ||\n                    sx >= 33.0f;\n                pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;\n            }\n        }"""
if old_shape not in t:
    raise SystemExit('v0.13.4 triangle block not found')
t = t.replace(old_shape, new_shape, 1)

old_mouse_upload = """        const std::uint32_t mousePixel = 0xFFFFFFFFu;\n        mouseCursorTexture_.Upload(\n            device, context,\n            reinterpret_cast<const std::uint8_t*>(&mousePixel),\n            1, 1, 4);\n\n"""
if old_mouse_upload not in t:
    raise SystemExit('mouse cursor upload block not found')
t = t.replace(old_mouse_upload, '', 1)

pattern = re.compile(r'''        const MousePointerState mouse = mouseReader_\.ReadLatest\(\);\n        if \(!cursorValid && mouse\.valid && mouseCursorTexture_\.Valid\(\)\) \{.*?        if \(cursorValid && cursorTexture_\.Valid\(\)\) \{.*?            context->OMSetBlendState\(nullptr, blendFactor, 0xffffffffu\);\n        \}\n''', re.S)
m = pattern.search(t)
if not m:
    raise SystemExit('combined v0.13.4 cursor render blocks not found')
new_cursor = """        const MousePointerState mouse = mouseReader_.ReadLatest();\n        bool unifiedCursorValid = false;\n        float unifiedCursorX = 0.0f;\n        float unifiedCursorY = 0.0f;\n\n        if (cursorValid) {\n            unifiedCursorValid = true;\n            unifiedCursorX = cursorX;\n            unifiedCursorY = cursorY;\n        } else if (mouse.valid) {\n            const float baseWidth = baseRect.right - baseRect.left;\n            const float baseHeight = baseRect.top - baseRect.bottom;\n            const float hitX = baseRect.left + baseWidth * mouse.u;\n            const float hitY = baseRect.top - baseHeight * mouse.v;\n            const float scale = kCursorDistanceMeters / kScreenDistanceMeters;\n            unifiedCursorValid = true;\n            unifiedCursorX = hitX * scale;\n            unifiedCursorY = hitY * scale;\n        }\n\n        if (unifiedCursorValid && cursorTexture_.Valid()) {\n            PanelRect cursor{\n                unifiedCursorX - kCursorSizeMeters * 0.5f,\n                unifiedCursorX + kCursorSizeMeters * 0.5f,\n                unifiedCursorY + kCursorSizeMeters * 0.5f,\n                unifiedCursorY - kCursorSizeMeters * 0.5f};\n            const float blendFactor[4] = {0, 0, 0, 0};\n            context->OMSetBlendState(cursorBlend_.Get(), blendFactor, 0xffffffffu);\n            DrawQuad(\n                context, view, cursor, -kCursorDistanceMeters,\n                cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);\n            context->OMSetBlendState(nullptr, blendFactor, 0xffffffffu);\n        }\n"""
t = t[:m.start()] + new_cursor + t[m.end():]
t = t.replace('    SourceTexture mouseCursorTexture_;\n', '', 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 3. Version/build labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.13.4-login-keyboard-cursor', '0.13.5-cursor-keyboard-fix')
    t = t.replace(r'0\\.13\\.4-login-keyboard-cursor', r'0\\.13\\.5-cursor-keyboard-fix')
    t = t.replace('v0.13.4 ·', 'v0.13.5 ·')
    t = t.replace('[GGQ-PC v0.13.4]', '[GGQ-PC v0.13.5]')
    if file.endswith('.csproj'):
        t = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.5</Version>', t, count=1)
        t = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.5.0</FileVersion>', t, count=1)
        t = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.5.0</AssemblyVersion>', t, count=1)
    p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.5 cursor + keyboard fix applied')
