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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.13.1-gpu-stereo-fix-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"

$xrMain = Join-Path $xrSource "main-v13.cpp"
$xrShared = Join-Path $xrSource "v11-shared.hpp"
$xrRender = Join-Path $xrSource "v11-render.hpp"
$xrStereo = Join-Path $xrSource "v13-gpu-stereo.hpp"
$mainForm = Join-Path $pcDir "MainFormV11.cs"
$graphics = Join-Path $pcDir "MainFormV11.Graphics.cs"
$inputStereo = Join-Path $pcDir "MainFormV11.InputStereo.cs"
$cefBrowser = Join-Path $pcDir "D3DChromiumWebBrowser.cs"
$stereoRuntime = Join-Path $pcDir "pc-stereo-layout.js"
$gpuStereoPublisher = Join-Path $pcDir "GpuStereoTexturePublisher.cs"
$xrManager = Join-Path $pcDir "XrCompanionManager.cs"

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
    $xrMain, $xrShared, $xrRender, $xrStereo,
    $mainForm, $graphics, $inputStereo, $cefBrowser,
    $stereoRuntime, $gpuStereoPublisher, $xrManager)) {
    if (-not (Test-Path $required)) {
        throw "v0.13.1 kaynak dosyası eksik: $required"
    }
}

$xrText = Get-Content $xrMain -Raw
$xrStereoText = Get-Content $xrStereo -Raw
$graphicsText = Get-Content $graphics -Raw
$browserText = Get-Content $cefBrowser -Raw
$mainFormText = Get-Content $mainForm -Raw
$inputText = Get-Content $inputStereo -Raw
$runtimeText = Get-Content $stereoRuntime -Raw
$gpuStereoPublisherText = Get-Content $gpuStereoPublisher -Raw
$xrManagerText = Get-Content $xrManager -Raw
$allV13 = $xrText + "`n" + $xrStereoText + "`n" + $graphicsText + "`n" +
          $browserText + "`n" + $mainFormText + "`n" + $inputText + "`n" +
          $runtimeText + "`n" + $gpuStereoPublisherText + "`n" + $xrManagerText

if ($allV13 -match "BitBlt\s*\(" -or
    $allV13 -match "Windows\.Graphics\.Capture|GraphicsCaptureItem|PrintWindow\s*\(") {
    throw "v0.13.1 doğrulaması başarısız: ekran yakalama kodu bulundu."
}
if ($browserText -notmatch "SharedTextureEnabled = true") {
    throw "v0.13.1 doğrulaması başarısız: CEF shared GPU texture etkin değil."
}
if ($runtimeText -match "toDataURL|toBlob|image/jpeg|FileReader") {
    throw "v0.13.1 doğrulaması başarısız: JPEG/base64 stereo taşıma kodu hâlâ var."
}
if ($inputText -match "DecodeDataUrl|Convert\.FromBase64String\(dataUrl|QueueStereoFrames") {
    throw "v0.13.1 doğrulaması başarısız: CPU stereo decode yolu hâlâ aktif."
}
if ($runtimeText -notmatch "STEREO_INTERVAL_MS = 33") {
    throw "v0.13.1 doğrulaması başarısız: 30 Hz B GPU taşıma sınırı eksik."
}
if ($runtimeText -notmatch "stereoGpuPhase" -or
    $runtimeText -notmatch "ggq-pc-gpu-left-eye-overlay") {
    throw "v0.13.1 doğrulaması başarısız: GPU stereo compositor phase yolu eksik."
}
if ($graphicsText -notmatch "CaptureStereoGpuPhaseLocked" -or
    $graphicsText -notmatch "CopySubresourceRegion") {
    throw "v0.13.1 doğrulaması başarısız: CEF 3D bölgesinin GPU crop yolu eksik."
}
if ($graphicsText -notmatch "GpuStereoTexturePublisher" -and
    $mainFormText -notmatch "GpuStereoTexturePublisher") {
    throw "v0.13.1 doğrulaması başarısız: B GPU metadata publisher kullanılmıyor."
}
if ($graphicsText -match "WaitForGpuLocked") {
    throw "v0.13.1 performans regresyonu: GeoGebra/CEF tarafında CPU GPU-query bekleme yolu bulundu."
}
if ($graphicsText -match 'Present\(1,') {
    throw "v0.13.1 performans regresyonu: Present(1) VSync bekleme yolu bulundu."
}
if ($graphicsText -notmatch "_presentEvent\.WaitOne") {
    throw "v0.13.1 doğrulaması başarısız: event-driven PC present yolu eksik."
}
if ($xrStereoText -notmatch "SharedGpuTextureCache" -or
    $xrStereoText -notmatch "D3D11_QUERY_EVENT" -or
    $xrStereoText -notmatch "GetData\(") {
    throw "v0.13.1 doğrulaması başarısız: XR-only güvenli GPU cache senkronizasyonu eksik."
}
if ($inputText -notmatch "questBalancedMaxWidth = 2880" -or
    $inputText -notmatch "questBalancedMaxHeight = 1800") {
    throw "v0.13.1 doğrulaması başarısız: dengeli CEF viewport sınırı eksik."
}
if ($xrManagerText -notmatch "WmClose" -or
    $xrManagerText -notmatch "owner\.Stop\(\)") {
    throw "v0.13.1 doğrulaması başarısız: ana pencere kapanışında XR stop güvenliği eksik."
}
if ($xrText -notmatch "kProjectionResolutionScale = 1\.30f") {
    throw "v0.13.1 doğrulaması başarısız: yüksek çözünürlüklü Quest projection ayarı eksik."
}
if ($xrText -notmatch "StereoGpuFrameInfoReader" -or
    $xrText -notmatch "stereoTexture_\.Srv\(\)") {
    throw "v0.13.1 doğrulaması başarısız: B GPU texture OpenXR'a bağlanmamış."
}
if ($xrText -notmatch "XR_ACTION_TYPE_POSE_INPUT" -or
    $xrText -notmatch "XR_ACTION_TYPE_FLOAT_INPUT" -or
    $xrText -notmatch "/interaction_profiles/oculus/touch_controller") {
    throw "v0.13.1 doğrulaması başarısız: Meta Touch OpenXR input yolu eksik."
}
if ($xrText -notmatch "XrCompositionLayerProjection") {
    throw "v0.13.1 doğrulaması başarısız: projection layer bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.13.1] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.13.1] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.13.1] CEF/Windows x64 app publish..."
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
Write-Host "[GGQ-PC v0.13.1] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
Write-Host "A:      CEF D3D11 GPU -> shared GPU -> synchronized XR GPU cache"
Write-Host "B:      Exp46 L/R -> CEF GPU phase @30 Hz -> shared GPU -> synchronized XR cache"
Write-Host "PIXELS: JPEG/base64/Bitmap/CPU stereo transport yok"
Write-Host "QUEST:  recommended projection x1.30, runtime max/cap sınırında"
Write-Host "CEF:    2880x1800 balanced viewport ceiling"
Write-Host "CLOSE:  main WM_CLOSE -> XR child immediate Stop()"
Write-Host "INPUT:  mevcut sağ Touch aim/trigger yolu korunuyor"
Write-Host "PAKET:  Tek ZIP katmanı"
