from pathlib import Path

p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
old = '0\\.13\\.8-real-auth-popup'
new = '0\\.13\\.9-popup-close-safety'
if old not in t:
    raise SystemExit('v0.13.8 build validation tag not found')
t = t.replace(old, new)
t = t.replace('v0.13.8 doğrulaması başarısız', 'v0.13.9 doğrulaması başarısız')
p.write_text(t, encoding='utf-8')
print('v0.13.9 build validation tag fixed')
