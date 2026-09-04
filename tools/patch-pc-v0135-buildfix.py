from pathlib import Path
import re

# v0.13.4 buildfix installs a strict cache-busting validator. Move that validator
# to the v0.13.5 runtime tag after the v0.13.5 patch has updated MainFormV11.cs.
p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
pattern = re.compile(
    r'if \(\$mainFormText -notmatch "[^"]*0\\\.13\\\.4-login-keyboard-cursor[^"]*"\) \{\s*'
    r'throw "[^"]*stereo runtime cache-busting[^"]*"\s*\}',
    re.MULTILINE,
)
replacement = '''if ($mainFormText -notmatch "0\\.13\\.5-cursor-keyboard-fix") {
    throw "v0.13.5 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}'''
t, n = pattern.subn(replacement, t, count=1)
if n != 1:
    # Fallback for slightly different escaping from earlier validators.
    pattern2 = re.compile(
        r'if \(\$mainFormText -notmatch "[^"]+"\) \{\s*'
        r'throw "[^"]*stereo runtime cache-busting[^"]*"\s*\}',
        re.MULTILINE,
    )
    t, n = pattern2.subn(replacement, t, count=1)
if n != 1:
    raise SystemExit('v0.13.5 cache-busting validator not found')
p.write_text(t, encoding='utf-8')
print('v0.13.5 build validation tag fixed')
