from pathlib import Path
import re

# v0.13.9 runs after v0.13.8. It fixes popup-close teardown and also improves
# the Quest login keyboard requested during testing.

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

# ---------------------------------------------------------------------------
# 1) Add lightweight lifecycle logging so a future failure leaves evidence.
# ---------------------------------------------------------------------------
field_marker = '''    private D3DChromiumWebBrowser? _authPopupBrowser;'''
field_new = '''    private D3DChromiumWebBrowser? _authPopupBrowser;
    private static readonly object AuthTraceLock = new();'''
if field_marker not in t:
    raise SystemExit('auth popup field marker not found')
t = t.replace(field_marker, field_new, 1)

helper_marker = '''    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)
    {'''
helper = '''    private static void AuthTrace(string message)
    {
        try
        {
            lock (AuthTraceLock)
            {
                var path = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuest-auth.log");
                File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{Environment.NewLine}");
            }
        }
        catch { }
    }

    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)
    {'''
if helper_marker not in t:
    raise SystemExit('CreateAuthPopupBrowser marker not found')
t = t.replace(helper_marker, helper, 1)

# Trace popup creation and close handoff.
t = t.replace('''        try
        {
            Size size;''', '''        try
        {
            AuthTrace($"popup-create begin url={targetUrl}");
            Size size;''', 1)

t = t.replace('''            _authPopupBrowser = popup;
            _browser = popup;''', '''            _authPopupBrowser = popup;
            _browser = popup;
            AuthTrace("popup-create success; active surface switched to popup");''', 1)

t = t.replace('''        catch (Exception ex)
        {
            _cefPageText = "CEF popup create: " + ShortError(ex);''', '''        catch (Exception ex)
        {
            AuthTrace("popup-create exception: " + ex);
            _cefPageText = "CEF popup create: " + ShortError(ex);''', 1)

# ---------------------------------------------------------------------------
# 2) Most important crash fix: never Dispose the managed popup wrapper from the
#    OnBeforeClose-derived callback. CEF owns native popup teardown here.
# ---------------------------------------------------------------------------
old_close = '''    private void AuthPopupClosed(IWebBrowser popupWebBrowser)
    {
        BeginInvokeSafe(() =>
        {
            if (_closing) return;
            if (_authPopupBrowser is not null &&
                !ReferenceEquals(_authPopupBrowser, popupWebBrowser)) return;

            var oldPopup = _authPopupBrowser;
            _authPopupBrowser = null;
            _browser = _rootBrowser;
            SetStereoUiSuspended(false);

            try
            {
                var host = _rootBrowser?.GetBrowserHost();
                host?.WasHidden(false);
                host?.SetFocus(true);
                host?.Invalidate(PaintElementType.View);
            }
            catch { }

            try { oldPopup?.Dispose(); } catch { }
            _cefPageText = "CEF GeoGebra · giriş penceresi kapandı";
            UpdateWindowTitle();
        });
    }'''
new_close = '''    private void AuthPopupClosed(IWebBrowser popupWebBrowser)
    {
        AuthTrace("popup-close callback received");
        BeginInvokeSafe(() =>
        {
            try
            {
                if (_closing) return;
                if (_authPopupBrowser is not null &&
                    !ReferenceEquals(_authPopupBrowser, popupWebBrowser))
                {
                    AuthTrace("popup-close ignored: stale popup instance");
                    return;
                }

                // Do not Dispose popupWebBrowser here. OnBeforeClose means CEF is
                // already destroying its native browser. Disposing the wrapper from
                // this path can re-enter native teardown and crash the whole process.
                _authPopupBrowser = null;
                _browser = _rootBrowser;
                SetStereoUiSuspended(false);

                var host = _rootBrowser?.GetBrowserHost();
                if (host is not null)
                {
                    host.WasHidden(false);
                    host.SetFocus(true);
                    host.Invalidate(PaintElementType.View);
                }

                _cefPageText = "CEF GeoGebra · giriş tamamlandı";
                UpdateWindowTitle();
                AuthTrace("popup-close complete; root surface restored");
            }
            catch (Exception ex)
            {
                AuthTrace("popup-close restore exception: " + ex);
                _cefPageText = "CEF popup dönüş: " + ShortError(ex);
                UpdateWindowTitle();
            }
        });
    }'''
if old_close not in t:
    raise SystemExit('v0.13.8 AuthPopupClosed block not found')
t = t.replace(old_close, new_close, 1)

# During final app shutdown, close popup first but do not Dispose it separately.
old_shutdown = '''        try
        {
            _authPopupBrowser?.GetBrowserHost()?.CloseBrowser(true);
            _authPopupBrowser?.Dispose();
        }
        catch { }'''
new_shutdown = '''        try
        {
            _authPopupBrowser?.GetBrowserHost()?.CloseBrowser(true);
        }
        catch { }'''
if old_shutdown not in t:
    raise SystemExit('v0.13.8 popup shutdown block not found')
t = t.replace(old_shutdown, new_shutdown, 1)

# ---------------------------------------------------------------------------
# 3) Quest keyboard UX.
#    - audible click for every key
#    - TAB focuses next editable field
#    - desktop-style numeric keypad on the right (7-8-9 / 4-5-6 / 1-2-3 / 0)
#    - @ and . always available in ABC mode
#    - one-tap common email suffixes
# ---------------------------------------------------------------------------
old_key = '''              function key(label, value, wide) {
                var b=document.createElement('button');
                b.type='button'; b.textContent=label;
                b.style.cssText='min-width:'+(wide?'92':'48')+'px;height:48px;margin:4px;padding:0 10px;'+
                  'border:1px solid #52606d;border-radius:9px;background:#27313d;color:white;font-size:20px;font-weight:600;';
                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });
                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); value(); });
                return b;
              }'''
