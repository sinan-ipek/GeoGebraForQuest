from pathlib import Path


# GeoGebraForQuest PC v0.13.28 build validation fix.
# Replace the inherited v0.13.27 one-eye structural validator with checks that
# describe the actual v0.13.28 architecture: A as common UI/base + explicit
# true L and true R 3D patches -> one full A_L|A_R SBS panel.

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

throw_text = 'v0.13.28 doğrulaması başarısız: full A_L/A_R SBS / single panel / quality minification eksik.'
throw_pos = s.find(throw_text)
if throw_pos < 0:
    raise SystemExit('v0.13.28 buildfix: inherited structural validator not found')

block_start = s.rfind('if ($renderText -notmatch ', 0, throw_pos)
if block_start < 0:
    raise SystemExit('v0.13.28 buildfix: structural validator start not found')

block_end = s.find('\n}', throw_pos)
if block_end < 0:
    raise SystemExit('v0.13.28 buildfix: structural validator end not found')
block_end += 2
if block_end < len(s) and s[block_end] == '\n':
    block_end += 1

replacement = '''if ($renderText -notmatch "GGQ v0\\.13\\.28 TRUE A_L/A_R SBS single-panel path" -or
    $renderText -notmatch "class FullSbsComposer" -or
    $renderText -notmatch "0\\.0f, 0\\.0f, 0\\.5f, 1\\.0f" -or
    $renderText -notmatch "0\\.5f, 0\\.0f, 1\\.0f, 1\\.0f" -or
    $renderText -notmatch "rightEye \\? 0\\.5f : 0\\.0f" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.28 doğrulaması başarısız: TRUE L/R A_L|A_R / tek panel / kalite yolu eksik."
}

if ($runtimeText -notmatch "stereoRawPair" -or
    $runtimeText -notmatch "js-al-ar-pair-raw" -or
    $runtimeText -match "stereoRawLeft") {
    throw "v0.13.28 doğrulaması başarısız: TRUE L/R raw IPC yolu eksik veya eski LEFT-only yol geri dönmüş."
}

if ($writerText -notmatch "WriteRawStereoPairRgba" -or
    $writerText -notmatch "_view\\.Write\\(116, 2\\)") {
    throw "v0.13.28 doğrulaması başarısız: TRUE L/R raw SBS MMF yazıcısı eksik."
}

if ($renderText -match "constexpr float behindDistance = kScreenDistanceMeters \\+ 0\\.02f") {
    throw "v0.13.28 doğrulaması başarısız: eski B-behind-A görsel geometrisi geri dönmüş."
}
'''

s = s[:block_start] + replacement + s[block_end:]
p.write_text(s, encoding='utf-8')
print('v0.13.28 exact TRUE A_L/A_R build validation applied')
