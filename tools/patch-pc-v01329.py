from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.29
#
# Purpose: isolate the failure seen in v0.13.28.
#
# Keep the NEW single-panel A_L|A_R GPU compositor, but feed it with the exact
# PROVEN v0.13.22 JPEG/Base64 L/R transport and legacy Bitmap -> BGRA SBS MMF
# path. If this produces depth, the compositor architecture is valid and the
# v0.13.24+ raw ArrayBuffer transport is the broken layer.
#
# The workflow restores pc/pc-stereo-layout.js verbatim from
# checkpoint-v0.13.22-working-stereo BEFORE this patch runs.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) Restore the old updateStereoEyes bridge and stereoEyes host switch arm.
#    v0.13.24 intentionally removed both; decoder helpers were left compiled.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

if 'updateStereoEyes: function (left, right)' not in s:
    marker = '''                updateStereoLayout: function (json) {
                  post({ type: 'stereoLayout', payload: String(json || '') });
                },
'''
    req(s, marker, 'v0.13.29 updateStereoLayout bridge marker missing')
    addition = marker + '''                updateStereoEyes: function (left, right) {
                  post({ type: 'stereoEyes', left: String(left || ''), right: String(right || '') });
                },
'''
    s = s.replace(marker, addition, 1)

if 'case "stereoEyes":' not in s:
    arm = '''                case "stereoEyes":
                    if (!root.TryGetProperty("left", out var leftNode) ||
                        !root.TryGetProperty("right", out var rightNode)) return;
                    var left = leftNode.GetString();
                    var right = rightNode.GetString();
                    if (!string.IsNullOrWhiteSpace(left) &&
                        !string.IsNullOrWhiteSpace(right))
                        QueueStereoFrames(left, right);
                    break;
'''
    if '                case "performanceSample":' in s:
        s = s.replace('                case "performanceSample":', arm + '                case "performanceSample":', 1)
    else:
        req(s, '                case "runtimeError":', 'v0.13.29 stereoEyes insertion marker missing')
        s = s.replace('                case "runtimeError":', arm + '                case "runtimeError":', 1)

# Old JPEG messages must fall through TryHandleRawStereoMessage(false) and reach
# the JSON switch above. The raw handler remains compiled but is unused here.
s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.29-jpeg-proof-single-panel',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.28', 'GeoGebraForQuest PC v0.13.29')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) NEW compositor accepts BOTH legacy BGRA SBS (pixelFormat=1) and raw RGBA
#    SBS (pixelFormat=2). v0.13.29 intentionally exercises format=1 only.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')
old = '            pairFrame->pixelFormat == 2 &&\n'
req(s, old, 'v0.13.29 renderer pixel-format gate missing')
s = s.replace(
    old,
    '            (pairFrame->pixelFormat == 1 || pairFrame->pixelFormat == 2) &&\n',
    1)
s = s.replace(
    '// GGQ v0.13.28 TRUE A_L/A_R SBS single-panel path.',
    '// GGQ v0.13.29 JPEG-PROOF A_L/A_R SBS single-panel path.',
    1)
p.write_text(s, encoding='utf-8')

p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')
old = '                        sbsFrame_.pixelFormat == 2 && !sbsFrame_.sbs.empty();\n'
req(s, old, 'v0.13.29 main pixel-format gate missing')
s = s.replace(
    old,
    '                        (sbsFrame_.pixelFormat == 1 || sbsFrame_.pixelFormat == 2) && !sbsFrame_.sbs.empty();\n',
    1)
s = s.replace(
    'initialized: A CEF GPU + raw TRUE L/R -> GPU A_L|A_R full-SBS single panel',
    'initialized: A CEF GPU + proven JPEG L/R -> GPU A_L|A_R full-SBS single panel',
    1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Version/package labels.
# ---------------------------------------------------------------------------
p = Path('pc/GeoGebraForQuest.PC.csproj')
s = p.read_text(encoding='utf-8')
s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.29</Version>', s, count=1)
s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.29.0</FileVersion>', s, count=1)
s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.29.0</AssemblyVersion>', s, count=1)
p.write_text(s, encoding='utf-8')

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'GeoGebraForQuest-PC-v0.13.28-true-al-ar-full-sbs-win-x64',
    'GeoGebraForQuest-PC-v0.13.29-jpeg-proof-single-panel-win-x64')
s = s.replace('0.13.28-true-al-ar-full-sbs', '0.13.29-jpeg-proof-single-panel')
s = s.replace(r'0\.13\.28-true-al-ar-full-sbs', r'0\.13\.29-jpeg-proof-single-panel')
s = s.replace('v0.13.28', 'v0.13.29')
s = s.replace(r'v0\.13\.28', r'v0\.13\.29')

