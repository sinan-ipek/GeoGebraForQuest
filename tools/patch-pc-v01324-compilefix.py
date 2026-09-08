from pathlib import Path

p = Path('pc-xr/v11-shared.hpp')
s = p.read_text(encoding='utf-8')

old = '''        int rowPitch,
        int pixelFormat) {
'''
new = '''        int rowPitch,
        int pixelFormat = 1) {
'''

if old not in s:
    raise SystemExit('v0.13.24 compilefix: SourceTexture::Upload pixelFormat signature missing')

s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

print('v0.13.24 compilefix: SourceTexture::Upload keeps legacy 6-argument callers')
