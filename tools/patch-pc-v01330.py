from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.30
#
# Root cause fixed here:
# v0.13.27/v0.13.28 correctly built a full [A_L | A_R] SBS GPU texture, then
# passed it to ProjectionRenderer::RenderEye as sbsSrv with stereoRect=nullptr.
# RenderEye defines legacy stereo as:
#     sbsSrv != nullptr && stereoRect != nullptr
# so the full-SBS texture was NEVER drawn. The else branch drew ordinary A.
# That exactly explains the user's "no depth" result.
#
# New invariant:
#   sbsSrv != nullptr && stereoRect == nullptr  => FULL APPLICATION SBS mode.
# In that mode LEFT physical eye samples U=0..0.5 and RIGHT samples U=0.5..1
# across the normal A panel rectangle. No second B panel exists.
# ---------------------------------------------------------------------------

p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

old = '''        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;
        if (stereoVisible) {
'''
req(s, old, 'v0.13.30 RenderEye stereo gate missing')

new = '''        // GGQ v0.13.30 FULL-APPLICATION-SBS PRESENTATION FIX.
        // v0.13.27/28 passed the already-composed [A_L|A_R] texture as sbsSrv
        // with stereoRect == nullptr. The old code therefore ignored it and drew
        // baseSrv (ordinary A) to both eyes. Treat that combination explicitly as
        // a complete-application SBS source and crop one half per physical eye.
        const bool fullApplicationSbs = sbsSrv != nullptr && stereoRect == nullptr;
        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;

        if (fullApplicationSbs) {
            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);
        } else if (stereoVisible) {
'''
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# Version / cache / package labels.
# ---------------------------------------------------------------------------
p = Path('pc/GeoGebraForQuest.PC.csproj')
s = p.read_text(encoding='utf-8')
s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.30</Version>', s, count=1)
s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.30.0</FileVersion>', s, count=1)
s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.30.0</AssemblyVersion>', s, count=1)
p.write_text(s, encoding='utf-8')

p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')
s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.30-full-sbs-presentation-fix',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.28', 'GeoGebraForQuest PC v0.13.30')
p.write_text(s, encoding='utf-8')

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'GeoGebraForQuest-PC-v0.13.28-true-al-ar-full-sbs-win-x64',
    'GeoGebraForQuest-PC-v0.13.30-full-sbs-presentation-fix-win-x64')
s = s.replace('0.13.28-true-al-ar-full-sbs', '0.13.30-full-sbs-presentation-fix')
s = s.replace(r'0\.13\.28-true-al-ar-full-sbs', r'0\.13\.30-full-sbs-presentation-fix')
s = s.replace('v0.13.28', 'v0.13.30')
s = s.replace(r'v0\.13\.28', r'v0\.13\.30')

# Existing v0.13.28 validator refers to the old compositor label/version.
s = s.replace(
    'GGQ v0\\.13\\.30 TRUE A_L/A_R SBS single-panel path',
    'GGQ v0\\.13\\.28 TRUE A_L/A_R SBS single-panel path')

# Add a hard guard for the actual presentation fix. This is the line that was
# missing in v0.13.27/28 and made the correct full SBS texture invisible.
insert_marker = '$renderText = Get-Content $renderPath -Raw\n'
req(s, insert_marker, 'v0.13.30 build renderText marker missing')
validation = '''$renderText = Get-Content $renderPath -Raw
if (-not $renderText.Contains("const bool fullApplicationSbs = sbsSrv != nullptr && stereoRect == nullptr;") -or
    -not $renderText.Contains("if (fullApplicationSbs)") -or
    -not $renderText.Contains("const float u0 = rightEye ? 0.5f : 0.0f;") -or
    -not $renderText.Contains("const float u1 = rightEye ? 1.0f : 0.5f;")) {
    throw "v0.13.30 doğrulaması başarısız: full application SBS eye-crop presentation yolu eksik."
}
'''
s = s.replace(insert_marker, validation, 1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# Final source invariants.
# ---------------------------------------------------------------------------
checks = {
    'pc-xr/v11-render.hpp': [
        'FULL-APPLICATION-SBS PRESENTATION FIX',
        'const bool fullApplicationSbs = sbsSrv != nullptr && stereoRect == nullptr;',
        'if (fullApplicationSbs)',
        'const float u0 = rightEye ? 0.5f : 0.0f;',
        'const float u1 = rightEye ? 1.0f : 0.5f;',
        'sbsSrv, u0, 0.0f, u1, 1.0f, true',
    ],
    'pc-xr/main-v11.cpp': [
        'fullSbsComposer_.Compose',
        'pairReady',
    ],
    'pc/pc-stereo-layout.js': [
        "type: 'stereoRawPair'",
        'eyes.left',
        'eyes.right',
    ],
    'pc/StereoSharedFrameWriter.cs': [
        'WriteRawStereoPairRgba',
        '_view.Write(116, 2)',
    ],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.30 invariant missing in {file}: {needle}')

print('GeoGebraForQuest PC v0.13.30 full-SBS presentation fix applied')
