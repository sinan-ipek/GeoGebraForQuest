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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.12.3-xr-behind-native-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"

$xrWrapper = Join-Path $xrSource "main-v123.cpp"
$xrMain = Join-Path $xrSource "main-v11.cpp"
$xrShared = Join-Path $xrSource "v11-shared.hpp"
$xrRender = Join-Path $xrSource "v11-render.hpp"
$xrMouse = Join-Path $xrSource "v123-mouse.hpp"
$xrCmake = Join-Path $xrSource "CMakeLists.txt"

$mainForm = Join-Path $pcDir "MainFormV11.cs"
$graphics = Join-Path $pcDir "MainFormV11.Graphics.cs"
$inputStereo = Join-Path $pcDir "MainFormV11.InputStereo.cs"
$mouseWriter = Join-Path $pcDir "XrMouseSharedWriter.cs"
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
    $xrWrapper, $xrMain, $xrShared, $xrRender, $xrMouse, $xrCmake,
    $mainForm, $graphics, $inputStereo, $mouseWriter, $cefBrowser,
    $stereoRuntime, $stereoWriter)) {
    if (-not (Test-Path $required)) {
        throw "v0.12.3 kaynak dosyası eksik: $required"
    }
}

$wrapperText = Get-Content $xrWrapper -Raw
$xrText = Get-Content $xrMain -Raw
$sharedText = Get-Content $xrShared -Raw
$renderText = Get-Content $xrRender -Raw
$mouseXrText = Get-Content $xrMouse -Raw
$cmakeText = Get-Content $xrCmake -Raw
$graphicsText = Get-Content $graphics -Raw
$browserText = Get-Content $cefBrowser -Raw
$mainFormText = Get-Content $mainForm -Raw
$inputText = Get-Content $inputStereo -Raw
$mouseWriterText = Get-Content $mouseWriter -Raw
$runtimeText = Get-Content $stereoRuntime -Raw
$writerText = Get-Content $stereoWriter -Raw

$all = $wrapperText + "`n" + $xrText + "`n" + $sharedText + "`n" +
       $renderText + "`n" + $mouseXrText + "`n" + $graphicsText + "`n" +
       $browserText + "`n" + $mainFormText + "`n" + $inputText + "`n" +
       $mouseWriterText + "`n" + $runtimeText + "`n" + $writerText

