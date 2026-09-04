from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

old = """            popup.FrameLoadEnd += BrowserFrameLoadEnd;\n            popup.LoadError += (_, args) =>"""
new = """            popup.FrameLoadEnd += BrowserFrameLoadEnd;\n            popup.JavascriptMessageReceived += BrowserJavascriptMessageReceived;\n            popup.LoadError += (_, args) =>"""
if old not in t:
    raise SystemExit('popup event wiring marker missing')
t = t.replace(old, new, 1)

field = '    private static readonly object AuthTraceLock = new();'
if field not in t:
    raise SystemExit('AuthTraceLock field missing')
t = t.replace(field, field + '\n    private readonly QuestTonePlayer _questTonePlayer = new();', 1)

needle = '''                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
replacement = '''                case "keyTone":\n                    _questTonePlayer.PlayClick();\n                    break;\n                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
if needle not in t:
    raise SystemExit('JS message switch marker missing')
t = t.replace(needle, replacement, 1)

needle = '        _xrMousePointer.Dispose();\n        _xrCompanion.Dispose();'
replacement = '        _xrMousePointer.Dispose();\n        _questTonePlayer.Dispose();\n        _xrCompanion.Dispose();'
if needle not in t:
    raise SystemExit('shutdown dispose marker missing')
t = t.replace(needle, replacement, 1)

start = t.find('        // External sign-in pages are usable without removing the headset.')
if start < 0:
    raise SystemExit('login assist comment missing')
cond = t.find('        if (!e.Url.StartsWith("https://appassets.androidplatform.net/", StringComparison.OrdinalIgnoreCase))', start)
if cond < 0:
    raise SystemExit('external-only keyboard condition missing')
brace = t.find('        {\n            const string loginAssist = """', cond)
if brace < 0:
    raise SystemExit('keyboard condition body start missing')
prefix = t[:cond]
body_start = brace + len('        {\n')
end_marker = '            e.Frame.ExecuteJavaScriptAsync(loginAssist);\n        }\n    }'
end = t.find(end_marker, body_start)
if end < 0:
    raise SystemExit('keyboard wrapper end missing')
body = t[body_start:end] + '            e.Frame.ExecuteJavaScriptAsync(loginAssist);\n'
t = prefix + body + '    }' + t[end+len(end_marker):]

old_style = "rows.style.cssText='display:flex;align-items:stretch;justify-content:center;gap:10px;';"
new_style = "rows.style.cssText='display:flex;align-items:stretch;justify-content:center;gap:2px;max-width:1040px;margin:0 auto;';"
if old_style not in t:
    raise SystemExit('keyboard rows style missing')
t = t.replace(old_style, new_style, 1)

t = t.replace("main.style.cssText='flex:1;min-width:0;text-align:center;';",
              "main.style.cssText='flex:0 1 auto;min-width:0;text-align:center;';", 1)
t = t.replace("['@','.','-','_']", "['@','.','!','-','_']", 1)
t = t.replace("num.style.cssText='width:190px;border-left:1px solid #52606d;padding-left:8px;display:flex;flex-direction:column;justify-content:center;';",
              "num.style.cssText='width:176px;border-left:1px solid #52606d;padding-left:2px;margin-left:0;display:flex;flex-direction:column;justify-content:center;';", 1)

marker = "              function playKeyTone(){\n"
if marker not in t:
    raise SystemExit('playKeyTone function missing')
helper = '''              function postNative(message){\n                try{\n                  if(window.CefSharp && typeof window.CefSharp.PostMessage==='function'){ window.CefSharp.PostMessage(message); return; }\n                  if(window.cefSharp && typeof window.cefSharp.postMessage==='function'){ window.cefSharp.postMessage(message); }\n                }catch(_){}\n              }\n'''
t = t.replace(marker, helper + marker, 1)
old_play_end = "                }catch(_){}\n              }\n              function key(label, value, wide, extraStyle) {"
new_play_end = "                }catch(_){}\n                postNative({type:'keyTone'});\n              }\n              function key(label, value, wide, extraStyle) {"
if old_play_end not in t:
    raise SystemExit('playKeyTone end missing')
