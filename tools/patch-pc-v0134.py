from pathlib import Path
import re


def must_replace(path, old, new, count=1):
    p = Path(path)
    t = p.read_text(encoding='utf-8')
    n = t.count(old)
    if n != count:
        raise SystemExit(f'{path}: expected {count} occurrences, got {n}: {old[:120]!r}')
    p.write_text(t.replace(old, new), encoding='utf-8')

# ---------------------------------------------------------------------------
# 1. XR cursor: larger, high-contrast, triangular and alpha blended.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
t = p.read_text(encoding='utf-8')
t = t.replace('constexpr float kCursorSizeMeters = 0.018f;',
              'constexpr float kCursorSizeMeters = 0.032f;', 1)
p.write_text(t, encoding='utf-8')

p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')
old_cursor = '''    void InitializeCursor(ID3D11Device* device, ID3D11DeviceContext* context) {\n        const std::uint32_t controllerPixel = 0xFF00FFFFu;\n        const std::uint32_t mousePixel = 0xFFFFFFFFu;\n        cursorTexture_.Upload(\n            device, context,\n            reinterpret_cast<const std::uint8_t*>(&controllerPixel),\n            1, 1, 4);\n        mouseCursorTexture_.Upload(\n            device, context,\n            reinterpret_cast<const std::uint8_t*>(&mousePixel),\n            1, 1, 4);\n    }'''
new_cursor = '''    void InitializeCursor(ID3D11Device* device, ID3D11DeviceContext* context) {\n        // 40x40 right-pointing cyan triangle with a dark outline. Transparent\n        // background + alpha blending keeps it visible on both white and dark UI.\n        constexpr int s = 40;\n        std::array<std::uint32_t, s * s> pixels{};\n        constexpr std::uint32_t transparent = 0x00000000u;\n        constexpr std::uint32_t outline = 0xFF101820u;\n        constexpr std::uint32_t fill = 0xFF00DDF5u;\n        pixels.fill(transparent);\n        for (int y = 0; y < s; ++y) {\n            for (int x = 0; x < s; ++x) {\n                const float dx = static_cast<float>(x - 5);\n                const float dy = std::abs(static_cast<float>(y) - 19.5f);\n                const bool inside = dx >= 0.0f && dx <= 30.0f &&\n                    dy <= dx * 0.58f + 1.0f;\n                if (!inside) continue;\n                const bool edge = dx < 3.0f ||\n                    std::abs(dy - (dx * 0.58f + 1.0f)) < 2.2f ||\n                    x >= 33;\n                pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;\n            }\n        }\n        cursorTexture_.Upload(\n            device, context,\n            reinterpret_cast<const std::uint8_t*>(pixels.data()),\n            s, s, s * 4);\n\n        const std::uint32_t mousePixel = 0xFFFFFFFFu;\n        mouseCursorTexture_.Upload(\n            device, context,\n            reinterpret_cast<const std::uint8_t*>(&mousePixel),\n            1, 1, 4);\n\n        D3D11_BLEND_DESC blend{};\n        blend.RenderTarget[0].BlendEnable = TRUE;\n        blend.RenderTarget[0].SrcBlend = D3D11_BLEND_SRC_ALPHA;\n        blend.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;\n        blend.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;\n        blend.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;\n        blend.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;\n        blend.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;\n        blend.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;\n        CheckHr(device->CreateBlendState(&blend, &cursorBlend_),\n            \"CreateBlendState(cursor)\");\n    }'''
if old_cursor not in t: raise SystemExit('InitializeCursor block missing')
t = t.replace(old_cursor, new_cursor, 1)