if ($all -match "BitBlt\s*\(" -or
    $all -match "Windows\.Graphics\.Capture|GraphicsCaptureItem|PrintWindow\s*\(") {
    throw "v0.12.3 doğrulaması başarısız: ekran yakalama kodu bulundu."
}
if ($browserText -notmatch "SharedTextureEnabled = true") {
    throw "v0.12.3 doğrulaması başarısız: CEF shared GPU texture etkin değil."
}
if ($browserText -notmatch "WindowlessFrameRate = 60") {
    throw "v0.12.3 doğrulaması başarısız: CEF 60 fps tavanı korunmuyor."
}
if ($cmakeText -notmatch "main-v123\.cpp" -or
    $cmakeText -notmatch "HEADER_FILE_ONLY TRUE") {
    throw "v0.12.3 doğrulaması başarısız: Quest v0.12.3 XR wrapper build'e bağlı değil."
}
if ($cmakeText -match "main-v121\.cpp") {
    throw "v0.12.3 doğrulaması başarısız: eski +25% supersampling wrapper sızdı."
}
if ($wrapperText -notmatch "2064" -or
    $wrapperText -notmatch "2208" -or
    $wrapperText -notmatch "maxImageRectWidth" -or
    $wrapperText -notmatch "maxImageRectHeight") {
    throw "v0.12.3 doğrulaması başarısız: Quest 3 fiziksel 2064x2208 XR hedefi eksik."
}
if ($mainFormText -notmatch "0\.12\.3-xr-behind-native") {
    throw "v0.12.3 doğrulaması başarısız: stereo runtime cache-busting sürümü eksik."
}
if ($graphicsText -notmatch "DeviceDpi" -or
    $graphicsText -notmatch "DeviceScaleFactor = GetBrowserDeviceScaleFactor") {
    throw "v0.12.3 doğrulaması başarısız: native Windows DPI CEF'e bağlı değil."
}
if ($inputText -notmatch "clientW / dpiScale" -or
    $inputText -notmatch "SetStereoUiSuspended") {
    throw "v0.12.3 doğrulaması başarısız: native DIP viewport veya stereo UI suspension eksik."
}
if ($inputText -notmatch "Parallel\.Invoke") {
    throw "v0.12.3 doğrulaması başarısız: paralel L/R decode korunmuyor."
}
if ($inputText -notmatch "PublishMousePointerToXr" -or
    $inputText -notmatch "OnMouseLeave") {
    throw "v0.12.3 doğrulaması başarısız: fiziksel mouse -> Quest pointer yolu eksik."
}
if ($mouseWriterText -notmatch "GeoGebraForQuestPC_Mouse_v1" -or
    $mouseXrText -notmatch "GeoGebraForQuestPC_Mouse_v1") {
    throw "v0.12.3 doğrulaması başarısız: mouse shared-state protokolü eşleşmiyor."
}
if ($runtimeText -notmatch "QUEST3_PPD = 25\.0" -or
    $runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 1536" -or
    $runtimeText -notmatch "CAPTURE_JPEG_QUALITY = 0\.99") {
    throw "v0.12.3 doğrulaması başarısız: Quest-bazlı B kalite parametreleri eksik."
}
if ($runtimeText -notmatch "knownBlockingMenu" -or
    $runtimeText -notmatch "denseGridBlocked" -or
    $runtimeText -notmatch "clipAgainstPersistentEdgePanels" -or
    $runtimeText -notmatch "reportInactive\('ui-overlay'\)") {
    throw "v0.12.3 doğrulaması başarısız: GeoGebra menü/overlay öncelik yolu eksik."
}
if ($renderText -notmatch "behindDistance = kScreenDistanceMeters \+ 0\.02f" -or
    $renderText -notmatch "DrawBaseWithHole" -or
    $renderText -notmatch "footprint <= 1\.12") {
    throw "v0.12.3 doğrulaması başarısız: B-behind / XR transparent hole / quality minification eksik."
}
if ($renderText -notmatch "MousePointerSharedReader") {
    throw "v0.12.3 doğrulaması başarısız: Quest mouse cursor renderer eksik."
}
if ($graphicsText -match 'Present\(1,') {
    throw "v0.12.3 performans regresyonu: Present(1) bulundu."
}
if ($graphicsText -notmatch 'Present\(0,') {
    throw "v0.12.3 doğrulaması başarısız: non-blocking PC present yolu eksik."
}
if ($runtimeText -notmatch "canvas\.toBlob") {
    throw "v0.12.3 doğrulaması başarısız: async stereo JPEG yolu eksik."
}
if ($writerText -notmatch "ArrayPool<byte>") {
    throw "v0.12.3 doğrulaması başarısız: pooled SBS write optimizasyonu eksik."
}
if ($graphicsText -notmatch "OnAcceleratedPaint" -or
    $graphicsText -notmatch "CopyResource\(cefTexture, _xrSharedTexture\)") {
    throw "v0.12.3 doğrulaması başarısız: A GPU-direct yolu eksik."
}
if ($xrText -notmatch "XR_ACTION_TYPE_POSE_INPUT" -or
    $xrText -notmatch "XR_ACTION_TYPE_FLOAT_INPUT" -or
    $xrText -notmatch "/interaction_profiles/oculus/touch_controller") {
    throw "v0.12.3 doğrulaması başarısız: Meta Touch input yolu eksik."
}
if ($xrText -notmatch "XrCompositionLayerProjection") {
    throw "v0.12.3 doğrulaması başarısız: projection layer bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.12.3] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.12.3] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.12.3] CEF/Windows x64 app publish..."
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
Write-Host "[GGQ-PC v0.12.3] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
Write-Host "PC:     Windows PerMonitorV2 DPI -> CEF DIP; native GeoGebra sizing"
Write-Host "A XR:   Quest 3 physical target 2064x2208/göz, runtime maxImageRect ile clamp"
Write-Host "FILTER: XR 4-tap derivative minification; ince GeoGebra çizgileri için"
Write-Host "B XR:   Quest angular-density source; 640..1536 px/göz; A'nın 2 cm arkasında"
Write-Host "B UI:   XR-only transparent 3D hole; menu/dialog açılınca B inactive + A opaque"
Write-Host "INPUT:  Meta Touch ray + fiziksel mouse aynı anda GeoGebra/Quest'te"
Write-Host "PAKET:  Tek ZIP katmanı"
