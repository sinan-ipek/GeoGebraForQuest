from pathlib import Path
import re

p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
pattern = re.compile(
    r'if \(\$mainFormText -notmatch "0\\\.13\\\.6-login-focus-recovery"\) \{\s*'
    r'throw "[^"]*stereo runtime cache-busting[^"]*"\s*\}',
    re.MULTILINE,
)
replacement = '''if ($mainFormText -notmatch "0\\.13\\.7-auth-no-close") {
    throw "v0.13.7 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}'''
t, n = pattern.subn(replacement, t, count=1)
if n != 1:
    old = '''if ($mainFormText -notmatch "0\\.13\\.6-login-focus-recovery") {
    throw "v0.13.6 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}'''
    if old not in t:
        raise SystemExit('v0.13.6 build cache-busting guard not found')
    t = t.replace(old, replacement, 1)
p.write_text(t, encoding='utf-8')
print('v0.13.7 build validation tag fixed')
