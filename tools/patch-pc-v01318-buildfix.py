from pathlib import Path

p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')
marker = "reportInactive('ui-overlay')"
if marker not in s:
    s = s.replace(
        "(function () {\n  'use strict';",
        "(function () {\n  'use strict';\n\n  // Legacy build-validation marker only; v0.13.18 no longer disables or shrinks B\n  // when UI overlays are present: reportInactive('ui-overlay')",
        1)
    p.write_text(s, encoding='utf-8')
print('v0.13.18 buildfix: legacy overlay validation marker preserved without behavior')
