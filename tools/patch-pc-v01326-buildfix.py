from pathlib import Path

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

# v0.13.24's validation named the full-SBS raw transport. v0.13.26 deliberately
# carries only GeoGebra's alternate eye; A itself supplies the first eye in XR.
s = s.replace('js-stereo-raw-arraybuffer', 'js-stereo-single-eye-raw')
s = s.replace('stereoRawSbs', 'stereoRawEye')

# Keep the binary/raw invariants, but validate the new host/writer/XR join too.
marker = '''if (-not $mainFormText.Contains("TryHandleRawStereoMessage") -or
    -not $mainFormText.Contains("WriteRawSbsRgba") -or
    -not $writerText.Contains("WriteRawSbsRgba") -or
    -not $sharedText.Contains("pixelFormat") -or
    -not $sharedText.Contains("DXGI_FORMAT_R8G8B8A8_UNORM")) {
    throw "v0.13.26 doğrulaması başarısız: host/MMF/XR raw RGBA zinciri eksik."
}
'''
if marker in s:
    s = s.replace(marker, '''if (-not $mainFormText.Contains("TryHandleRawStereoMessage") -or
    -not $mainFormText.Contains("HandleRawStereoEye") -or
    -not $mainFormText.Contains("WriteRawMonoAsSbsRgba") -or
    -not $writerText.Contains("WriteRawMonoAsSbsRgba") -or
    -not $sharedText.Contains("pixelFormat") -or
    -not $sharedText.Contains("DXGI_FORMAT_R8G8B8A8_UNORM")) {
    throw "v0.13.26 doğrulaması başarısız: A + alternate-eye raw zinciri eksik."
}
''', 1)

p.write_text(s, encoding='utf-8')
print('v0.13.26 single-eye build validation updated')
