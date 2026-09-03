from pathlib import Path
import re


def rep(path, old, new, count=None):
    p = Path(path)
    t = p.read_text(encoding='utf-8')
    n = t.count(old)
    if n == 0:
        raise SystemExit(f'Missing fragment in {path}: {old[:120]!r}')
    if count is not None and n != count:
        raise SystemExit(f'Expected {count}, got {n} in {path}: {old[:120]!r}')
    p.write_text(t.replace(old, new), encoding='utf-8')

rep('pc-xr/main-v13fixed.cpp',
    'constexpr float kRenderQualityScale = 1.15f;',
    'constexpr float kRenderQualityScale = 1.08f;', 1)
rep('pc-xr/main-v13fixed.cpp',
    'v0.13.1 eye target = OpenXR recommended x1.15, clamped to Quest3 physical/runtime max',
    'v0.13.2 eye target = OpenXR recommended x1.08, clamped to Quest3 physical/runtime max', 1)

p = Path('pc-xr/v11-shared.hpp')
t = p.read_text(encoding='utf-8')
t = t.replace('constexpr float kScreenWidthMeters = 1.95f;',
              'constexpr float kScreenWidthMeters = 2.05f;', 1)
t = t.replace('constexpr float kScreenHeightMeters = 1.10f;',
              'constexpr float kScreenHeightMeters = 1.155f;', 1)
p.write_text(t, encoding='utf-8')

p = Path('pc/MainFormV11.InputStereo.cs')
t = p.read_text(encoding='utf-8')
t = t.replace('const int xrSourceWidth = 2560;', 'const int xrSourceWidth = 2048;', 1)
p.write_text(t, encoding='utf-8')

p = Path('pc/MainFormV11.Graphics.cs')
t = p.read_text(encoding='utf-8')
old = '''    private float GetBrowserDeviceScaleFactor()\n    {\n        var dpi = DeviceDpi > 0 ? DeviceDpi : 96;\n        return Math.Clamp(dpi / 96.0F, 1.0F, 4.0F);\n    }'''
new = '''    private float GetBrowserDeviceScaleFactor()\n    {\n        // Keep the Quest-facing CEF raster stable and independent of the PC\n        // monitor DPI. 1.25 DPR gives GeoGebra strokes/text subpixel coverage\n        // while the 2048 logical viewport keeps the final texture economical.\n        return 1.25F;\n    }'''
if old not in t:
    raise SystemExit('GetBrowserDeviceScaleFactor block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')

p = Path('pc/SameSurfaceLifeSpanHandler.cs')
p.write_text(r'''using CefSharp;
using CefSharp.Handler;

namespace GeoGebraForQuest.PC;

internal sealed class SameSurfaceLifeSpanHandler : LifeSpanHandler
{
    protected override bool OnBeforePopup(
        IWebBrowser chromiumWebBrowser,
        IBrowser browser,
        IFrame frame,
        string targetUrl,
        string targetFrameName,
        WindowOpenDisposition targetDisposition,
        bool userGesture,
        IPopupFeatures popupFeatures,
        IWindowInfo windowInfo,
        IBrowserSettings browserSettings,
        ref bool noJavascriptAccess,
        out IWebBrowser newBrowser)
    {
        newBrowser = null!;
        if (!string.IsNullOrWhiteSpace(targetUrl))
        {
            browser.MainFrame.LoadUrl(targetUrl);
        }
        return true;
    }
}
''', encoding='utf-8')

p = Path('pc/D3DChromiumWebBrowser.cs')
t = p.read_text(encoding='utf-8')
needle = '''        RenderHandler = renderHandler;\n        _initialWidth = Math.Max(2, initialWidth);'''
replace = '''        RenderHandler = renderHandler;\n        LifeSpanHandler = new SameSurfaceLifeSpanHandler();\n        _initialWidth = Math.Max(2, initialWidth);'''
if needle not in t:
    raise SystemExit('D3D browser constructor marker missing')
t = t.replace(needle, replace, 1)
p.write_text(t, encoding='utf-8')

for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    t = p.read_text(encoding='utf-8')
    t = t.replace('0.13.1-tuning-exit', '0.13.2-popup-clarity')
    t = t.replace(r'0\.13\.1-tuning-exit', r'0\.13\.2-popup-clarity')
    t = t.replace('v0.13.1 ·', 'v0.13.2 ·')
    t = t.replace('[GGQ-PC v0.13.1]', '[GGQ-PC v0.13.2]')
    if file.endswith('.csproj'):
        t = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.2</Version>', t, count=1)
        t = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.2.0</FileVersion>', t, count=1)
        t = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.2.0</AssemblyVersion>', t, count=1)
    if file.endswith('build.ps1'):
        t = t.replace('kRenderQualityScale = 1\\.15f', 'kRenderQualityScale = 1\\.08f')
        t = t.replace('kRenderQualityScale = 1.15f', 'kRenderQualityScale = 1.08f')
        t = t.replace('kScreenWidthMeters = 1\\.95f', 'kScreenWidthMeters = 2\\.05f')
        t = t.replace('kScreenWidthMeters = 1.95f', 'kScreenWidthMeters = 2.05f')
        t = t.replace('kScreenHeightMeters = 1\\.10f', 'kScreenHeightMeters = 1\\.155f')
        t = t.replace('kScreenHeightMeters = 1.10f', 'kScreenHeightMeters = 1.155f')
        t = t.replace('xrSourceWidth = 2560', 'xrSourceWidth = 2048')
        old_guard = '''if ($graphicsText -notmatch "DeviceDpi" -or\n    $graphicsText -notmatch "DeviceScaleFactor = GetBrowserDeviceScaleFactor") {\n    throw "v0.13 doğrulaması başarısız: native Windows DPI CEF'e bağlı değil."\n}'''
        new_guard = '''if ($graphicsText -notmatch "return 1\\.25F" -or\n    $graphicsText -notmatch "DeviceScaleFactor = GetBrowserDeviceScaleFactor") {\n    throw "v0.13.2 doğrulaması başarısız: sabit 1.25 CEF DPR yolu eksik."\n}'''
        if old_guard in t:
            t = t.replace(old_guard, new_guard, 1)
    p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.2 popup/clarity tuning applied')
