from pathlib import Path

p = Path('tools/patch-pc-v01318.py')
s = p.read_text(encoding='utf-8')

old_marker = """member_marker = '''    SourceTexture cursorTexture_;
    SourceTexture mouseCursorTexture_;'''"""
new_marker = """member_marker = '''    SourceTexture cursorTexture_;'''"""
if old_marker not in s:
    raise SystemExit('v0.13.18 prep: old cursor member marker missing')
s = s.replace(old_marker, new_marker, 1)

old_replacement = """    '''    SourceTexture cursorTexture_;
    SourceTexture mouseCursorTexture_;
    float cursorHotspotU_{0.0f};
    float cursorHotspotV_{0.0f};
    float cursorAspect_{1.0f};''',"""
new_replacement = """    '''    SourceTexture cursorTexture_;
    float cursorHotspotU_{0.0f};
    float cursorHotspotV_{0.0f};
    float cursorAspect_{1.0f};''',"""
if old_replacement not in s:
    raise SystemExit('v0.13.18 prep: old cursor member replacement missing')
s = s.replace(old_replacement, new_replacement, 1)

p.write_text(s, encoding='utf-8')
print('v0.13.18 prep: cursor member compatibility fixed')
