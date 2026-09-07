from pathlib import Path

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

old_parallel = '''if ($inputText -notmatch "Parallel\\.Invoke") {
    throw "v0.12.3 doğrulaması başarısız: paralel L/R decode korunmuyor."
}
'''
new_parallel = '''if ($inputText -match "DecodeDataUrl" -or $inputText -match "QueueStereoFrames") {
    throw "v0.13.23 doğrulaması başarısız: eski JPEG/DataURL decode yolu hâlâ mevcut."
}
if ($graphicsText -notmatch "CaptureStereoRawPhaseLocked" -or
    $graphicsText -notmatch "MapSubresource" -or
    $writerText -notmatch "WriteRawSbs") {
    throw "v0.13.23 doğrulaması başarısız: raw SBS GPU/readback yolu eksik."
}
'''
if old_parallel not in s:
    raise SystemExit('v0.13.23 buildfix: parallel decode validation marker missing')
s = s.replace(old_parallel, new_parallel, 1)

old_quality = '''if ($runtimeText -notmatch "QUEST3_PPD = 25\\.0" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1536" -or
    $runtimeText -notmatch "CAPTURE_JPEG_QUALITY = 0\\.99") {
    throw "v0.12.3 doğrulaması başarısız: Quest-bazlı B kalite parametreleri eksik."
}
'''
new_quality = '''if ($runtimeText -notmatch "QUEST3_PPD = 25\\.0" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1536" -or
    $runtimeText -notmatch "CAPTURE_INTERVAL_MS = 33" -or
    $runtimeText -notmatch "js-stereo-raw") {
    throw "v0.13.23 doğrulaması başarısız: Quest-bazlı raw B parametreleri eksik."
}
'''
if old_quality not in s:
    raise SystemExit('v0.13.23 buildfix: JPEG quality validation marker missing')
s = s.replace(old_quality, new_quality, 1)

old_blob = '''if ($runtimeText -notmatch "canvas\\.toBlob") {
    throw "v0.12.3 doğrulaması başarısız: async stereo JPEG yolu eksik."
}
'''
new_blob = '''if ($runtimeText -match "canvas\\.toBlob" -or
    $runtimeText -match "image/jpeg" -or
    $runtimeText -match "bridgeStereoEyes") {
    throw "v0.13.23 doğrulaması başarısız: JPEG/Base64 stereo yolu tamamen kaldırılmamış."
}
'''
if old_blob not in s:
    raise SystemExit('v0.13.23 buildfix: toBlob validation marker missing')
s = s.replace(old_blob, new_blob, 1)

# Keep the pooled legacy writer check harmlessly; WriteRawSbs coexists with the old
# method for protocol compatibility. Update visible build labels only.
s = s.replace('[GGQ-PC v0.12.3]', '[GGQ-PC v0.13.23]')
s = s.replace('B XR:   Quest angular-density source; 640..1536 px/göz; A\'nın 2 cm arkasında',
              'B XR:   no-JPEG raw SBS; GPU crop + staging readback + mevcut XR SBS consumer')

p.write_text(s, encoding='utf-8')
print('v0.13.23 build validation updated for no-JPEG raw SBS')
