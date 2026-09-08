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

# v0.13.24 changes transport only. Do not bind this build check to historical
# Quest-density literals that earlier tuning patches are free to rewrite.
s = replace_block_containing(
    s,
    'CAPTURE_JPEG_QUALITY',
    '''if (-not $runtimeText.Contains("CAPTURE_INTERVAL_MS = 33")) { throw "v0.13.24 doğrulaması: 33 ms raw cadence eksik." }
if (-not $runtimeText.Contains("js-stereo-raw-arraybuffer")) { throw "v0.13.24 doğrulaması: raw telemetry eksik." }
if (-not $runtimeText.Contains("stereoRawSbs")) { throw "v0.13.24 doğrulaması: stereoRawSbs mesajı eksik." }
if (-not $runtimeText.Contains("getImageData")) { throw "v0.13.24 doğrulaması: raw canvas readback eksik." }
if (-not $runtimeText.Contains("image.data.buffer")) { throw "v0.13.24 doğrulaması: ArrayBuffer payload eksik." }
''',
    'JPEG quality validation')

# In v0.13.24 the presence of toBlob/JPEG is a regression, not a requirement.
s = replace_block_containing(
    s,
    'canvas\\.toBlob',
    '''if ($runtimeText.Contains("canvas.toBlob") -or
    $runtimeText.Contains("image/jpeg") -or
    $runtimeText.Contains("bridgeStereoEyes") -or
    $runtimeText.Contains("stereoGpuPhase") -or
    $runtimeText.Contains("ggq-pc-raw-left-eye-overlay")) {
    throw "v0.13.24 doğrulaması başarısız: eski JPEG veya görünür-kompozit stereo yolu bulundu."
}
if (-not $mainFormText.Contains("TryHandleRawStereoMessage") -or
    -not $mainFormText.Contains("WriteRawSbsRgba") -or
    -not $writerText.Contains("WriteRawSbsRgba") -or
    -not $sharedText.Contains("pixelFormat") -or
    -not $sharedText.Contains("DXGI_FORMAT_R8G8B8A8_UNORM")) {
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

# SourceTexture is also used by cursor/UI helper textures. v0.13.24 added a
# pixelFormat argument for the SBS texture, but all old six-argument callers must
# remain valid and continue to mean BGRA. Keep one method with a default value.
p = Path('pc-xr/v11-shared.hpp')
s = p.read_text(encoding='utf-8')
old = '''        int rowPitch,
        int pixelFormat) {
'''
new = '''        int rowPitch,
        int pixelFormat = 1) {
'''
if old not in s:
    raise SystemExit('v0.13.24 buildfix: SourceTexture::Upload pixelFormat signature missing')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

print('v0.13.24 build validation + SourceTexture compatibility updated')
