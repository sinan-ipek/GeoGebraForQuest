from pathlib import Path


def rep(path, old, new, count=None):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    n = text.count(old)
    if n == 0:
        raise SystemExit(f'Missing fragment in {path}: {old[:100]!r}')
    if count is not None and n != count:
        raise SystemExit(f'Expected {count}, got {n} in {path}: {old[:100]!r}')
    p.write_text(text.replace(old, new), encoding='utf-8')

# ----- XR geometry: fixed physical size; NEVER derive panel size from texture pixels.
rep('pc-xr/v11-shared.hpp',
    'constexpr float kScreenWidthMeters = 1.65f;\nconstexpr float kScreenDistanceMeters = 1.55f;\nconstexpr float kStereoDistanceMeters = 1.53f;\nconstexpr float kCursorDistanceMeters = 1.515f;',
    'constexpr float kScreenWidthMeters = 1.95f;\nconstexpr float kScreenHeightMeters = 1.10f;\nconstexpr float kScreenDistanceMeters = 1.50f;\nconstexpr float kStereoDistanceMeters = 1.48f;\nconstexpr float kCursorDistanceMeters = 1.465f;', 1)

p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')
old = '''    PanelRect MakeBaseRect() const {\n        const int width = std::max(1, baseTexture_.Width());\n        const int height = std::max(1, baseTexture_.Height());\n        const float screenHeight =\n            kScreenWidthMeters * static_cast<float>(height) /\n            static_cast<float>(width);\n        return {\n            -kScreenWidthMeters * 0.5f,\n             kScreenWidthMeters * 0.5f,\n             screenHeight * 0.5f,\n            -screenHeight * 0.5f\n        };\n    }'''
new = '''    PanelRect MakeBaseRect() const {\n        // Physical XR geometry is invariant. CEF texture size, DPI, popup/login\n        // surfaces and desktop window resizes are presentation details only.\n        return {\n            -kScreenWidthMeters * 0.5f,\n             kScreenWidthMeters * 0.5f,\n             kScreenHeightMeters * 0.5f,\n            -kScreenHeightMeters * 0.5f\n        };\n    }'''
if old not in t: raise SystemExit('MakeBaseRect block missing')
t = t.replace(old, new, 1)

