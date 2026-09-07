from pathlib import Path

p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')
if '#include <iomanip>' not in s:
    marker = '#include "v11-render.hpp"\n'
    if marker in s:
        s = s.replace(marker, marker + '#include <iomanip>\n', 1)
    else:
        s = '#include <iomanip>\n' + s
p.write_text(s, encoding='utf-8')
print('v0.13.21 telemetry compile include applied')
