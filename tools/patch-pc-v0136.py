from pathlib import Path
import re

# v0.13.6 runs after v0.13.5.

# ---------------------------------------------------------------------------
# 1. Make the active login field unmistakable in Quest.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

old_focus = """              document.addEventListener('focusin',function(e){\n                if (isEditable(e.target)) { active=e.target; root.style.display='block'; }\n              },true);\n              document.addEventListener('pointerdown',function(e){\n                if (root.contains(e.target)) return;\n                if (isEditable(e.target)) { active=e.target; root.style.display='block'; }\n              },true);"""

new_focus = """              var focusMarker=document.createElement('div');\n              focusMarker.id='ggq-focus-marker';\n              focusMarker.style.cssText='position:fixed;z-index:2147483646;display:none;pointer-events:none;'+\n                'padding:5px 9px;border-radius:8px;background:#00ddf5;color:#071018;font:bold 14px Arial;'+\n                'box-shadow:0 2px 10px rgba(0,0,0,.45)';\n              (document.body||document.documentElement).appendChild(focusMarker);\n\n              var previousActive=null;\n              function fieldLabel(el){\n                var type=(el && el.type || '').toLowerCase();\n                if(type==='password') return 'ŞİFRE';\n                var ac=(el && el.autocomplete || '').toLowerCase();\n                var text=((el && (el.placeholder||el.name||el.id))||'').toLowerCase();\n                if(ac.indexOf('user')>=0 || ac==='email' || /mail|user|login|name|ad/.test(text)) return 'KULLANICI ADI';\n                return 'YAZI ALANI';\n              }\n              function playFocusTone(password){\n                try{\n                  var C=window.AudioContext||window.webkitAudioContext; if(!C) return;\n                  window.__ggqAudio=window.__ggqAudio||new C();\n                  var ctx=window.__ggqAudio, osc=ctx.createOscillator(), gain=ctx.createGain();\n                  osc.frequency.value=password?880:660; gain.gain.value=.035;\n                  osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime+.055);\n                }catch(_){}\n              }\n              function updateFocusMarker(){\n                if(!active || !isEditable(active)){ focusMarker.style.display='none'; return; }\n                var r=active.getBoundingClientRect();\n                focusMarker.style.left=Math.max(6,Math.min(innerWidth-160,r.right-145))+'px';\n                focusMarker.style.top=Math.max(6,r.top-34)+'px';\n              }\n              function markActive(el){\n                if(!isEditable(el)) return;\n                if(previousActive && previousActive!==el){\n                  try{ previousActive.style.removeProperty('outline'); previousActive.style.removeProperty('box-shadow'); }catch(_){}\n                }\n                active=el; previousActive=el;\n                try{\n                  el.style.setProperty('caret-color','#00ddf5','important');\n                  el.style.setProperty('outline','3px solid #00ddf5','important');\n                  el.style.setProperty('box-shadow','0 0 0 4px rgba(0,221,245,.28)','important');\n                }catch(_){}\n                var label=fieldLabel(el);\n                title.textContent='Quest keyboard · '+label;\n                focusMarker.textContent='◀ '+label;\n                focusMarker.style.display='block'; updateFocusMarker();\n                try{ el.scrollIntoView({block:'center',inline:'nearest'}); }catch(_){}\n                if(el!==window.__ggqLastFocused){ playFocusTone((el.type||'').toLowerCase()==='password'); }\n                window.__ggqLastFocused=el;\n              }\n              function focusNext(){\n                var fields=Array.prototype.filter.call(document.querySelectorAll('input,textarea,[contenteditable=true]'),isEditable);\n                if(!fields.length) return;\n                var i=fields.indexOf(active); var next=fields[(i+1+fields.length)%fields.length];\n                try{ next.focus(); }catch(_){} markActive(next);\n              }\n              addEventListener('scroll',updateFocusMarker,true);\n              addEventListener('resize',updateFocusMarker,{passive:true});\n\n              document.addEventListener('focusin',function(e){\n                if (isEditable(e.target)) { markActive(e.target); root.style.display='block'; }\n              },true);\n              document.addEventListener('pointerdown',function(e){\n                if (root.contains(e.target)) return;\n                if (isEditable(e.target)) { markActive(e.target); root.style.display='block'; }\n              },true);"""

if old_focus not in t:
    raise SystemExit('v0.13.5 focus listener block not found')
t = t.replace(old_focus, new_focus, 1)

# Add an explicit NEXT key next to Backspace/Enter.
old_keys = """                d.appendChild(key('SPACE',function(){insertText(' ');},true));\n                d.appendChild(key('⌫',backspace,true));\n                d.appendChild(key('ENTER',pressEnter,true));"""
new_keys = """                d.appendChild(key('SPACE',function(){insertText(' ');},true));\n                d.appendChild(key('⌫',backspace,true));\n                d.appendChild(key('SONRAKİ',focusNext,true));\n                d.appendChild(key('ENTER',pressEnter,true));"""
if old_keys not in t:
    raise SystemExit('keyboard action row not found')
t = t.replace(old_keys, new_keys, 1)

# Reuse the existing RequestContext on auth recovery so cookies/session survive.
old_ctx = """        _requestContext = new RequestContext(new RequestContextSettings { CachePath = cache });\n        _requestContext.RegisterSchemeHandlerFactory(\n            \"https\",\n            LocalHost,\n            new FolderSchemeHandlerFactory(\n                rootFolder: root,\n                schemeName: \"https\",\n                hostName: LocalHost,\n                defaultPage: \"index.html\"));"""
new_ctx = """        if (_requestContext is null)\n        {\n            _requestContext = new RequestContext(new RequestContextSettings { CachePath = cache });\n            _requestContext.RegisterSchemeHandlerFactory(\n                \"https\",\n                LocalHost,\n                new FolderSchemeHandlerFactory(\n                    rootFolder: root,\n                    schemeName: \"https\",\n                    hostName: LocalHost,\n                    defaultPage: \"index.html\"));\n        }"""
if old_ctx not in t:
    raise SystemExit('CreateBrowser RequestContext block not found')
