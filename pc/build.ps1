param(
    [switch]$FrameworkDependent
)

$ErrorActionPreference = "Stop"

$pcDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $pcDir
$xrSource = Join-Path $root "pc-xr"
$xrBuild = Join-Path $root ".pc-xr-build"
$boot = Join-Path $root "app\src\main\assets\web\GeoGebra\web3d\web3d.nocache.js"
$project = Join-Path $pcDir "GeoGebraForQuest.PC.csproj"
$distRoot = Join-Path $root "dist"
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.12.2-native-quality-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$xrMain = Join-Path $xrSource "main-v11.cpp"
$xrShared = Join-Path $xrSource "v11-shared.hpp"
$xrRender = Join-Path $xrSource "v11-render.hpp"
$xrCmake = Join-Path $xrSource "CMakeLists.txt"
$mainForm = Join-Path $pcDir "MainFormV11.cs"
$graphics = Join-Path $pcDir "MainFormV11.Graphics.cs"
$inputStereo = Join-Path $pcDir "MainFormV11.InputStereo.cs"
$cefBrowser = Join-Path $pcDir "D3DChromiumWebBrowser.cs"
$stereoRuntime = Join-Path $pcDir "pc-stereo-layout.js"
$stereoWriter = Join-Path $pcDir "StereoSharedFrameWriter.cs"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK bulunamadı."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake bulunamadı."
}
if (-not (Test-Path $boot)) {
    throw "Exp46 patched GeoGebra Web3D paketi yok. Önce CI asset extraction adımını çalıştırın."
}
foreach ($required in @(
    $xrMain, $xrShared, $xrRender, $xrCmake, $mainForm, $graphics,
    $inputStereo, $cefBrowser, $stereoRuntime, $stereoWriter)) {
    if (-not (Test-Path $required)) {
        throw "v0.12.2 kaynak dosyası eksik: $required"
    }
}

$xrText = Get-Content $xrMain -Raw
$sharedText = Get-Content $xrShared -Raw
$renderText = Get-Content $xrRender -Raw
$cmakeText = Get-Content $xrCmake -Raw
$graphicsText = Get-Content $graphics -Raw
$browserText = Get-Content $cefBrowser -Raw
$mainFormText = Get-Content $mainForm -Raw
$inputText = Get-Content $inputStereo -Raw
$runtimeText = Get-Content $stereoRuntime -Raw
$writerText = Get-Content $stereoWriter -Raw
$all = $xrText + "`n" + $sharedText + "`n" + $renderText + "`n" +
       $graphicsText + "`n" + $browserText + "`n" + $mainFormText + "`n" +
       $inputText + "`n" + $runtimeText + "`n" + $writerText

