from pathlib import Path

# v0.13.22 validation-label compatibility patch.
# This commit also retriggers CI after a transient GitHub/OpenXR SDK 504.
p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(r'0\.13\.21-performance-telemetry', r'0\.13\.22-performance-stage-timing')
s = s.replace(r'v0\.13\.21', r'v0\.13\.22')
s = s.replace('0.13.21-performance-telemetry', '0.13.22-performance-stage-timing')
s = s.replace('v0.13.21', 'v0.13.22')
p.write_text(s, encoding='utf-8')
print('v0.13.22 legacy build validation labels fixed')