old_draw = '''        if (cursorValid && cursorTexture_.Valid()) {\n            PanelRect cursor{\n                cursorX - kCursorSizeMeters * 0.5f,\n                cursorX + kCursorSizeMeters * 0.5f,\n                cursorY + kCursorSizeMeters * 0.5f,\n                cursorY - kCursorSizeMeters * 0.5f};\n            DrawQuad(\n                context, view, cursor, -kCursorDistanceMeters,\n                cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);\n        }'''
new_draw = '''        if (cursorValid && cursorTexture_.Valid()) {\n            PanelRect cursor{\n                cursorX - kCursorSizeMeters * 0.5f,\n                cursorX + kCursorSizeMeters * 0.5f,\n                cursorY + kCursorSizeMeters * 0.5f,\n                cursorY - kCursorSizeMeters * 0.5f};\n            const float blendFactor[4] = {0, 0, 0, 0};\n            context->OMSetBlendState(cursorBlend_.Get(), blendFactor, 0xffffffffu);\n            DrawQuad(\n                context, view, cursor, -kCursorDistanceMeters,\n                cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);\n            context->OMSetBlendState(nullptr, blendFactor, 0xffffffffu);\n        }'''
if old_draw not in t: raise SystemExit('cursor draw block missing')
t = t.replace(old_draw, new_draw, 1)
member = '    ComPtr<ID3D11RasterizerState> rasterizer_;\n    SourceTexture cursorTexture_;'
member_new = '    ComPtr<ID3D11RasterizerState> rasterizer_;\n    ComPtr<ID3D11BlendState> cursorBlend_;\n    SourceTexture cursorTexture_;'
if member not in t: raise SystemExit('renderer member marker missing')
t = t.replace(member, member_new, 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 2. Login assist: injected VR keyboard on external login pages.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
needle = '''        e.Frame.ExecuteJavaScriptAsync(script);\n    }'''
login_injection = '''        e.Frame.ExecuteJavaScriptAsync(script);

        // External sign-in pages are usable without removing the headset. The
        // keyboard appears only while an editable field has focus.
        if (!e.Url.StartsWith("https://appassets.androidplatform.net/", StringComparison.OrdinalIgnoreCase))
        {
            const string loginAssist = """
            (function () {
              if (window.__ggqVrKeyboardInstalled) return;
              window.__ggqVrKeyboardInstalled = true;

              var active = null, shift = false, symbols = false;
              var root = document.createElement('div');
              root.id = 'ggq-vr-keyboard';
              root.style.cssText = 'position:fixed;left:3%;right:3%;bottom:2%;z-index:2147483647;display:none;'+
                'padding:12px;background:rgba(14,18,24,.96);border:2px solid #00ddf5;border-radius:16px;'+
                'box-shadow:0 8px 34px rgba(0,0,0,.55);font-family:Arial,sans-serif;user-select:none;';
              var title = document.createElement('div');
              title.textContent = 'Quest keyboard';
              title.style.cssText='color:#bff8ff;font-size:18px;margin:0 0 8px 4px';
              root.appendChild(title);
              var rows = document.createElement('div');
              root.appendChild(rows);
              (document.body || document.documentElement).appendChild(root);

              function isEditable(el) {
                if (!el) return false;
                var tag=(el.tagName||'').toLowerCase();
                if (tag==='textarea') return true;
                if (tag!=='input') return !!el.isContentEditable;
                var type=(el.type||'text').toLowerCase();
                return !['button','checkbox','radio','submit','reset','file','image','range','color','hidden'].includes(type);
              }
              function emitInput(el) {
                try { el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'})); }
                catch (_) { el.dispatchEvent(new Event('input',{bubbles:true})); }
                try { el.dispatchEvent(new Event('change',{bubbles:true})); } catch (_) {}
              }
              function insertText(text) {
                if (!active) return;
                active.focus();
                if (active.isContentEditable) {
                  document.execCommand('insertText', false, text); return;
                }
                var a=active.selectionStart, b=active.selectionEnd;
                if (typeof a==='number' && typeof b==='number' && active.setRangeText) {
                  active.setRangeText(text,a,b,'end');
                } else active.value=(active.value||'')+text;
                emitInput(active);
              }
              function backspace() {
                if (!active) return;
                active.focus();
                if (active.isContentEditable) { document.execCommand('delete'); return; }
                var a=active.selectionStart, b=active.selectionEnd;
                if (typeof a==='number' && typeof b==='number') {
                  if (a===b && a>0) a--;
                  active.setRangeText('',a,b,'end'); emitInput(active);
                }
              }
              function pressEnter() {
                if (!active) return;
                active.focus();
                ['keydown','keypress','keyup'].forEach(function(t){
                  try { active.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})); } catch(_){}
                });
                var form=active.form;
                if (form && typeof form.requestSubmit==='function') { try { form.requestSubmit(); } catch(_){} }
              }
              function key(label, value, wide) {
                var b=document.createElement('button');
                b.type='button'; b.textContent=label;
                b.style.cssText='min-width:'+(wide?'92':'48')+'px;height:48px;margin:4px;padding:0 10px;'+
                  'border:1px solid #52606d;border-radius:9px;background:#27313d;color:white;font-size:20px;font-weight:600;';
                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });
                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); value(); });
                return b;
              }
              function render() {
                rows.textContent='';
                var layouts = symbols ? [
                  ['1','2','3','4','5','6','7','8','9','0'],
                  ['!','@','#','$','%','^','&','*','(',')'],
                  ['-','_','=','+','[',']','{','}','/','\\\\'],
                  ['.',',',';',':','?','\\\'', '"','<','>','|']
                ] : [
                  ['q','w','e','r','t','y','u','i','o','p'],
                  ['a','s','d','f','g','h','j','k','l'],
                  ['z','x','c','v','b','n','m'],
                  ['1','2','3','4','5','6','7','8','9','0']
                ];
                layouts.forEach(function(row){
                  var d=document.createElement('div'); d.style.textAlign='center';
                  row.forEach(function(ch){
                    var out=(!symbols && shift)?ch.toUpperCase():ch;
                    d.appendChild(key(out,function(){insertText(out);},false));
                  }); rows.appendChild(d);
                });
                var d=document.createElement('div'); d.style.textAlign='center';
                d.appendChild(key(shift?'SHIFT ✓':'SHIFT',function(){shift=!shift;render();},true));
                d.appendChild(key(symbols?'ABC':'#+=',function(){symbols=!symbols;render();},true));
                d.appendChild(key('SPACE',function(){insertText(' ');},true));
                d.appendChild(key('⌫',backspace,true));
                d.appendChild(key('ENTER',pressEnter,true));
                d.appendChild(key('HIDE',function(){root.style.display='none';},true));
                rows.appendChild(d);
              }
              render();

              document.addEventListener('focusin',function(e){
                if (isEditable(e.target)) { active=e.target; root.style.display='block'; }
              },true);
              document.addEventListener('pointerdown',function(e){
                if (root.contains(e.target)) return;
                if (isEditable(e.target)) { active=e.target; root.style.display='block'; }
              },true);
            })();
            """;
            e.Frame.ExecuteJavaScriptAsync(loginAssist);
        }
    }'''
if needle not in t: raise SystemExit('BrowserFrameLoadEnd end marker missing')
t = t.replace(needle, login_injection, 1)
p.write_text(t, encoding='utf-8')

# Version labels only; retain all v0.13.3 visual/controller tuning.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    q = Path(file)
    s = q.read_text(encoding='utf-8')
    s = s.replace('0.13.3-resume-controls', '0.13.4-login-keyboard-cursor')
    s = s.replace(r'0\\.13\\.3-resume-controls', r'0\\.13\\.4-login-keyboard-cursor')
    s = s.replace('v0.13.3 ·', 'v0.13.4 ·')
    s = s.replace('[GGQ-PC v0.13.3]', '[GGQ-PC v0.13.4]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.4</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.4.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.4.0</AssemblyVersion>', s, count=1)
    q.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.4 login keyboard + cursor applied')
