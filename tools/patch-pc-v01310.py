from pathlib import Path
import re

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')

# Remove every brittle wrapper identity gate. CefSharp can surface a different
# managed IWebBrowser wrapper during teardown for the same native popup.
gate_pattern = re.compile(
    r'\s*if \(_authPopupBrowser is not null &&\s*'
    r'!ReferenceEquals\(_authPopupBrowser, popupWebBrowser\)\) return;\s*',
    re.MULTILINE,
)
t, gate_count = gate_pattern.subn('\n', t)
if gate_count < 1:
    raise SystemExit('v0.13.9 auth wrapper identity gate not found')
if 'ReferenceEquals(_authPopupBrowser, popupWebBrowser)' in t:
    raise SystemExit('stale popup wrapper identity gate remains after cleanup')

# Replace the popup-close body with step-by-step restore + root reload using the
# shared RequestContext. Reloading local GeoGebra makes the newly authenticated
# session visible to the app immediately.
old_body = '''            _authPopupBrowser = null;\n            _browser = _rootBrowser;\n            SetStereoUiSuspended(false);\n\n            try\n            {\n                var host = _rootBrowser?.GetBrowserHost();\n                host?.WasHidden(false);\n                host?.SetFocus(true);\n                host?.Invalidate(PaintElementType.View);\n            }\n            catch { }\n\n            _cefPageText = \"CEF GeoGebra · giriş tamamlandı\";\n            UpdateWindowTitle();\n            AuthTrace(\"popup-close complete; root surface restored\");'''
new_body = '''            AuthTrace("popup-close step 1: clearing popup reference");\n            _authPopupBrowser = null;\n\n            AuthTrace("popup-close step 2: assigning root browser");\n            _browser = _rootBrowser;\n\n            AuthTrace("popup-close step 3: resuming stereo UI");\n            SetStereoUiSuspended(false);\n\n            try\n            {\n                var root = _rootBrowser?.GetBrowser();\n                var host = root?.GetHost();\n\n                AuthTrace("popup-close step 4: WasHidden(false)");\n                host?.WasHidden(false);\n\n                AuthTrace("popup-close step 5: SetFocus(true)");\n                host?.SetFocus(true);\n\n                AuthTrace("popup-close step 6: Invalidate(View)");\n                host?.Invalidate(PaintElementType.View);\n\n                if (root is not null)\n                {\n                    AuthTrace("popup-close step 7: reloading local GeoGebra with shared auth session");\n                    root.MainFrame.LoadUrl(LocalAppUrl);\n                }\n                else\n                {\n                    AuthTrace("popup-close ERROR: root browser is null");\n                }\n            }\n            catch (Exception ex)\n            {\n                AuthTrace("popup-close restore ERROR: " + ex.GetType().Name + ": " + ex.Message);\n            }\n\n            _cefPageText = \"CEF GeoGebra · girişten dönüldü\";\n            UpdateWindowTitle();\n            AuthTrace(\"popup-close complete; root surface restored and reloaded\");'''
if old_body not in t:
    raise SystemExit('v0.13.9 popup-close restore body not found')
t = t.replace(old_body, new_body, 1)
p.write_text(t, encoding='utf-8')

# Version labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    q = Path(file)
    s = q.read_text(encoding='utf-8')
    s = s.replace('0.13.9-popup-close-safety', '0.13.10-auth-return-fix')
    s = s.replace(r'0\\.13\\.9-popup-close-safety', r'0\\.13\\.10-auth-return-fix')
    s = s.replace('v0.13.9 ·', 'v0.13.10 ·')
    s = s.replace('[GGQ-PC v0.13.9]', '[GGQ-PC v0.13.10]')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.10</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.10.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.10.0</AssemblyVersion>', s, count=1)
    q.write_text(s, encoding='utf-8')

print(f'GeoGebraForQuest PC v0.13.10 auth return fix applied; removed {gate_count} identity gate(s)')