t = t.replace(old_play_end, new_play_end, 1)

mark = "                try{\n                  el.style.setProperty('caret-color','#00ddf5','important');"
repl = "                try{\n                  el.style.setProperty('caret-color','#00ddf5','important');\n                  el.style.setProperty('color',getComputedStyle(el).color || '#111','important');"
if mark not in t:
    raise SystemExit('caret style marker missing')
t = t.replace(mark, repl, 1)

install = "              window.__ggqVrKeyboardInstalled = true;\n\n              var active = null, shift = false, symbols = false;"
install_new = """              window.__ggqVrKeyboardInstalled = true;\n              var caretStyle=document.createElement('style');\n              caretStyle.textContent='input:focus,textarea:focus,[contenteditable=true]:focus{caret-color:#00ddf5 !important;}';\n              (document.head||document.documentElement).appendChild(caretStyle);\n\n              var active = null, shift = false, symbols = false;"""
if install not in t:
    raise SystemExit('keyboard install marker missing')
t = t.replace(install, install_new, 1)

classic_const = '    private const string LocalAppUrl = "https://appassets.androidplatform.net/assets/web/index.html";'
classic_new = classic_const + '\n    private const string PostLoginClassicUrl = "https://www.geogebra.org/classic";'
if classic_const not in t:
    raise SystemExit('LocalAppUrl constant missing')
t = t.replace(classic_const, classic_new, 1)
t = t.replace('root.MainFrame.LoadUrl(LocalAppUrl);', 'root.MainFrame.LoadUrl(PostLoginClassicUrl);', 1)
t = t.replace('popup-close step 7: reloading local GeoGebra with shared auth session',
              'popup-close step 7: opening geogebra.org/classic with shared auth session', 1)
t = t.replace('popup-close complete; root surface restored and reloaded',
              'popup-close complete; root surface restored and classic opened', 1)

# Keep QuestBridge/stereo runtime active on the canonical Classic page. Do not
# depend on the exact formatting of the inherited local-app guard; simply insert
# an explicit Classic branch immediately before the keyboard helper section.
classic_marker = '        // External sign-in pages are usable without removing the headset.'
classic_block = '''        if (e.Url.StartsWith("https://www.geogebra.org/classic", StringComparison.OrdinalIgnoreCase) ||\n            e.Url.StartsWith("https://geogebra.org/classic", StringComparison.OrdinalIgnoreCase))\n        {\n            e.Frame.ExecuteJavaScriptAsync(script);\n            try\n            {\n                var runtimePath = Path.Combine(AppContext.BaseDirectory, "pc-stereo-layout.js");\n                if (File.Exists(runtimePath))\n                {\n                    var runtimeSource = File.ReadAllText(runtimePath);\n                    e.Frame.ExecuteJavaScriptAsync(runtimeSource);\n                }\n            }\n            catch (Exception ex)\n            {\n                _cefPageText = "CEF classic runtime: " + ShortError(ex);\n                BeginInvokeSafe(UpdateWindowTitle);\n            }\n        }\n\n'''
if classic_marker not in t:
    raise SystemExit('classic insertion marker missing')
t = t.replace(classic_marker, classic_block + classic_marker, 1)

for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    q = Path(file)
    s = q.read_text(encoding='utf-8')
    s = s.replace('0.13.10-auth-return-fix', '0.13.11-keyboard-classic-splash')
    s = s.replace(r'0\\.13\\.10-auth-return-fix', r'0\\.13\\.11-keyboard-classic-splash')
    s = s.replace('v0.13.10 ·', 'v0.13.11 ·')
    s = s.replace('[GGQ-PC v0.13.10]', '[GGQ-PC v0.13.11]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.11</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.11.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.11.0</AssemblyVersion>', s, count=1)
    q.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.11 keyboard/classic/splash patch applied')
