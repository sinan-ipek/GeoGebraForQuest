from pathlib import Path


def replace(path, old, new, count=None):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    found = text.count(old)
    if found == 0:
        raise SystemExit(f'Missing expected fragment in {path}: {old[:120]!r}')
    if count is not None and found != count:
        raise SystemExit(f'Expected {count} matches in {path}, found {found}: {old[:120]!r}')
    p.write_text(text.replace(old, new), encoding='utf-8')

# XR panel: larger angular size, but still comfortably inside Quest FOV.
replace('pc-xr/v11-shared.hpp',
        'constexpr float kScreenWidthMeters = 1.65f;\nconstexpr float kScreenDistanceMeters = 1.55f;\nconstexpr float kStereoDistanceMeters = 1.53f;\nconstexpr float kCursorDistanceMeters = 1.515f;',
        'constexpr float kScreenWidthMeters = 1.95f;\nconstexpr float kScreenDistanceMeters = 1.50f;\nconstexpr float kStereoDistanceMeters = 1.48f;\nconstexpr float kCursorDistanceMeters = 1.465f;', 1)

# Build the balanced OpenXR wrapper instead of the physical-panel-forcing wrapper.
replace('pc-xr/CMakeLists.txt', 'main-v123.cpp', 'main-v124.cpp')
replace('pc-xr/CMakeLists.txt',
        '# v0.12.3 keeps the proven v0.12 OpenXR session/input/stereo loop.',
        '# v0.12.4 keeps the proven v0.12 OpenXR session/input/stereo loop.')
replace('pc-xr/CMakeLists.txt',
        '# Quest target: 2064x2208 physical pixels per eye, clamped to runtime maxImageRect.',
        '# Quest target: OpenXR recommended x1.12, clamped to Quest 3 physical/runtime max.')

# Filter the Touch ray once, then use the same filtered UV for both CEF and XR cursor.
p = Path('pc-xr/main-v11.cpp')
text = p.read_text(encoding='utf-8')
old = '''        inputWriter_.Publish(true, u, v, triggerDown_);\n\n        const float cursorScale =\n            kCursorDistanceMeters / kScreenDistanceMeters;\n        cursorX = hit.x * cursorScale;\n        cursorY = hit.y * cursorScale;\n        return true;'''
new = '''        // One shared filtered coordinate drives both the visible XR cursor and CEF.\n        // This removes tiny controller pose jitter without creating a second hit-test path.\n        static bool filterInitialized = false;\n        static float filteredU = 0.0f;\n        static float filteredV = 0.0f;\n        const float jump = filterInitialized\n            ? std::max(std::abs(u - filteredU), std::abs(v - filteredV))\n            : 1.0f;\n        if (!filterInitialized || jump > 0.075f) {\n            filteredU = u;\n            filteredV = v;\n            filterInitialized = true;\n        } else {\n            constexpr float alpha = 0.44f;\n            filteredU += (u - filteredU) * alpha;\n            filteredV += (v - filteredV) * alpha;\n        }\n\n        inputWriter_.Publish(true, filteredU, filteredV, triggerDown_);\n\n        const float filteredHitX = baseRect.left + width * filteredU;\n        const float filteredHitY = baseRect.top - height * filteredV;\n        const float cursorScale =\n            kCursorDistanceMeters / kScreenDistanceMeters;\n        cursorX = filteredHitX * cursorScale;\n        cursorY = filteredHitY * cursorScale;\n        return true;'''
if old not in text:
    raise SystemExit('XR pointer publish block not found')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# CEF pointer ownership: physical mouse and Touch ray no longer fight every 8 ms.
p = Path('pc/MainFormV11.InputStereo.cs')
text = p.read_text(encoding='utf-8')
text = text.replace(
    '''        if (!sample.Valid)\n        {\n            if (_xrPointerWasValid)''',
    '''        if (!sample.Valid)\n        {\n            ResetXrPointerRouting();\n            if (_xrPointerWasValid)''', 1)
text = text.replace(
    '''        var x = Math.Clamp(\n            (int)Math.Round(sample.U * (size.Width - 1)),''',
    '''        if (!ShouldRouteXrPointer(sample.U, sample.V, sample.TriggerDown)) return;\n\n        var x = Math.Clamp(\n            (int)Math.Round(sample.U * (size.Width - 1)),''', 1)
for signature in (
    'protected override void OnMouseMove(MouseEventArgs e)',
    'protected override void OnMouseDown(MouseEventArgs e)',
    'protected override void OnMouseUp(MouseEventArgs e)',
    'protected override void OnMouseWheel(MouseEventArgs e)',
):
    marker = signature + '\n    {\n        base.'
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit(f'Mouse handler not found: {signature}')
    base_end = text.find(';', idx + len(marker)) + 1
    text = text[:base_end] + '\n        MarkPhysicalMouseActivity();' + text[base_end:]
p.write_text(text, encoding='utf-8')

# Version/cache labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    text = p.read_text(encoding='utf-8')
    text = text.replace('0.12.3-xr-behind-native', '0.12.4-input-panel-quality')
    text = text.replace('v0.12.3', 'v0.12.4')
    text = text.replace('0.12.3.0', '0.12.4.0')
    text = text.replace('<Version>0.12.3</Version>', '<Version>0.12.4</Version>')
    text = text.replace('main-v123.cpp', 'main-v124.cpp')
    text = text.replace('main-v123\\.cpp', 'main-v124\\.cpp')
    text = text.replace('Quest 3 physical target 2064x2208/göz, runtime maxImageRect ile clamp',
                        'OpenXR recommended x1.12/göz, Quest 3 physical/runtime max ile clamp')
    p.write_text(text, encoding='utf-8')

# build.ps1 has old validation assumptions; update them to assert the new architecture.
p = Path('pc/build.ps1')
text = p.read_text(encoding='utf-8')
text = text.replace(
    'if ($wrapperText -notmatch "2064" -or\n    $wrapperText -notmatch "2208" -or\n    $wrapperText -notmatch "maxImageRectWidth" -or\n    $wrapperText -notmatch "maxImageRectHeight") {\n    throw "v0.12.4 doğrulaması başarısız: Quest 3 fiziksel 2064x2208 XR hedefi eksik."\n}',
    'if ($wrapperText -notmatch "kRenderQualityScale = 1.12f" -or\n    $wrapperText -notmatch "runtimeRecommendedWidth" -or\n    $wrapperText -notmatch "maxImageRectWidth" -or\n    $wrapperText -notmatch "kQuest3PhysicalEyeWidth") {\n    throw "v0.12.4 doğrulaması başarısız: balanced OpenXR render hedefi eksik."\n}')
text = text.replace(
    'if ($inputText -notmatch "PublishMousePointerToXr" -or\n    $inputText -notmatch "OnMouseLeave") {',
    'if ($inputText -notmatch "PublishMousePointerToXr" -or\n    $inputText -notmatch "ShouldRouteXrPointer" -or\n    $inputText -notmatch "MarkPhysicalMouseActivity" -or\n    $inputText -notmatch "OnMouseLeave") {')
p.write_text(text, encoding='utf-8')

print('GeoGebraForQuest PC v0.12.4 patch applied')