new_key = '''              function playKeyTone(){
                try{
                  var C=window.AudioContext||window.webkitAudioContext; if(!C) return;
                  window.__ggqAudio=window.__ggqAudio||new C();
                  var ctx=window.__ggqAudio, osc=ctx.createOscillator(), gain=ctx.createGain();
                  osc.type='square'; osc.frequency.value=720; gain.gain.value=.025;
                  osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime+.028);
                }catch(_){}
              }
              function key(label, value, wide, extraStyle) {
                var b=document.createElement('button');
                b.type='button'; b.textContent=label;
                b.style.cssText='min-width:'+(wide?'92':'48')+'px;height:48px;margin:4px;padding:0 10px;'+
                  'border:1px solid #52606d;border-radius:9px;background:#27313d;color:white;font-size:20px;font-weight:600;'+(extraStyle||'');
                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });
                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); playKeyTone(); value(); });
                return b;
              }'''
if old_key not in t:
    raise SystemExit('keyboard key() function not found')
t = t.replace(old_key, new_key, 1)

render_pattern = re.compile(r"              function render\(\) \{.*?              render\(\);", re.S)
m = render_pattern.search(t)
if not m:
    raise SystemExit('keyboard render() block not found')
new_render = '''              function render() {
                rows.textContent='';
                rows.style.cssText='display:flex;align-items:stretch;justify-content:center;gap:10px;';

                var main=document.createElement('div');
                main.style.cssText='flex:1;min-width:0;text-align:center;';
                var layouts = symbols ? [
                  ['!','@','#','$','%','^','&','*','(',')'],
                  ['-','_','=','+','[',']','{','}','/','\\\\'],
                  ['.',',',';',':','?','\\\'', '"','<','>','|']
                ] : [
                  ['q','w','e','r','t','y','u','i','o','p'],
                  ['a','s','d','f','g','h','j','k','l'],
                  ['z','x','c','v','b','n','m'],
                  ['@','.','-','_']
                ];
                layouts.forEach(function(row){
                  var d=document.createElement('div'); d.style.textAlign='center';
                  row.forEach(function(ch){
                    var out=(!symbols && shift)?ch.toUpperCase():ch;
                    d.appendChild(key(out,function(){insertText(out);},false));
                  }); main.appendChild(d);
                });

                var quick=document.createElement('div'); quick.style.textAlign='center';
                quick.appendChild(key('@gmail.com',function(){insertText('@gmail.com');},true,'font-size:17px;min-width:132px;'));
                quick.appendChild(key('@yahoo.com',function(){insertText('@yahoo.com');},true,'font-size:17px;min-width:132px;'));
                quick.appendChild(key('@outlook.com',function(){insertText('@outlook.com');},true,'font-size:17px;min-width:142px;'));
                main.appendChild(quick);

                var actions=document.createElement('div'); actions.style.textAlign='center';
                actions.appendChild(key(shift?'SHIFT ✓':'SHIFT',function(){shift=!shift;render();},true));
                actions.appendChild(key(symbols?'ABC':'#+=',function(){symbols=!symbols;render();},true));
                actions.appendChild(key('SPACE',function(){insertText(' ');},true));
                actions.appendChild(key('⌫',backspace,true));
                actions.appendChild(key('TAB',focusNext,true));
                actions.appendChild(key('ENTER',pressEnter,true));
                actions.appendChild(key('HIDE',function(){root.style.display='none';},true));
                main.appendChild(actions);
                rows.appendChild(main);

                // Real-keyboard-style numeric keypad at the right side.
                var num=document.createElement('div');
                num.style.cssText='width:190px;border-left:1px solid #52606d;padding-left:8px;display:flex;flex-direction:column;justify-content:center;';
                [['7','8','9'],['4','5','6'],['1','2','3']].forEach(function(row){
                  var d=document.createElement('div'); d.style.cssText='display:flex;justify-content:center;';
                  row.forEach(function(ch){ d.appendChild(key(ch,function(){insertText(ch);},false,'min-width:52px;')); });
                  num.appendChild(d);
                });
                var last=document.createElement('div'); last.style.cssText='display:flex;justify-content:center;';
                last.appendChild(key('0',function(){insertText('0');},true,'min-width:112px;'));
                last.appendChild(key('.',function(){insertText('.');},false,'min-width:52px;'));
                num.appendChild(last);
                rows.appendChild(num);
              }
              render();'''
t = t[:m.start()] + new_render + t[m.end():]

# ---------------------------------------------------------------------------
# 4) Version labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.8-real-auth-popup', '0.13.9-popup-close-safety')
    s = s.replace(r'0\\.13\\.8-real-auth-popup', r'0\\.13\\.9-popup-close-safety')
    s = s.replace('v0.13.8 ·', 'v0.13.9 ·')
    s = s.replace('[GGQ-PC v0.13.8]', '[GGQ-PC v0.13.9]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.9</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.9.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.9.0</AssemblyVersion>', s, count=1)
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.9 popup close safety + keyboard UX applied')
