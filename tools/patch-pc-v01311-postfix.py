from pathlib import Path
import re

main = Path('pc/MainFormV11.cs')
t = main.read_text(encoding='utf-8')

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

# Force popup JavascriptMessageReceived wiring. Earlier patches can be formatted
# differently, so use a regex anchored on the popup FrameLoadEnd subscription.
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

# Ensure the native key-tone message handler exists. This is intentionally
# idempotent so the postfix repairs older generated code too.
if 'case "keyTone":' not in t:
    marker = '''                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
    replacement = '''                case "keyTone":\n                    _questTonePlayer.PlayClick();\n                    break;\n                case "panelReady":\n                    BeginInvokeSafe(UpdateWindowTitle);\n                    break;'''
    if marker not in t:
        raise SystemExit('could not insert native keyTone handler')
    t = t.replace(marker, replacement, 1)

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

# Final hard assertions after every write, to prevent a later overwrite in this patch.
final_main = main.read_text(encoding='utf-8')
required = [
    'https://www.geogebra.org/classic',
    'root.MainFrame.LoadUrl(PostLoginClassicUrl);',
    bridge,
    'case "keyTone":',
]
for item in required:
    if item not in final_main:
        raise SystemExit('v0.13.11 postfix final assertion failed: ' + item)

print('v0.13.11 deterministic postfix + popup bridge applied')