t = t.replace(old_ctx, new_ctx, 1)

old_ctor = """            this,\n            initialSize.Width,\n            initialSize.Height);"""
new_ctor = """            this,\n            initialSize.Width,\n            initialSize.Height,\n            RecoverMainBrowserAfterAuthClose);"""
if old_ctor not in t:
    raise SystemExit('D3D browser constructor call not found')
t = t.replace(old_ctor, new_ctor, 1)

# Browser recreation callback. It is intentionally UI-thread marshalled and reuses
# the live RequestContext; auth cookies are therefore not lost when OAuth closes.
insert_before = """    private void BrowserFrameLoadEnd(object? sender, FrameLoadEndEventArgs e)\n    {"""
recovery = """    private int _authBrowserRecoveryPending;\n\n    private void RecoverMainBrowserAfterAuthClose()\n    {\n        if (_closing || Interlocked.Exchange(ref _authBrowserRecoveryPending, 1) != 0) return;\n        BeginInvokeSafe(() =>\n        {\n            try\n            {\n                if (_closing) return;\n                var old = _browser;\n                _browser = null;\n                try { old?.Dispose(); } catch { }\n                _cefPageText = \"CEF oturum yenileniyor\";\n                UpdateWindowTitle();\n                CreateBrowser();\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = \"CEF auth recovery: \" + ShortError(ex);\n                UpdateWindowTitle();\n            }\n            finally\n            {\n                Interlocked.Exchange(ref _authBrowserRecoveryPending, 0);\n            }\n        });\n    }\n\n    private void BrowserFrameLoadEnd(object? sender, FrameLoadEndEventArgs e)\n    {"""
if insert_before not in t:
    raise SystemExit('BrowserFrameLoadEnd marker missing')
t = t.replace(insert_before, recovery, 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 2. Replace fragile same-tab close recovery with explicit browser recreation.
# ---------------------------------------------------------------------------
p = Path('pc/SameSurfaceLifeSpanHandler.cs')
p.write_text(r'''using CefSharp;
using CefSharp.Handler;

namespace GeoGebraForQuest.PC;

internal sealed class SameSurfaceLifeSpanHandler : LifeSpanHandler
{
    private readonly Action? _recoverMainBrowser;
    private bool _authRedirected;

    public SameSurfaceLifeSpanHandler(Action? recoverMainBrowser)
    {
        _recoverMainBrowser = recoverMainBrowser;
    }

    protected override bool OnBeforePopup(
        IWebBrowser chromiumWebBrowser,
        IBrowser browser,
        IFrame frame,
        string targetUrl,
        string targetFrameName,
        WindowOpenDisposition targetDisposition,
        bool userGesture,
        IPopupFeatures popupFeatures,
        IWindowInfo windowInfo,
        IBrowserSettings browserSettings,
        ref bool noJavascriptAccess,
        out IWebBrowser newBrowser)
    {
        newBrowser = null!;
        if (!string.IsNullOrWhiteSpace(targetUrl))
        {
            _authRedirected = true;
            browser.MainFrame.LoadUrl(targetUrl);
        }
        return true;
    }

    protected override bool DoClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        // A real OAuth popup is redirected into the single XR CEF surface. Once
        // the provider calls window.close(), let that browser close cleanly. The
        // MainForm will recreate the local GeoGebra browser with the SAME live
        // RequestContext, keeping cookies/session while avoiding a dead black view.
        return false;
    }

    protected override void OnBeforeClose(IWebBrowser chromiumWebBrowser, IBrowser browser)
    {
        if (_authRedirected && !browser.IsPopup)
        {
            try { _recoverMainBrowser?.Invoke(); } catch { }
        }
        base.OnBeforeClose(chromiumWebBrowser, browser);
    }
}
''', encoding='utf-8')

# D3D browser passes the recovery callback into the lifespan handler.
p = Path('pc/D3DChromiumWebBrowser.cs')
t = p.read_text(encoding='utf-8')
old_sig = """        IRenderHandler renderHandler,\n        int initialWidth,\n        int initialHeight)"""
new_sig = """        IRenderHandler renderHandler,\n        int initialWidth,\n        int initialHeight,\n        Action? recoverMainBrowser = null)"""
if old_sig not in t:
    raise SystemExit('D3D browser constructor signature missing')
t = t.replace(old_sig, new_sig, 1)
t = t.replace('LifeSpanHandler = new SameSurfaceLifeSpanHandler();',
              'LifeSpanHandler = new SameSurfaceLifeSpanHandler(recoverMainBrowser);', 1)
p.write_text(t, encoding='utf-8')

# ---------------------------------------------------------------------------
# 3. Version labels/build validation tag.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.13.5-cursor-keyboard-fix', '0.13.6-login-focus-recovery')
    t = t.replace(r'0\\.13\\.5-cursor-keyboard-fix', r'0\\.13\\.6-login-focus-recovery')
    t = t.replace('v0.13.5 ·', 'v0.13.6 ·')
    t = t.replace('[GGQ-PC v0.13.5]', '[GGQ-PC v0.13.6]')
    if file.endswith('.csproj'):
        t = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.6</Version>', t, count=1)
        t = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.6.0</FileVersion>', t, count=1)
        t = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.6.0</AssemblyVersion>', t, count=1)
    p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.6 login focus + auth recovery applied')
