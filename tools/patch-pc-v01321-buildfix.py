from pathlib import Path

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(r'0\.13\.20-60fps-test', r'0\.13\.21-performance-telemetry')
s = s.replace(r'v0\.13\.20', r'v0\.13\.21')
s = s.replace('v0.13.20', 'v0.13.21')
p.write_text(s, encoding='utf-8')
print('v0.13.21 legacy build validation labels fixed')
