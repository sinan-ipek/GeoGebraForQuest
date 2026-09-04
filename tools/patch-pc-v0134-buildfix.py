from pathlib import Path
import re

# Force the runtime cache-busting tag to the actual v0.13.4 package version.
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
t, n = re.subn(
    r'pc-stereo-layout\.js\?v=[^"\r\n]+',
    'pc-stereo-layout.js?v=0.13.4-login-keyboard-cursor',
    t,
    count=1,
)
if n != 1:
    raise SystemExit('PcStereoRuntimeUrl cache-busting tag not found')
p.write_text(t, encoding='utf-8')

# Old build.ps1 validators were inherited from v0.12/v0.13.x. Replace only the
# cache-busting guard; all other architecture/quality checks remain intact.
p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
pattern = re.compile(
    r'if \(\$mainFormText -notmatch "[^"]+"\) \{\s*'
    r'throw "[^"]*stereo runtime cache-busting[^"]*"\s*\}',
    re.MULTILINE,
)
replacement = '''if ($mainFormText -notmatch "0\\.13\\.4-login-keyboard-cursor") {
    throw "v0.13.4 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}'''
t, n = pattern.subn(replacement, t, count=1)
if n != 1:
    raise SystemExit('build.ps1 stereo runtime cache-busting guard not found')
p.write_text(t, encoding='utf-8')

print('v0.13.4 cache-busting build validation fixed')
