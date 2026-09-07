from pathlib import Path

p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')
if '#include <iostream>' not in s:
    marker = '#include <iomanip>\n'
    if marker in s:
        s = s.replace(marker, marker + '#include <iostream>\n', 1)
    else:
        s = '#include <iostream>\n' + s
p.write_text(s, encoding='utf-8')
print('v0.13.22 XR telemetry iostream include applied')
