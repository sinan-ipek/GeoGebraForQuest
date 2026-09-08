from pathlib import Path


def replace_block_containing(text: str, token: str, replacement: str, label: str) -> str:
    pos = text.find(token)
    if pos < 0:
        raise SystemExit(f'v0.13.24 buildfix: {label} token missing')
    start = text.rfind('\nif (', 0, pos)
    if start < 0:
        if text.startswith('if ('):
            start = 0
        else:
            raise SystemExit(f'v0.13.24 buildfix: {label} block start missing')
    else:
        start += 1
    end = text.find('\n}', pos)
    if end < 0:
        raise SystemExit(f'v0.13.24 buildfix: {label} block end missing')
    end += 2
    if end < len(text) and text[end] == '\n':
        end += 1
    return text[:start] + replacement + text[end:]


p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

# Old JPEG quality validation is no longer meaningful. Keep the Quest-density
# geometry checks, and require the new raw transport markers instead.
s = replace_block_containing(
    s,
    'CAPTURE_JPEG_QUALITY',
    '''if ($runtimeText -notmatch "QUEST3_PPD = 25\\.0" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1536" -or
    $runtimeText -notmatch "CAPTURE_INTERVAL_MS = 33" -or
    $runtimeText -notmatch "js-stereo-raw-arraybuffer" -or
    $runtimeText -notmatch "stereoRawSbs" -or
    $runtimeText -notmatch "getImageData" -or
    $runtimeText -notmatch "image\\.data\\.buffer") {
    throw "v0.13.24 doğrulaması başarısız: raw ArrayBuffer B yolu eksik."
}
''',
    'JPEG quality validation')

# In v0.13.24 the presence of toBlob/JPEG is a regression, not a requirement.
s = replace_block_containing(
    s,
    'canvas\\.toBlob',
    '''if ($runtimeText -match "canvas\\.toBlob" -or
    $runtimeText -match "image/jpeg" -or
    $runtimeText -match "bridgeStereoEyes" -or
    $runtimeText -match "stereoGpuPhase" -or
    $runtimeText -match "ggq-pc-raw-left-eye-overlay") {
    throw "v0.13.24 doğrulaması başarısız: eski JPEG veya görünür-kompozit stereo yolu bulundu."
}
if ($mainFormText -notmatch "TryHandleRawStereoMessage" -or
    $mainFormText -notmatch "WriteRawSbsRgba" -or
    $writerText -notmatch "WriteRawSbsRgba" -or
    $sharedText -notmatch "pixelFormat" -or
    $sharedText -notmatch "DXGI_FORMAT_R8G8B8A8_UNORM") {
    throw "v0.13.24 doğrulaması başarısız: host/MMF/XR raw RGBA zinciri eksik."
}
''',
    'toBlob validation')

# Durable labels for the final build transcript.
s = s.replace('[GGQ-PC v0.13.22]', '[GGQ-PC v0.13.24]')
s = s.replace('[GGQ-PC v0.13.21]', '[GGQ-PC v0.13.24]')
s = s.replace('[GGQ-PC v0.12.3]', '[GGQ-PC v0.13.24]')
s = s.replace("B XR:   Quest angular-density source; 640..1536 px/göz; A'nın 2 cm arkasında",
              "B XR:   detached SBS canvas -> RGBA ArrayBuffer -> binary CEF IPC -> raw MMF")

p.write_text(s, encoding='utf-8')
print('v0.13.24 build validation updated for raw ArrayBuffer stereo')
