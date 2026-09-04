from pathlib import Path
import re

main = Path('pc/MainFormV11.cs')
t = main.read_text(encoding='utf-8')

# Ensure the native Quest tone player field exists before any keyTone handler uses it.
tone_field = '    private readonly QuestTonePlayer _questTonePlayer = new();'
if tone_field not in t:
    anchor = '    private readonly XrCompanionManager _xrCompanion = new();'
    if anchor not in t:
        raise SystemExit('could not find field anchor for QuestTonePlayer')
    t = t.replace(anchor, anchor + '\n' + tone_field, 1)

# Ensure canonical post-login Classic constant exists, regardless of earlier patch formatting.
if 'PostLoginClassicUrl' not in t:
    pat = r'(private const string LocalAppUrl\s*=\s*"https://appassets\.androidplatform\.net/assets/web/index\.html";)'
    t, n = re.subn(pat, r'\1\n    private const string PostLoginClassicUrl = "https://www.geogebra.org/classic";', t, count=1)
    if n != 1:
        raise SystemExit('could not insert PostLoginClassicUrl')

# Force the auth-return navigation to Classic.
method = re.search(r'private void AuthPopupClosed\(IWebBrowser popupWebBrowser\).*?private void BrowserFrameLoadEnd', t, re.S)
if not method:
    raise SystemExit('AuthPopupClosed method not found')
block = method.group(0)
block2 = block.replace('root.MainFrame.LoadUrl(LocalAppUrl);', 'root.MainFrame.LoadUrl(PostLoginClassicUrl);')
if 'root.MainFrame.LoadUrl(PostLoginClassicUrl);' not in block2:
    raise SystemExit('post-login Classic navigation missing')
t = t[:method.start()] + block2 + t[method.end():]

# Force popup JavascriptMessageReceived wiring.
bridge = 'popup.JavascriptMessageReceived += BrowserJavascriptMessageReceived;'
if bridge not in t:
    t, n = re.subn(
        r'(\s*popup\.FrameLoadEnd\s*\+=\s*BrowserFrameLoadEnd\s*;)',
        r'\1\n            popup.JavascriptMessageReceived += BrowserJavascriptMessageReceived;',
        t,
        count=1,
    )
    if n != 1:
        raise SystemExit('could not insert popup JavascriptMessageReceived bridge')

# Ensure native key-tone handler exists.
if 'case "keyTone":' not in t:
    marker = '''                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
    replacement = '''                case "keyTone":\n                    _questTonePlayer.PlayClick();\n                    break;\n                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
    if marker not in t:
        raise SystemExit('could not insert native keyTone handler')
    t = t.replace(marker, replacement, 1)

# Force common punctuation into the ABC layout, regardless of whitespace/formatting.
if "['@','.','!','-','_']" not in t:
    t, n = re.subn(
        r"\[\s*'@'\s*,\s*'\.'\s*,\s*'-'\s*,\s*'_'\s*\]",
        "['@','.','!','-','_']",
        t,
        count=1,
    )
    if n != 1:
        raise SystemExit('could not insert ABC punctuation row')

# Force compact letter/numpad spacing.
if 'max-width:1040px' not in t:
    t, n = re.subn(
        r"rows\.style\.cssText='display:flex;align-items:stretch;justify-content:center;gap:\d+px;'",
        "rows.style.cssText='display:flex;align-items:stretch;justify-content:center;gap:2px;max-width:1040px;margin:0 auto;'",
        t,
        count=1,
    )
    if n != 1:
        raise SystemExit('could not compact keyboard rows')

t = t.replace("main.style.cssText='flex:1;min-width:0;text-align:center;'",
              "main.style.cssText='flex:0 1 auto;min-width:0;text-align:center;'", 1)
t = re.sub(
    r"num\.style\.cssText='width:\d+px;border-left:1px solid #52606d;padding-left:\d+px;display:flex;flex-direction:column;justify-content:center;'",
    "num.style.cssText='width:176px;border-left:1px solid #52606d;padding-left:2px;margin-left:0;display:flex;flex-direction:column;justify-content:center;'",
    t,
    count=1,
)

# Force a clearly visible text caret for all editable fields.
if 'caret-color:#00ddf5' not in t:
    install_marker = '              window.__ggqVrKeyboardInstalled = true;'
    caret_css = '''              window.__ggqVrKeyboardInstalled = true;\n              var caretStyle=document.createElement('style');\n              caretStyle.textContent='input:focus,textarea:focus,[contenteditable=true]:focus{caret-color:#00ddf5 !important;}';\n              (document.head||document.documentElement).appendChild(caretStyle);'''
    if install_marker not in t:
        raise SystemExit('could not find keyboard install marker for caret CSS')
    t = t.replace(install_marker, caret_css, 1)

# Version labels, project version and build output/validation tags.
main.write_text(t, encoding='utf-8')

for file in ('pc/MainFormV11.cs','pc/GeoGebraForQuest.PC.csproj','pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.10-auth-return-fix','0.13.11-keyboard-classic-splash')
    s = s.replace(r'0\.13\.10-auth-return-fix', r'0\.13\.11-keyboard-classic-splash')
    s = s.replace('v0.13.10','v0.13.11')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.11</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.11.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.11.0</AssemblyVersion>', s, count=1)
    if file.endswith('build.ps1'):
        s = re.sub(r'GeoGebraForQuest-PC-v[^"\r\n]+-win-x64', 'GeoGebraForQuest-PC-v0.13.11-keyboard-classic-splash-win-x64', s, count=1)
        s = s.replace('0\\.13\\.10-auth-return-fix','0\\.13\\.11-keyboard-classic-splash')
        s = s.replace('v0.13.10 doğrulaması başarısız','v0.13.11 doğrulaması başarısız')
        s = s.replace('v0.13.10 doÄŸrulamasÄ± baÅŸarÄ±sÄ±z','v0.13.11 doÄŸrulamasÄ± baÅŸarÄ±sÄ±z')
    p.write_text(s, encoding='utf-8')

# Final hard assertions.
final_main = main.read_text(encoding='utf-8')
required = [
    tone_field,
    'https://www.geogebra.org/classic',
    'root.MainFrame.LoadUrl(PostLoginClassicUrl);',
    bridge,
    'case "keyTone":',
    "['@','.','!','-','_']",
    'max-width:1040px',
    'caret-color:#00ddf5',
]
for item in required:
    if item not in final_main:
        raise SystemExit('v0.13.11 postfix final assertion failed: ' + item)

print('v0.13.11 deterministic postfix + Quest tone field + popup bridge + compact punctuation layout + visible caret applied')
