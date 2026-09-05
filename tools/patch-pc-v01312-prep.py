from pathlib import Path

p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')

old = '''    PanelRect MakeBaseRect() const {
        // Physical XR geometry is invariant. CEF texture size, DPI, popup/login
        // surfaces and desktop window resizes are presentation details only.
        return {
            -kScreenWidthMeters * 0.5f,
             kScreenWidthMeters * 0.5f,
             kScreenHeightMeters * 0.5f,
            -kScreenHeightMeters * 0.5f
        };
    }'''

new = '''    PanelRect MakeBaseRect() const {
        const int width = std::max(1, baseTexture_.Width());
        const int height = std::max(1, baseTexture_.Height());
        // Physical XR geometry is invariant. The width/height locals are kept
        // only so the v0.13.12 splash patch can attach optional splash dimensions
        // without changing the proven fixed-surface geometry below.
        (void)width;
        (void)height;
        return {
            -kScreenWidthMeters * 0.5f,
             kScreenWidthMeters * 0.5f,
             kScreenHeightMeters * 0.5f,
            -kScreenHeightMeters * 0.5f
        };
    }'''

if old not in t:
    raise SystemExit('v0.13.12 prep: fixed MakeBaseRect block missing')

p.write_text(t.replace(old, new, 1), encoding='utf-8')
print('v0.13.12 prep: MakeBaseRect compatibility marker inserted')
