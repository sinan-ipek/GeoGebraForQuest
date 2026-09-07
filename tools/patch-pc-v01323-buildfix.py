from pathlib import Path


def replace_block_containing(text: str, token: str, replacement: str, label: str) -> str:
    pos = text.find(token)
    if pos < 0:
        raise SystemExit(f'v0.13.23 buildfix: {label} token missing')
    start = text.rfind('\nif (', 0, pos)
    if start < 0:
        if text.startswith('if ('):
            start = 0
        else:
            raise SystemExit(f'v0.13.23 buildfix: {label} block start missing')
    else:
        start += 1
    end = text.find('\n}', pos)
    if end < 0:
        raise SystemExit(f'v0.13.23 buildfix: {label} block end missing')
    end += 2
    if end < len(text) and text[end] == '\n':
        end += 1
    return text[:start] + replacement + text[end:]


p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

s = replace_block_containing(
    s,
    'Parallel\\.Invoke',
    '''if ($inputText -match "DecodeDataUrl" -or $inputText -match "QueueStereoFrames") {
    throw "v0.13.23 doğrulaması başarısız: eski JPEG/DataURL decode yolu hâlâ mevcut."
}
if ($graphicsText -notmatch "CaptureStereoRawPhaseLocked" -or
    $graphicsText -notmatch "MapSubresource" -or
    $writerText -notmatch "WriteRawSbs") {
    throw "v0.13.23 doğrulaması başarısız: raw SBS GPU/readback yolu eksik."
}
''',
    'parallel decode validation')

s = replace_block_containing(
    s,
    'CAPTURE_JPEG_QUALITY',
    '''if ($runtimeText -notmatch "QUEST3_PPD = 25\\.0" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1536" -or
    $runtimeText -notmatch "CAPTURE_INTERVAL_MS = 33" -or
    $runtimeText -notmatch "js-stereo-raw") {
    throw "v0.13.23 doğrulaması başarısız: Quest-bazlı raw B parametreleri eksik."
}
''',
    'JPEG quality validation')

s = replace_block_containing(
    s,
    'canvas\\.toBlob',
    '''if ($runtimeText -match "canvas\\.toBlob" -or
    $runtimeText -match "image/jpeg" -or
    $runtimeText -match "bridgeStereoEyes") {
    throw "v0.13.23 doğrulaması başarısız: JPEG/Base64 stereo yolu tamamen kaldırılmamış."
}
''',
    'toBlob validation')

s = s.replace('[GGQ-PC v0.12.3]', '[GGQ-PC v0.13.23]')
s = s.replace('[GGQ-PC v0.13]', '[GGQ-PC v0.13.23]')
s = s.replace('[GGQ-PC v0.13.21]', '[GGQ-PC v0.13.23]')
s = s.replace('[GGQ-PC v0.13.22]', '[GGQ-PC v0.13.23]')
s = s.replace("B XR:   Quest angular-density source; 640..1536 px/göz; A'nın 2 cm arkasında",
              'B XR:   no-JPEG raw SBS; GPU crop + staging readback + mevcut XR SBS consumer')

p.write_text(s, encoding='utf-8')
print('v0.13.23 build validation updated for no-JPEG raw SBS')
