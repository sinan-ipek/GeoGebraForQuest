from pathlib import Path
import re


def require(text, needle, label):
    if needle not in text:
        raise SystemExit(label)

# ---------------------------------------------------------------------------
# Main C# app: return from OAuth to OUR local GeoGebra surface, keep the shared
# RequestContext/session, and strengthen the Quest virtual keyboard.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

# Login must return to the local GeoGebraForQuest surface. Cookies/session stay
# in the shared RequestContext, so this does not sign the user out.
t = t.replace('root.MainFrame.LoadUrl(PostLoginClassicUrl);',
              'root.MainFrame.LoadUrl(LocalAppUrl);', 1)
t = t.replace('popup-close step 7: opening geogebra.org/classic with shared auth session',
              'popup-close step 7: returning to local GeoGebraForQuest surface with shared auth session')
t = t.replace('popup-close complete; root surface restored and classic opened',
              'popup-close complete; local stereo surface restored')

# Do not run the external Classic special branch anymore. It was the source of
# the post-login hand-off to the standard non-stereo GeoGebra surface.
classic_pat = re.compile(
    r'        if \(e\.Url\.StartsWith\("https://www\.geogebra\.org/classic".*?\n        \}\n\n(?=        // External sign-in pages)',
    re.S)
t, _ = classic_pat.subn('', t, count=1)

# Expand editable detection to GeoGebra's dynamically created search controls.
old_edit = """              function isEditable(el) {
                if (!el) return false;
                var tag=(el.tagName||'').toLowerCase();
                if (tag==='textarea') return true;
                if (tag!=='input') return !!el.isContentEditable;
                var type=(el.type||'text').toLowerCase();
                return !['button','checkbox','radio','submit','reset','file','image','range','color','hidden'].includes(type);
              }"""
new_edit = """              function isEditable(el) {
                if (!el || el.nodeType!==1) return false;
                var tag=(el.tagName||'').toLowerCase();
                var role=(el.getAttribute&&el.getAttribute('role')||'').toLowerCase();
                var ce=(el.getAttribute&&el.getAttribute('contenteditable')||'').toLowerCase();
                if (tag==='textarea' || role==='textbox' || role==='searchbox' || el.isContentEditable || ce==='true' || ce==='plaintext-only') return true;
                if (tag!=='input') return false;
                var type=(el.type||'text').toLowerCase();
                return !['button','checkbox','radio','submit','reset','file','image','range','color','hidden'].includes(type);
              }
              function editableFrom(node) {
                if (!node || node.nodeType!==1) return null;
                if (isEditable(node)) return node;
                var direct=node.closest&&node.closest('input,textarea,[contenteditable=true],[contenteditable=plaintext-only],[role=textbox],[role=searchbox]');
                if (direct && isEditable(direct)) return direct;
                var child=node.querySelector&&node.querySelector('input,textarea,[contenteditable=true],[contenteditable=plaintext-only],[role=textbox],[role=searchbox]');
                return child && isEditable(child) ? child : null;
              }
              function visibleEditable() {
                var all=document.querySelectorAll('input,textarea,[contenteditable=true],[contenteditable=plaintext-only],[role=textbox],[role=searchbox]');
                for (var i=0;i<all.length;i++) {
                  var el=all[i], r=el.getBoundingClientRect();
                  if (isEditable(el) && r.width>20 && r.height>12 && getComputedStyle(el).visibility!=='hidden' && getComputedStyle(el).display!=='none') return el;
                }
                return null;
              }"""
require(t, old_edit, 'v0.13.12: isEditable block missing')
t = t.replace(old_edit, new_edit, 1)

# Improve key press reliability in XR: act on pointerdown, give visible feedback,
# and allow Backspace to repeat while held.
old_key_events = """                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });
                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); playKeyTone(); value(); });
                return b;"""
new_key_events = """                var holdTimer=null, repeatTimer=null;
                function releaseVisual(){ b.style.transform='translateY(0)'; b.style.filter='none'; if(holdTimer){clearTimeout(holdTimer);holdTimer=null;} if(repeatTimer){clearInterval(repeatTimer);repeatTimer=null;} }
                b.addEventListener('pointerdown',function(e){
                  e.preventDefault(); e.stopPropagation();
                  b.style.transform='translateY(2px)'; b.style.filter='brightness(1.35)';
                  playKeyTone(); value();
                  if(label==='⌫') holdTimer=setTimeout(function(){ repeatTimer=setInterval(function(){ playKeyTone(); value(); },70); },380);
                });
                b.addEventListener('pointerup',function(e){ e.preventDefault(); e.stopPropagation(); releaseVisual(); });
                b.addEventListener('pointercancel',releaseVisual);
                b.addEventListener('pointerleave',releaseVisual);
                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); });
                return b;"""