# Smooth the actual Touch ray once and use the exact same UV for CEF + visible cursor.
old = '''        inputWriter_.Publish(true, u, v, triggerDown_);\n\n        const float cursorScale =\n            kCursorDistanceMeters / kScreenDistanceMeters;\n        cursorX = hit.x * cursorScale;\n        cursorY = hit.y * cursorScale;\n        return true;'''
new = '''        static bool filterInitialized = false;\n        static float filteredU = 0.0f;\n        static float filteredV = 0.0f;\n        const float jump = filterInitialized\n            ? std::max(std::abs(u - filteredU), std::abs(v - filteredV))\n            : 1.0f;\n        if (!filterInitialized || jump > 0.09f) {\n            filteredU = u; filteredV = v; filterInitialized = true;\n        } else {\n            constexpr float alpha = 0.52f;\n            filteredU += (u - filteredU) * alpha;\n            filteredV += (v - filteredV) * alpha;\n        }\n        inputWriter_.Publish(true, filteredU, filteredV, triggerDown_);\n\n        const float filteredHitX = baseRect.left + width * filteredU;\n        const float filteredHitY = baseRect.top - height * filteredV;\n        const float cursorScale = kCursorDistanceMeters / kScreenDistanceMeters;\n        cursorX = filteredHitX * cursorScale;\n        cursorY = filteredHitY * cursorScale;\n        return true;'''
if old not in t: raise SystemExit('pointer publish block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

# Only one cursor is shown in Quest: controller cursor wins whenever the ray is valid.
rep('pc-xr/v11-render.hpp',
    '        if (mouse.valid && mouseCursorTexture_.Valid()) {',
    '        if (!cursorValid && mouse.valid && mouseCursorTexture_.Valid()) {', 1)

# Build v0.13 wrapper.
rep('pc-xr/CMakeLists.txt', 'main-v123.cpp', 'main-v13fixed.cpp')

# ----- CEF source: high-resolution render surface frozen after startup.
p = Path('pc/MainFormV11.InputStereo.cs')
t = p.read_text(encoding='utf-8')
t = t.replace(
'''    private void RequestResize()\n    {\n        if (_closing || !IsHandleCreated) return;\n        UpdateBrowserSize();\n        lock (_d3dLock) _swapChainResizePending = true;\n    }''',
'''    private void RequestResize()\n    {\n        if (_closing || !IsHandleCreated) return;\n        // The desktop swapchain may resize, but the CEF render surface is frozen.\n        // Login dialogs, DPI changes and window resize events therefore cannot alter\n        // the XR texture dimensions or the panel geometry.\n        lock (_d3dLock) _swapChainResizePending = true;\n    }''', 1)
old = '''        var size = new Size(\n            Math.Max(320, (int)Math.Round(clientW / dpiScale)),\n            Math.Max(240, (int)Math.Round(clientH / dpiScale)));'''
new = '''        var logicalW = Math.Max(320, (int)Math.Round(clientW / dpiScale));\n        var logicalH = Math.Max(240, (int)Math.Round(clientH / dpiScale));\n        var aspect = logicalW / (double)Math.Max(1, logicalH);\n        const int xrSourceWidth = 2560;\n        var xrSourceHeight = Math.Max(1080, (int)Math.Round(xrSourceWidth / aspect));\n        var size = new Size(xrSourceWidth, xrSourceHeight);'''
if old not in t: raise SystemExit('browser size block missing')
t = t.replace(old, new, 1)

# XR/Mouse ownership.
t = t.replace('''        if (!sample.Valid)\n        {\n            if (_xrPointerWasValid)''',
              '''        if (!sample.Valid)\n        {\n            ResetXrPointerRouting();\n            if (_xrPointerWasValid)''', 1)
t = t.replace('''        var x = Math.Clamp(\n            (int)Math.Round(sample.U * (size.Width - 1)),''',
              '''        if (!ShouldRouteXrPointer(sample.U, sample.V, sample.TriggerDown)) return;\n\n        var x = Math.Clamp(\n            (int)Math.Round(sample.U * (size.Width - 1)),''', 1)

# Physical mouse handlers: ignore them while XR owns pointer.
for signature, force in [
    ('OnMouseMove', 'false'), ('OnMouseDown', 'true'), ('OnMouseUp', 'true'), ('OnMouseWheel', 'true')]:
    needle = f'    protected override void {signature}(MouseEventArgs e)\n    {{\n        base.{signature}(e);'
    if needle not in t: raise SystemExit(f'{signature} missing')
    extra = f'''    protected override void {signature}(MouseEventArgs e)\n    {{\n        base.{signature}(e);\n        MarkPhysicalMouseActivity(e.Location, {force});\n        if (!PhysicalMouseMayRoute()) return;'''
    t = t.replace(needle, extra, 1)
p.write_text(t, encoding='utf-8')

# ----- CEF accelerated popup composition.
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
needle = '    private bool _xrTriggerDown;\n    private bool _xrPointerWasValid;'
if needle not in t: raise SystemExit('MainForm pointer fields missing')
t = t.replace(needle, needle + '''\n    private Texture2D? _cefPopupTexture;\n    private Rect _cefPopupRect;\n    private bool _cefPopupVisible;''', 1)
t = t.replace('            foreach (var tex in _pcTextures) tex?.Dispose();',
              '            foreach (var tex in _pcTextures) tex?.Dispose();\n            _cefPopupTexture?.Dispose();', 1)
p.write_text(t, encoding='utf-8')

p = Path('pc/MainFormV11.Graphics.cs')
t = p.read_text(encoding='utf-8')
old = '''        if (_closing || type != PaintElementType.View ||\n            _device is null || _device1 is null) return;\n\n        try\n        {\n            lock (_d3dLock)\n            {\n                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(\n                    acceleratedPaintInfo.SharedTextureHandle);'''
new = '''        if (_closing || _device is null || _device1 is null) return;\n\n        try\n        {\n            lock (_d3dLock)\n            {\n                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(\n                    acceleratedPaintInfo.SharedTextureHandle);\n\n                if (type == PaintElementType.Popup)\n                {\n                    UpdatePopupTextureLocked(cefTexture);\n                    PublishCurrentCompositeLocked();\n                    return;\n                }\n                if (type != PaintElementType.View) return;'''
if old not in t: raise SystemExit('OnAcceleratedPaint header missing')
t = t.replace(old, new, 1)

# Bake stored popup onto the copied View before PC/XR publishing.
t = t.replace('''                _device.ImmediateContext.CopyResource(cefTexture, target);\n                _currentPcTexture = next;''',
'''                _device.ImmediateContext.CopyResource(cefTexture, target);\n                CompositePopupLocked(target);\n                _currentPcTexture = next;''', 1)
t = t.replace('TryQueueGpuPublishLocked(cefTexture)', 'TryQueueGpuPublishLocked(target)', 1)
t = t.replace('CompleteGpuPublishLocked(cefTexture.Description)', 'CompleteGpuPublishLocked(target.Description)', 1)

helper = r'''
    private void UpdatePopupTextureLocked(Texture2D source)
    {
        if (_device is null) return;
        var d = source.Description;
        if (_cefPopupTexture is null ||
            _cefPopupTexture.Description.Width != d.Width ||
            _cefPopupTexture.Description.Height != d.Height ||
            _cefPopupTexture.Description.Format != d.Format)
        {
            _cefPopupTexture?.Dispose();
            _cefPopupTexture = new Texture2D(_device, new Texture2DDescription
            {
                Width = d.Width,
                Height = d.Height,
                MipLevels = 1,
                ArraySize = 1,
                Format = d.Format,
                SampleDescription = new SampleDescription(1, 0),
                Usage = ResourceUsage.Default,
                BindFlags = BindFlags.ShaderResource,
                CpuAccessFlags = CpuAccessFlags.None,
                OptionFlags = ResourceOptionFlags.None
            });
        }
        _device.ImmediateContext.CopyResource(source, _cefPopupTexture);
    }

    private void CompositePopupLocked(Texture2D target)
    {
        if (_device is null || !_cefPopupVisible || _cefPopupTexture is null) return;
        Size browserSize;
        lock (_geometryLock) browserSize = _browserSize;
        if (browserSize.Width < 1 || browserSize.Height < 1) return;

        var td = target.Description;
        var pd = _cefPopupTexture.Description;
        var sx = td.Width / (double)browserSize.Width;
        var sy = td.Height / (double)browserSize.Height;
        var dx = Math.Clamp((int)Math.Round(_cefPopupRect.X * sx), 0, Math.Max(0, td.Width - 1));
        var dy = Math.Clamp((int)Math.Round(_cefPopupRect.Y * sy), 0, Math.Max(0, td.Height - 1));
        var copyW = Math.Min(pd.Width, td.Width - dx);
        var copyH = Math.Min(pd.Height, td.Height - dy);
        if (copyW < 1 || copyH < 1) return;

        var region = new ResourceRegion(0, 0, 0, copyW, copyH, 1);
        _device.ImmediateContext.CopySubresourceRegion(
            _cefPopupTexture, 0, region, target, 0, dx, dy, 0);
    }

    private void PublishCurrentCompositeLocked()
    {
        var target = _pcTextures[_currentPcTexture];
        if (target is null || _device is null) return;
        CompositePopupLocked(target);
        try
        {
            if (TryQueueGpuPublishLocked(target))
            {
                _device.ImmediateContext.Flush();
                CompleteGpuPublishLocked(target.Description);
                Interlocked.Increment(ref _gpuFrameNumber);
            }
        }
        catch { try { _xrSharedMutex?.Release(0); } catch { } }
    }
'''
marker = '    private void EnsurePcTextureLocked(Texture2DDescription source)'
if marker not in t: raise SystemExit('EnsurePcTexture marker missing')
t = t.replace(marker, helper + '\n' + marker, 1)

# Popup geometry/state is now meaningful and rendered into the same XR surface.
t = t.replace('''    public void OnPopupShow(bool show)\n    {\n        SetStereoUiSuspended(show);\n    }\n\n    public void OnPopupSize(Rect rect) { }''',
'''    public void OnPopupShow(bool show)\n    {\n        lock (_d3dLock) _cefPopupVisible = show;\n        SetStereoUiSuspended(show);\n        if (!show)\n        {\n            try { _browser?.GetBrowserHost()?.Invalidate(PaintElementType.View); } catch { }\n        }\n    }\n\n    public void OnPopupSize(Rect rect)\n    {\n        lock (_d3dLock) _cefPopupRect = rect;\n    }''', 1)
p.write_text(t, encoding='utf-8')

# ----- Stereo source quality: raise useful source density, but avoid 2048 CPU/JPEG overload.
p = Path('pc/pc-stereo-layout.js')
t = p.read_text(encoding='utf-8')
t = t.replace('var QUEST3_PPD = 25.0;', 'var QUEST3_PPD = 28.0;', 1)
t = t.replace('var XR_SCREEN_WIDTH_METERS = 1.65;', 'var XR_SCREEN_WIDTH_METERS = 1.95;', 1)
t = t.replace('var XR_SCREEN_DISTANCE_METERS = 1.55;', 'var XR_SCREEN_DISTANCE_METERS = 1.50;', 1)
t = t.replace('Math.min(1536, QUEST_FULL_A_TARGET_WIDTH)', 'Math.min(1792, QUEST_FULL_A_TARGET_WIDTH)', 1)
t = t.replace('var CAPTURE_MAX_EYE_WIDTH = 1536;', 'var CAPTURE_MAX_EYE_WIDTH = 1792;', 1)
t = t.replace('var CAPTURE_MAX_EYE_HEIGHT = 1664;', 'var CAPTURE_MAX_EYE_HEIGHT = 1792;', 1)
t = t.replace('var CAPTURE_JPEG_QUALITY = 0.99;', 'var CAPTURE_JPEG_QUALITY = 1.0;', 1)
p.write_text(t, encoding='utf-8')

# ----- Build/version labels and validation.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.12.3-xr-behind-native', '0.13-fixed-xr-surface')
    t = t.replace(r'0\.12\.3-xr-behind-native', r'0\.13-fixed-xr-surface')
    t = t.replace('v0.12.3', 'v0.13')
    t = t.replace(r'v0\.12\.3', r'v0\.13')
    t = t.replace('0.12.3.0', '0.13.0.0')
    t = t.replace('<Version>0.12.3</Version>', '<Version>0.13.0</Version>')
    t = t.replace('main-v123.cpp', 'main-v13fixed.cpp')
    t = t.replace(r'main-v123\.cpp', r'main-v13fixed\.cpp')
    p.write_text(t, encoding='utf-8')

# Replace old build.ps1 assumptions that specifically enforce v0.12.3 constants.
p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
t = t.replace('if ($wrapperText -notmatch "2064" -or\n    $wrapperText -notmatch "2208" -or\n    $wrapperText -notmatch "maxImageRectWidth" -or\n    $wrapperText -notmatch "maxImageRectHeight") {\n    throw "v0.13 doğrulaması başarısız: Quest 3 fiziksel 2064x2208 XR hedefi eksik."\n}',
'''if ($wrapperText -notmatch "kRenderQualityScale = 1.25f" -or\n    $wrapperText -notmatch "recommendedImageRectWidth" -or\n    $wrapperText -notmatch "kQuest3PhysicalEyeWidth") {\n    throw "v0.13 doğrulaması başarısız: fixed-surface native-quality XR wrapper eksik."\n}''')
t = t.replace('QUEST3_PPD = 25\\.0', 'QUEST3_PPD = 28\\.0')
t = t.replace('CAPTURE_MAX_EYE_WIDTH = 1536', 'CAPTURE_MAX_EYE_WIDTH = 1792')
p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13 fixed XR surface patch applied')
