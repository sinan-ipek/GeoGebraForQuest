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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.12.0-performance-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$xrMain = Join-Path $xrSource "main-v11.cpp"
$xrShared = Join-Path $xrSource "v11-shared.hpp"
$xrRender = Join-Path $xrSource "v11-render.hpp"
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
    $xrMain, $xrShared, $xrRender, $mainForm, $graphics,
    $inputStereo, $cefBrowser, $stereoRuntime, $stereoWriter)) {
    if (-not (Test-Path $required)) {
        throw "v0.12 kaynak dosyası eksik: $required"
    }
}

$xrText = Get-Content $xrMain -Raw
$sharedText = Get-Content $xrShared -Raw
$graphicsText = Get-Content $graphics -Raw
$browserText = Get-Content $cefBrowser -Raw
$mainFormText = Get-Content $mainForm -Raw
$inputText = Get-Content $inputStereo -Raw
$runtimeText = Get-Content $stereoRuntime -Raw
$writerText = Get-Content $stereoWriter -Raw
$allV12 = $xrText + "`n" + $sharedText + "`n" + $graphicsText + "`n" +
          $browserText + "`n" + $mainFormText + "`n" + $inputText + "`n" +
          $runtimeText + "`n" + $writerText

if ($allV12 -match "BitBlt\s*\(") {
    throw "v0.12 doğrulaması başarısız: BitBlt ekran yakalaması bulundu."
}
if ($allV12 -match "Windows\.Graphics\.Capture|GraphicsCaptureItem|PrintWindow\s*\(") {
    throw "v0.12 doğrulaması başarısız: ekran yakalama API'si bulundu."
}
if ($browserText -notmatch "SharedTextureEnabled = true") {
    throw "v0.12 doğrulaması başarısız: CEF shared GPU texture etkin değil."
}
if ($browserText -match 'base\("about:blank"') {
    throw "v0.12 doğrulaması başarısız: CEF hâlâ about:blank ile oluşturuluyor."
}
if ($browserText -notmatch 'base\(initialAddress') {
    throw "v0.12 doğrulaması başarısız: gerçek başlangıç adresi CEF constructor'a bağlı değil."
}
if ($browserText -notmatch "CreateGpuBrowser") {
    throw "v0.12 doğrulaması başarısız: geciktirilmiş native browser oluşturma yolu eksik."
}
if ($mainFormText -match '_browser\.Load\(LocalAppUrl\)') {
    throw "v0.12 doğrulaması başarısız: erken Load(LocalAppUrl) çağrısı hâlâ var."
}
if ($mainFormText -notmatch '_browser\.CreateGpuBrowser\(\)') {
    throw "v0.12 doğrulaması başarısız: CreateGpuBrowser çağrısı eksik."
}
if ($graphicsText -match "WaitForGpuLocked") {
    throw "v0.12 performans regresyonu: CPU GPU-query bekleme yolu bulundu."
}
if ($graphicsText -match 'Present\(1,') {
    throw "v0.12 performans regresyonu: Present(1) VSync bekleme yolu bulundu."
}
if ($graphicsText -notmatch 'Present\(0,') {
    throw "v0.12 doğrulaması başarısız: non-blocking PC present yolu eksik."
}
if ($runtimeText -notmatch "canvas\.toBlob") {
    throw "v0.12 doğrulaması başarısız: async stereo JPEG yolu eksik."
}
if ($runtimeText -notmatch "CAPTURE_MAX_EYE_WIDTH = 2048") {
    throw "v0.12 doğrulaması başarısız: 2K/göz stereo kalite sınırı korunmuyor."
}
if ($inputText -notmatch "Math\.Clamp\(scale, 0\.5f, BrowserSupersample\)") {
    throw "v0.12 doğrulaması başarısız: 4K CEF boyut cap düzeltmesi eksik."
}
if ($writerText -notmatch "ArrayPool<byte>") {
    throw "v0.12 doğrulaması başarısız: SBS buffer reuse optimizasyonu eksik."
}
if ($graphicsText -notmatch "OnAcceleratedPaint") {
    throw "v0.12 doğrulaması başarısız: CEF accelerated paint yolu bulunamadı."
}
if ($graphicsText -notmatch 'new InputElement\("POSITION"') {
    throw "v0.12 doğrulaması başarısız: standart POSITION input layout eksik."
}
if ($graphicsText -notmatch "CopyResource\(cefTexture, _xrSharedTexture\)") {
    throw "v0.12 doğrulaması başarısız: CEF -> A GPU shared texture kopyası bulunamadı."
}
if ($sharedText -notmatch "OpenSharedResource") {
    throw "v0.12 doğrulaması başarısız: XR shared GPU texture açma yolu bulunamadı."
}
if ($xrText -notmatch "XR_ACTION_TYPE_POSE_INPUT" -or
    $xrText -notmatch "XR_ACTION_TYPE_FLOAT_INPUT" -or
    $xrText -notmatch "/interaction_profiles/oculus/touch_controller") {
    throw "v0.12 doğrulaması başarısız: Meta Touch OpenXR input yolu eksik."
}
if ($xrText -notmatch "XrCompositionLayerProjection") {
    throw "v0.12 doğrulaması başarısız: projection layer bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.12] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.12] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.12] CEF/Windows x64 app publish..."
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
Write-Host "[GGQ-PC v0.12] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
Write-Host "A:      CEF D3D11 GPU direct; 3072x2048 cap; CPU query wait yok"
Write-Host "PC:     Present(0), yalnız yeni CEF frame geldiğinde"
Write-Host "B:      Exp46 L/R 2048px/göz; async JPEG encode; pooled SBS copy"
Write-Host "INPUT:  Right Touch aim/trigger -> CEF GeoGebra"
Write-Host "PAKET:  Tek ZIP katmanı"
