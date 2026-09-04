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

# Version labels, project version and build output/validation tags.
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

main.write_text(t, encoding='utf-8')
print('v0.13.11 deterministic postfix applied')
