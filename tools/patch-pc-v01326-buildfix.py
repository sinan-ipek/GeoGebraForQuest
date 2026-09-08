from pathlib import Path

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')

# v0.13.24's validation named the full-SBS raw transport. v0.13.26 deliberately
# carries only GeoGebra's alternate eye; A itself supplies the first eye in XR.
s = s.replace('js-stereo-raw-arraybuffer', 'js-stereo-single-eye-raw')
s = s.replace('stereoRawSbs', 'stereoRawEye')

# build.ps1 uses an escaped regex literal for the cache-busting version.
s = s.replace(r'0\.13\.24-raw-arraybuffer', r'0\.13\.26-geogebra-glasses-raw')
s = s.replace('0.13.24-raw-arraybuffer', '0.13.26-geogebra-glasses-raw')

# v0.13.26 intentionally removes the old artificial "B 2 cm behind A" geometry.
# Keep validating the XR transparent-hole and high-quality minification code, but
# require the new simple composition instead: A for the first eye and GeoGebra's
# alternate raw eye for the second, both on A's exact physical plane.
old_render_validation = '''if ($renderText -notmatch "behindDistance = kScreenDistanceMeters \\+ 0\\.02f" -or
    $renderText -notmatch "DrawBaseWithHole" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.26 doğrulaması başarısız: B-behind / XR transparent hole / quality minification eksik."
}
'''
if old_render_validation not in s:
    # The message may still carry an older version label after cumulative patches;
    # locate the exact three-line legacy check structurally instead.
    start = s.find('if ($renderText -notmatch "behindDistance = kScreenDistanceMeters')
    if start < 0:
        raise SystemExit('v0.13.26 buildfix: legacy B-behind validation start missing')
    end = s.find('\n}', start)
    if end < 0:
        raise SystemExit('v0.13.26 buildfix: legacy B-behind validation end missing')
    end += 2
    if end < len(s) and s[end] == '\n':
        end += 1
    s = s[:start] + '''if ($renderText -notmatch "if \\(!rightEye\\)" -or
    $renderText -notmatch "First eye already exists" -or
    $renderText -notmatch "sbsSrv, 0\\.5f" -or
    $renderText -notmatch "DrawBaseWithHole" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.26 doğrulaması başarısız: A-left / GeoGebra-right / XR hole / quality minification eksik."
}
''' + s[end:]
else:
    s = s.replace(old_render_validation, '''if ($renderText -notmatch "if \\(!rightEye\\)" -or
    $renderText -notmatch "First eye already exists" -or
    $renderText -notmatch "sbsSrv, 0\\.5f" -or
    $renderText -notmatch "DrawBaseWithHole" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.26 doğrulaması başarısız: A-left / GeoGebra-right / XR hole / quality minification eksik."
}
''', 1)

# Keep the binary/raw invariants, but validate the new host/writer/XR join too.
legacy_chain = '''if (-not $mainFormText.Contains("TryHandleRawStereoMessage") -or
    -not $mainFormText.Contains("WriteRawSbsRgba") -or
    -not $writerText.Contains("WriteRawSbsRgba") -or
    -not $sharedText.Contains("pixelFormat") -or
    -not $sharedText.Contains("DXGI_FORMAT_R8G8B8A8_UNORM")) {
    throw "v0.13.26 doğrulaması başarısız: host/MMF/XR raw RGBA zinciri eksik."
}
'''
if legacy_chain in s:
    s = s.replace(legacy_chain, '''if (-not $mainFormText.Contains("TryHandleRawStereoMessage") -or
    -not $mainFormText.Contains("HandleRawStereoEye") -or
    -not $mainFormText.Contains("WriteRawMonoAsSbsRgba") -or
    -not $writerText.Contains("WriteRawMonoAsSbsRgba") -or
    -not $sharedText.Contains("pixelFormat") -or
    -not $sharedText.Contains("DXGI_FORMAT_R8G8A8_UNORM") -and
    -not $sharedText.Contains("DXGI_FORMAT_R8G8B8A8_UNORM")) {
    throw "v0.13.26 doğrulaması başarısız: A + alternate-eye raw zinciri eksik."
}
''', 1)

p.write_text(s, encoding='utf-8')
print('v0.13.26 single-eye build validation updated')