if ($all -match "BitBlt\s*\(" -or
    $all -match "Windows\.Graphics\.Capture|GraphicsCaptureItem|PrintWindow\s*\(") {
    throw "v0.12.2 doğrulaması başarısız: ekran yakalama kodu bulundu."
}
if ($browserText -notmatch "SharedTextureEnabled = true") {
    throw "v0.12.2 doğrulaması başarısız: CEF shared GPU texture etkin değil."
}
if ($browserText -notmatch "WindowlessFrameRate = 60") {
    throw "v0.12.2 doğrulaması başarısız: CEF 60 fps tavanı korunmuyor."
}
if ($cmakeText -notmatch "main-v11\.cpp" -or $cmakeText -match "main-v121\.cpp") {
    throw "v0.12.2 doğrulaması başarısız: runtime-recommended OpenXR projection yolu aktif değil."
}
if ($mainFormText -notmatch "0\.12\.2-native-quality") {
    throw "v0.12.2 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}
if ($graphicsText -notmatch "DeviceDpi" -or
    $graphicsText -notmatch "DeviceScaleFactor = GetBrowserDeviceScaleFactor") {
    throw "v0.12.2 doğrulaması başarısız: native Windows DPI CEF'e bağlı değil."
}
if ($inputText -notmatch "clientW / dpiScale" -or
    $inputText -notmatch "SetStereoUiSuspended") {
    throw "v0.12.2 doğrulaması başarısız: DIP viewport veya stereo UI suspension eksik."
}
if ($inputText -notmatch "Parallel\.Invoke") {
    throw "v0.12.2 doğrulaması başarısız: paralel L/R decode korunmuyor."
}
if ($runtimeText -notmatch "QUEST_PANEL_TARGET_WIDTH = 1680" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1600" -or
    $runtimeText -notmatch "CAPTURE_JPEG_QUALITY = 0\.98") {
    throw "v0.12.2 doğrulaması başarısız: Quest'e uygun dinamik B kalite sınırları eksik."
}
if ($runtimeText -notmatch "clippedRectOf" -or
    $runtimeText -notmatch "stereoUiOccluded") {
    throw "v0.12.2 doğrulaması başarısız: 3D viewport clipping/UI occlusion yolu eksik."
}
if ($runtimeText -match "CAPTURE_MAX_EYE_WIDTH = 2048") {
    throw "v0.12.2 doğrulaması başarısız: eski sabit 2048px/göz B yolu hâlâ aktif."
}
if ($graphicsText -match 'Present\(1,') {
    throw "v0.12.2 performans regresyonu: Present(1) bulundu."
}
if ($graphicsText -notmatch 'Present\(0,') {
    throw "v0.12.2 doğrulaması başarısız: non-blocking PC present yolu eksik."
}
if ($runtimeText -notmatch "canvas\.toBlob") {
    throw "v0.12.2 doğrulaması başarısız: async stereo JPEG yolu eksik."
}
if ($writerText -notmatch "ArrayPool<byte>") {
    throw "v0.12.2 doğrulaması başarısız: pooled SBS write optimizasyonu eksik."
}
if ($graphicsText -notmatch "OnAcceleratedPaint" -or
    $graphicsText -notmatch "CopyResource\(cefTexture, _xrSharedTexture\)") {
    throw "v0.12.2 doğrulaması başarısız: A GPU-direct yolu eksik."
}
if ($xrText -notmatch "XR_ACTION_TYPE_POSE_INPUT" -or
    $xrText -notmatch "XR_ACTION_TYPE_FLOAT_INPUT" -or
    $xrText -notmatch "/interaction_profiles/oculus/touch_controller") {
    throw "v0.12.2 doğrulaması başarısız: Meta Touch input yolu eksik."
}
if ($xrText -notmatch "XrCompositionLayerProjection") {
    throw "v0.12.2 doğrulaması başarısız: projection layer bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.12.2] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.12.2] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.12.2] CEF/Windows x64 app publish..."
& dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained $selfContained `
    -o $appPublish `
    -p:Platform=x64 `
    -p:PublishReadyToRun=true
if ($LASTEXITCODE -ne 0) { throw "dotnet publish başarısız." }

Copy-Item (Join-Path $appPublish "*") $publishDir -Recurse -Force

$xrOut = Join-Path $publishDir "xr"
New-Item -ItemType Directory -Force -Path $xrOut | Out-Null

$xrExe = Get-ChildItem -Path $xrBuild -Filter "GeoGebraForQuestPC.XR.exe" -Recurse | Select-Object -First 1
if (-not $xrExe) { throw "GeoGebraForQuestPC.XR.exe bulunamadı." }
Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force

$loader = Get-ChildItem -Path $xrBuild -Filter "openxr_loader.dll" -Recurse | Select-Object -First 1
if ($loader) {
    Copy-Item $loader.FullName (Join-Path $xrOut "openxr_loader.dll") -Force
}

$sourceInfo = Join-Path $publishDir "assets\web\GeoGebra\GGQ_SOURCE_BUILD.txt"
if (-not (Test-Path $sourceInfo)) {
    throw "GGQ_SOURCE_BUILD.txt publish paketinde bulunamadı."
}
if (-not (Test-Path (Join-Path $publishDir "GeoGebraForQuestPC.exe"))) {
    throw "GeoGebraForQuestPC.exe publish paketinde bulunamadı."
}
if (-not (Test-Path (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe"))) {
    throw "OpenXR helper publish paketinde bulunamadı."
}

Write-Host ""
Write-Host "[GGQ-PC v0.12.2] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
Write-Host "PC:     Windows PerMonitorV2 DPI -> CEF DIP; native GeoGebra sizing"
Write-Host "A XR:   OpenXR runtime recommended per-eye projection; supersampling yok"
Write-Host "B XR:   angular-size matched 720..1600 px/göz; target A width 1680"
Write-Host "B UI:   3D viewport'a clip; dialog/menu/popup sırasında görünmez"
Write-Host "INPUT:  proven v0.12 Touch/input + native DIP coordinate mapping"
Write-Host "PAKET:  Tek ZIP katmanı"
