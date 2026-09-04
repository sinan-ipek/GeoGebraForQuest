from pathlib import Path
import re

p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')

# Normalize inherited v0.13.9 cache-busting validation to v0.13.10.
t = t.replace('0\\.13\\.9-popup-close-safety', '0\\.13\\.10-auth-return-fix')
t = t.replace('v0.13.9 doğrulaması başarısız', 'v0.13.10 doğrulaması başarısız')
t = t.replace('v0.13.9 doÄŸrulamasÄ± baÅŸarÄ±sÄ±z', 'v0.13.10 doÄŸrulamasÄ± baÅŸarÄ±sÄ±z')

if '0\\.13\\.10-auth-return-fix' not in t:
    raise SystemExit('v0.13.10 build validation guard missing after rewrite')

p.write_text(t, encoding='utf-8')
print('v0.13.10 build validation tag fixed')