require(t, old_key_events, 'v0.13.12: keyboard event block missing')
t = t.replace(old_key_events, new_key_events, 1)

# Replace the old focus/pointer listeners with dynamic-search-aware listeners.
old_listeners = """              document.addEventListener('focusin',function(e){
                if (isEditable(e.target)) { markActive(e.target); root.style.display='block'; }
              },true);
              document.addEventListener('pointerdown',function(e){
                if (root.contains(e.target)) return;
                if (isEditable(e.target)) { markActive(e.target); root.style.display='block'; }
              },true);"""
new_listeners = """              function showFor(el){
                if(!el || !isEditable(el)) return false;
                try{ el.focus({preventScroll:true}); }catch(_){ try{el.focus();}catch(__){} }
                markActive(el); root.style.display='block'; updateFocusMarker(); return true;
              }
              function recoverFocusedEditable(seed){
                if(showFor(editableFrom(seed))) return;
                if(showFor(editableFrom(document.activeElement))) return;
                showFor(visibleEditable());
              }
              document.addEventListener('focusin',function(e){
                recoverFocusedEditable(e.target);
              },true);
              document.addEventListener('pointerdown',function(e){
                if (root.contains(e.target)) return;
                var candidate=editableFrom(e.target);
                if(candidate){ showFor(candidate); return; }
                setTimeout(function(){recoverFocusedEditable(e.target);},0);
                setTimeout(function(){recoverFocusedEditable(document.activeElement);},80);
                setTimeout(function(){recoverFocusedEditable(document.activeElement);},220);
              },true);
              document.addEventListener('click',function(e){
                if(root.contains(e.target)) return;
                setTimeout(function(){recoverFocusedEditable(document.activeElement);},30);
                setTimeout(function(){recoverFocusedEditable(document.activeElement);},180);
              },true);
              var keyboardObserver=new MutationObserver(function(){
                var a=editableFrom(document.activeElement);
                if(a && root.style.display==='block') markActive(a);
              });
              keyboardObserver.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['contenteditable','role','type']});"""
require(t, old_listeners, 'v0.13.12: keyboard listener block missing')
t = t.replace(old_listeners, new_listeners, 1)

# Better layout density.
t = t.replace('max-width:1040px', 'max-width:980px', 1)
t = t.replace("width:176px;border-left:1px solid #52606d;padding-left:2px;margin-left:0;",
              "width:168px;border-left:1px solid #52606d;padding-left:0;margin-left:-2px;", 1)

# Version labels.
for file in ('pc/MainFormV11.cs','pc/GeoGebraForQuest.PC.csproj','pc/build.ps1'):
    q = Path(file)
    s = q.read_text(encoding='utf-8') if file != 'pc/MainFormV11.cs' else t
    s = s.replace('0.13.11-keyboard-classic-splash','0.13.12-login-stereo-keyboard-xr-splash')
    s = s.replace(r'0\.13\.11-keyboard-classic-splash', r'0\.13\.12-login-stereo-keyboard-xr-splash')
    s = s.replace('v0.13.11','v0.13.12')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.12</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.12.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.12.0</AssemblyVersion>', s, count=1)
    if file.endswith('build.ps1'):
        s = re.sub(r'GeoGebraForQuest-PC-v[^"\r\n]+-win-x64',
                   'GeoGebraForQuest-PC-v0.13.12-login-stereo-keyboard-xr-splash-win-x64', s, count=1)
    q.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Native XR splash.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
x = p.read_text(encoding='utf-8')

require(x, '#include "v11-render.hpp"', 'v0.13.12: XR include marker missing')
x = x.replace('#include "v11-render.hpp"',
              '#include "v11-render.hpp"\n#include "v1312-splash.hpp"', 1)

member = '    SharedGpuTextureConsumer baseTexture_;\n'
require(x, member, 'v0.13.12: base texture member missing')
x = x.replace(member, member +
              '    ggqv1312::SplashTexture splashLeft_;\n'
              '    ggqv1312::SplashTexture splashRight_;\n'
              '    std::chrono::steady_clock::time_point splashUntil_{};\n', 1)

init = '        baseTexture_.Initialize(device_.Get());\n'
require(x, init, 'v0.13.12: XR base texture init missing')
x = x.replace(init, init + '''
        try {
            const auto dir = ggqv1312::ExeDir1312();
            splashLeft_.Load(device_.Get(), dir / L"stereo_splash_left.png");
            splashRight_.Load(device_.Get(), dir / L"stereo_splash_right.png");
            splashUntil_ = std::chrono::steady_clock::now() + std::chrono::milliseconds(2800);
            if (splashLeft_.Valid() && splashRight_.Valid()) {
                Log("v0.13.12 native XR stereo splash loaded");
            } else {
                Log("v0.13.12 XR splash assets unavailable; continuing without splash");
            }
        } catch (const std::exception& ex) {
            Log(std::string("v0.13.12 XR splash load error: ") + ex.what());
        }
''', 1)

