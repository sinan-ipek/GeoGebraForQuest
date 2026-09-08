from pathlib import Path


p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

old = '''if (-not $runtimeText.Contains("CAPTURE_INTERVAL_MS = 33")) { throw "v0.13.27 doğrulaması: 33 ms raw cadence eksik." }'''
new = '''if (-not $runtimeText.Contains("CAPTURE_INTERVAL_MS = 16")) { throw "v0.13.27 doğrulaması: 16 ms LEFT-only raw cadence eksik." }'''

if old not in s:
    raise SystemExit('v0.13.27 buildfix: legacy 33 ms raw cadence validation missing')

s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

print('v0.13.27 build validation cadence updated to 16 ms LEFT-only path')
