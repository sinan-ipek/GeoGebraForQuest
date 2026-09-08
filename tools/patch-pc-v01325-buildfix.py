from pathlib import Path

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

# v0.13.24's validation contains an escaped regex literal, so the normal label
# replacement in patch-pc-v01325.py does not catch it.
s = s.replace(r'0\.13\.24-raw-arraybuffer', r'0\.13\.25-stereo-proof')
s = s.replace(r'0\.13\.24', r'0\.13\.25')

p.write_text(s, encoding='utf-8')
print('v0.13.25 cache-buster build validation fixed')