# v0.13.28's build guard requires raw ArrayBuffer markers. This proof build
# deliberately restores the old JPEG runtime, so replace only that architecture
# guard with a guard for the cross-connected JPEG + single-panel path.
pattern = re.compile(
    r'if \(\$renderText -notmatch "GGQ v0\\\.13\\\.29 TRUE A_L/A_R SBS single-panel path".*?\n\}',
    re.S)
match = pattern.search(s)
if match:
    replacement = '''if ($renderText -notmatch "GGQ v0\\.13\\.29 JPEG-PROOF A_L/A_R SBS single-panel path" -or
    $renderText -notmatch "class FullSbsComposer" -or
    $renderText -notmatch "pairFrame->pixelFormat == 1" -or
    $renderText -notmatch "rightEye \\? 0\\.5f : 0\\.0f" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.29 doğrulaması başarısız: proven JPEG L/R + full A_L/A_R SBS single-panel path eksik."
}'''
    s = s[:match.start()] + replacement + s[match.end():]
else:
    # Fallback: locate the previous throw block by its known message.
    throw_text = 'v0.13.29 doğrulaması başarısız: full A_L/A_R SBS / single panel / quality minification eksik.'
    idx = s.find(throw_text)
    if idx >= 0:
        start = s.rfind('if (', 0, idx)
        end = s.find('\n}', idx)
        if start < 0 or end < 0:
            raise SystemExit('v0.13.29 build guard boundaries missing')
        end += 2
        replacement = '''if ($renderText -notmatch "GGQ v0\\.13\\.29 JPEG-PROOF A_L/A_R SBS single-panel path" -or
    $renderText -notmatch "class FullSbsComposer" -or
    $renderText -notmatch "pairFrame->pixelFormat == 1" -or
    $renderText -notmatch "rightEye \\? 0\\.5f : 0\\.0f" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.29 doğrulaması başarısız: proven JPEG L/R + full A_L/A_R SBS single-panel path eksik."
}'''
        s = s[:start] + replacement + s[end:]

# Remove raw-runtime-specific checks that cannot be true after restoring the
# checkpoint JS. Keep all generic packaging/XR/quality checks.
lines = s.splitlines()
out = []
skip = False
brace_depth = 0
for line in lines:
    if not skip and ('stereoRawPair' in line or 'js-al-ar-pair-raw' in line or 'WriteRawStereoPairRgba' in line):
        # These tokens may occur in a multiline if guard. Drop the whole guard.
        if any(x in line for x in ('if (', '-notmatch', '-match')):
            skip = True
            brace_depth = line.count('{') - line.count('}')
            continue
    if skip:
        brace_depth += line.count('{') - line.count('}')
        if brace_depth <= 0 and '}' in line:
            skip = False
        continue
    out.append(line)
s = '\n'.join(out) + ('\n' if s.endswith('\n') else '')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Final proof invariants.
# ---------------------------------------------------------------------------
checks = {
    'pc/pc-stereo-layout.js': [
        'CAPTURE_JPEG_QUALITY',
        'canvasToDataUrlAsync',
        'bridgeStereoEyes(leftDataUrl, rightDataUrl)',
        "document.getElementById('ggq-renderer-left-eye')",
        "document.getElementById('ggq-renderer-right-eye')",
    ],
    'pc/MainFormV11.cs': [
        'updateStereoEyes: function (left, right)',
        'case "stereoEyes":',
        'QueueStereoFrames(left, right)',
    ],
    'pc/MainFormV11.InputStereo.cs': [
        'DecodeStereoLoop',
        '_sharedStereoFrames.WriteFrames',
    ],
    'pc-xr/v11-render.hpp': [
        'JPEG-PROOF A_L/A_R SBS single-panel path',
        'pairFrame->pixelFormat == 1',
        '0.0f, 0.0f, 0.5f, 1.0f',
        '0.5f, 0.0f, 1.0f, 1.0f',
    ],
    'pc-xr/main-v11.cpp': [
        'sbsFrame_.pixelFormat == 1',
        'fullSbsComposer_.Compose',
    ],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.29 final invariant missing in {file}: {needle}')

# The proof runtime itself must not use the raw binary transport.
runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
for forbidden in ("type: 'stereoRawPair'", "type: 'stereoRawSbs'", 'getImageData('):
    if forbidden in runtime:
        raise SystemExit(f'v0.13.29 raw proof contamination: {forbidden}')

print('GeoGebraForQuest PC v0.13.29 proven JPEG L/R -> single-panel A_L/A_R proof applied')