old_rect = '''    PanelRect MakeBaseRect() const {
        const int width = std::max(1, baseTexture_.Width());
        const int height = std::max(1, baseTexture_.Height());'''
new_rect = '''    PanelRect MakeBaseRect(int widthOverride = 0, int heightOverride = 0) const {
        const int width = std::max(1, widthOverride > 0 ? widthOverride : baseTexture_.Width());
        const int height = std::max(1, heightOverride > 0 ? heightOverride : baseTexture_.Height());'''
require(x, old_rect, 'v0.13.12: MakeBaseRect marker missing')
x = x.replace(old_rect, new_rect, 1)

old_if = '        if (frameState.shouldRender && baseTexture_.Valid()) {'
new_if = '''        const bool splashReady = splashLeft_.Valid() && splashRight_.Valid();
        const bool showSplash = splashReady &&
            (!baseTexture_.Valid() || std::chrono::steady_clock::now() < splashUntil_);
        if (frameState.shouldRender && (baseTexture_.Valid() || showSplash)) {'''
require(x, old_if, 'v0.13.12: RenderFrame base condition missing')
x = x.replace(old_if, new_if, 1)

old_base_rect = '                const PanelRect baseRect = MakeBaseRect();'
new_base_rect = '''                const PanelRect baseRect = showSplash
                    ? MakeBaseRect(splashLeft_.Width(), splashLeft_.Height())
                    : MakeBaseRect();'''
require(x, old_base_rect, 'v0.13.12: baseRect call missing')
x = x.replace(old_base_rect, new_base_rect, 1)

x = x.replace('                const bool stereoValid =\n                    sbsTexture_.Valid() && MakeStereoRect(baseRect, stereoRect);',
              '                const bool stereoValid =\n                    !showSplash && sbsTexture_.Valid() && MakeStereoRect(baseRect, stereoRect);', 1)

old_pointer = '''                const bool cursorValid = UpdatePointer(
                    frameState.predictedDisplayTime,
                    baseRect,
                    cursorX,
                    cursorY);'''
new_pointer = '''                const bool cursorValid = !showSplash && UpdatePointer(
                    frameState.predictedDisplayTime,
                    baseRect,
                    cursorX,
                    cursorY);'''
require(x, old_pointer, 'v0.13.12: pointer marker missing')
x = x.replace(old_pointer, new_pointer, 1)

old_srv = '                        baseTexture_.Srv(),\n                        baseRect,'
new_srv = '''                        showSplash
                            ? (eye == 0 ? splashLeft_.Srv() : splashRight_.Srv())
                            : baseTexture_.Srv(),
                        baseRect,'''
require(x, old_srv, 'v0.13.12: RenderEye base SRV marker missing')
x = x.replace(old_srv, new_srv, 1)

x = x.replace('        context_.Reset();\n        device_.Reset();',
              '        splashLeft_.Reset();\n        splashRight_.Reset();\n        context_.Reset();\n        device_.Reset();', 1)
p.write_text(x, encoding='utf-8')

# Generated CMake must compile/link WIC support.
p = Path('pc-xr/CMakeLists.txt')
c = p.read_text(encoding='utf-8')
if 'v1312-splash.hpp' not in c:
    c = c.replace('  v11-render.hpp\n', '  v11-render.hpp\n  v1312-splash.hpp\n', 1)
if 'windowscodecs' not in c:
    c = c.replace('  user32\n)', '  user32\n  windowscodecs\n  ole32\n)', 1)
p.write_text(c, encoding='utf-8')

# Build package includes the converted standalone splash images next to XR EXE.
p = Path('pc/build.ps1')
b = p.read_text(encoding='utf-8')
copy_marker = 'Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force'
require(b, copy_marker, 'v0.13.12: XR copy marker missing')
b = b.replace(copy_marker, copy_marker + '''
$splashLeft = Join-Path $root "pc-xr\\stereo_splash_left.png"
$splashRight = Join-Path $root "pc-xr\\stereo_splash_right.png"
if (Test-Path $splashLeft) { Copy-Item $splashLeft (Join-Path $xrOut "stereo_splash_left.png") -Force }
if (Test-Path $splashRight) { Copy-Item $splashRight (Join-Path $xrOut "stereo_splash_right.png") -Force }''', 1)
p.write_text(b, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.12 login/stereo/keyboard/native-XR-splash patch applied')
