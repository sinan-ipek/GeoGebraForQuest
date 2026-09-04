from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

# --- popup close safety ---
if 'try { oldPopup?.Dispose(); } catch { }' not in t:
    raise SystemExit('unsafe popup dispose marker not found')
t = t.replace('            var oldPopup = _authPopupBrowser;\n', '', 1)
t = t.replace('            try { oldPopup?.Dispose(); } catch { }\n', '', 1)
t = t.replace('            _authPopupBrowser?.Dispose();\n', '', 1)

# Lightweight auth lifecycle trace.
field = '    private D3DChromiumWebBrowser? _authPopupBrowser;'
if field not in t:
    raise SystemExit('auth popup field missing')
t = t.replace(field, field + '\n    private static readonly object AuthTraceLock = new();', 1)

marker = '    private IWebBrowser? CreateAuthPopupBrowser(string targetUrl)\n    {'
if marker not in t:
    raise SystemExit('CreateAuthPopupBrowser marker missing')
helper = '''    private static void AuthTrace(string message)\n    {\n        try\n        {\n            lock (AuthTraceLock)\n            {\n                var path = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuest-auth.log");\n                File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{Environment.NewLine}");\n            }\n        }\n        catch { }\n    }\n\n'''
t = t.replace(marker, helper + marker, 1)

t = t.replace('    private void AuthPopupClosed(IWebBrowser popupWebBrowser)\n    {\n',
              '    private void AuthPopupClosed(IWebBrowser popupWebBrowser)\n    {\n        AuthTrace("popup-close callback received");\n', 1)
t = t.replace('            _cefPageText = "CEF GeoGebra · giriş penceresi kapandı";\n            UpdateWindowTitle();',
              '            _cefPageText = "CEF GeoGebra · giriş tamamlandı";\n            UpdateWindowTitle();\n            AuthTrace("popup-close complete; root surface restored");', 1)

# --- keyboard sound ---
old_key = '''              function key(label, value, wide) {\n                var b=document.createElement('button');\n                b.type='button'; b.textContent=label;\n                b.style.cssText='min-width:'+(wide?'92':'48')+'px;height:48px;margin:4px;padding:0 10px;'+\n                  'border:1px solid #52606d;border-radius:9px;background:#27313d;color:white;font-size:20px;font-weight:600;';\n                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });\n                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); value(); });\n                return b;\n              }'''
new_key = '''              function playKeyTone(){\n                try{\n                  var C=window.AudioContext||window.webkitAudioContext; if(!C) return;\n                  window.__ggqAudio=window.__ggqAudio||new C();\n                  var ctx=window.__ggqAudio, osc=ctx.createOscillator(), gain=ctx.createGain();\n                  osc.type='square'; osc.frequency.value=720; gain.gain.value=.025;\n                  osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime+.028);\n                }catch(_){}\n              }\n              function key(label, value, wide, extraStyle) {\n                var b=document.createElement('button');\n                b.type='button'; b.textContent=label;\n                b.style.cssText='min-width:'+(wide?'92':'48')+'px;height:48px;margin:4px;padding:0 10px;'+\n                  'border:1px solid #52606d;border-radius:9px;background:#27313d;color:white;font-size:20px;font-weight:600;'+(extraStyle||'');\n                b.addEventListener('pointerdown',function(e){ e.preventDefault(); e.stopPropagation(); });\n                b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); playKeyTone(); value(); });\n                return b;\n              }'''
if old_key not in t:
    raise SystemExit('keyboard key function missing')
t = t.replace(old_key, new_key, 1)

# --- keyboard layout ---
pat = re.compile(r"              function render\(\) \{.*?              render\(\);", re.S)
m = pat.search(t)
if not m:
    raise SystemExit('keyboard render block missing')
new_render = '''              function render() {\n                rows.textContent='';\n                rows.style.cssText='display:flex;align-items:stretch;justify-content:center;gap:10px;';\n                var main=document.createElement('div');\n                main.style.cssText='flex:1;min-width:0;text-align:center;';\n                var layouts = symbols ? [\n                  ['!','@','#','$','%','^','&','*','(',')'],\n                  ['-','_','=','+','[',']','{','}','/','\\\\'],\n                  ['.',',',';',':','?','\\\'', '"','<','>','|']\n                ] : [\n                  ['q','w','e','r','t','y','u','i','o','p'],\n                  ['a','s','d','f','g','h','j','k','l'],\n                  ['z','x','c','v','b','n','m'],\n                  ['@','.','-','_']\n                ];\n                layouts.forEach(function(row){\n                  var d=document.createElement('div'); d.style.textAlign='center';\n                  row.forEach(function(ch){\n                    var out=(!symbols && shift)?ch.toUpperCase():ch;\n                    d.appendChild(key(out,function(){insertText(out);},false));\n                  }); main.appendChild(d);\n                });\n                var quick=document.createElement('div'); quick.style.textAlign='center';\n                quick.appendChild(key('@gmail.com',function(){insertText('@gmail.com');},true,'font-size:17px;min-width:132px;'));\n                quick.appendChild(key('@yahoo.com',function(){insertText('@yahoo.com');},true,'font-size:17px;min-width:132px;'));\n                quick.appendChild(key('@outlook.com',function(){insertText('@outlook.com');},true,'font-size:17px;min-width:142px;'));\n                main.appendChild(quick);\n                var actions=document.createElement('div'); actions.style.textAlign='center';\n                actions.appendChild(key(shift?'SHIFT ✓':'SHIFT',function(){shift=!shift;render();},true));\n                actions.appendChild(key(symbols?'ABC':'#+=',function(){symbols=!symbols;render();},true));\n                actions.appendChild(key('SPACE',function(){insertText(' ');},true));\n                actions.appendChild(key('⌫',backspace,true));\n                actions.appendChild(key('TAB',focusNext,true));\n                actions.appendChild(key('ENTER',pressEnter,true));\n                actions.appendChild(key('HIDE',function(){root.style.display='none';},true));\n                main.appendChild(actions);\n                rows.appendChild(main);\n                var num=document.createElement('div');\n                num.style.cssText='width:190px;border-left:1px solid #52606d;padding-left:8px;display:flex;flex-direction:column;justify-content:center;';\n                [['7','8','9'],['4','5','6'],['1','2','3']].forEach(function(row){\n                  var d=document.createElement('div'); d.style.cssText='display:flex;justify-content:center;';\n                  row.forEach(function(ch){ d.appendChild(key(ch,function(){insertText(ch);},false,'min-width:52px;')); });\n                  num.appendChild(d);\n                });\n                var last=document.createElement('div'); last.style.cssText='display:flex;justify-content:center;';\n                last.appendChild(key('0',function(){insertText('0');},true,'min-width:112px;'));\n                last.appendChild(key('.',function(){insertText('.');},false,'min-width:52px;'));\n                num.appendChild(last);\n                rows.appendChild(num);\n              }\n              render();'''
t = t[:m.start()] + new_render + t[m.end():]
p.write_text(t, encoding='utf-8')

# Version/build labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    q = Path(file)
    s = q.read_text(encoding='utf-8')
    s = s.replace('0.13.8-real-auth-popup', '0.13.9-popup-close-safety')
    s = s.replace(r'0\\.13\\.8-real-auth-popup', r'0\\.13\\.9-popup-close-safety')
    s = s.replace('v0.13.8 ·', 'v0.13.9 ·')
    s = s.replace('[GGQ-PC v0.13.8]', '[GGQ-PC v0.13.9]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.9</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.9.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.9.0</AssemblyVersion>', s, count=1)
    q.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.9 direct crash + keyboard patch applied')
