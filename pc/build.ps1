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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.11.2-cef-gpu-direct-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$xrMain = Join-Path $xrSource "main-v11.cpp"
$xrShared = Join-Path $xrSource "v11-shared.hpp"
$xrRender = Join-Path $xrSource "v11-render.hpp"
$mainForm = Join-Path $pcDir "MainFormV11.cs"
$graphics = Join-Path $pcDir "MainFormV11.Graphics.cs"
$inputStereo = Join-Path $pcDir "MainFormV11.InputStereo.cs"
$cefBrowser = Join-Path $pcDir "D3DChromiumWebBrowser.cs"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK bulunamadı."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake bulunamadı."
}
if (-not (Test-Path $boot)) {
    throw "Exp46 patched GeoGebra Web3D paketi yok. Önce CI asset extraction adımını çalıştırın."
}
foreach ($required in @($xrMain, $xrShared, $xrRender, $mainForm, $graphics, $inputStereo, $cefBrowser)) {
    if (-not (Test-Path $required)) {
        throw "v0.11.2 kaynak dosyası eksik: $required"
    }
}

$xrText = Get-Content $xrMain -Raw
$sharedText = Get-Content $xrShared -Raw
$graphicsText = Get-Content $graphics -Raw
$browserText = Get-Content $cefBrowser -Raw
$mainFormText = Get-Content $mainForm -Raw
$allV11 = $xrText + "`n" + $sharedText + "`n" + $graphicsText + "`n" + $browserText + "`n" + $mainFormText

if ($allV11 -match "BitBlt\s*\(") {
    throw "v0.11.2 doğrulaması başarısız: BitBlt ekran yakalaması bulundu."
}
if ($allV11 -match "Windows\.Graphics\.Capture|GraphicsCaptureItem|PrintWindow\s*\(") {
    throw "v0.11.2 doğrulaması başarısız: ekran yakalama API'si bulundu."
}
if ($browserText -notmatch "SharedTextureEnabled = true") {
    throw "v0.11.2 doğrulaması başarısız: CEF shared GPU texture etkin değil."
}
if ($browserText -match 'base\("about:blank"') {
    throw "v0.11.2 doğrulaması başarısız: CEF hâlâ about:blank ile oluşturuluyor."
}
if ($browserText -notmatch 'base\(initialAddress') {
    throw "v0.11.2 doğrulaması başarısız: gerçek başlangıç adresi CEF constructor'a bağlanmamış."
}
if ($browserText -notmatch "CreateGpuBrowser") {
    throw "v0.11.2 doğrulaması başarısız: geciktirilmiş native browser oluşturma yolu eksik."
}
if ($mainFormText -match '_browser\.Load\(LocalAppUrl\)') {
    throw "v0.11.2 doğrulaması başarısız: erken Load(LocalAppUrl) çağrısı hâlâ var."
}
if ($mainFormText -notmatch '_browser\.CreateGpuBrowser\(\)') {
    throw "v0.11.2 doğrulaması başarısız: event aboneliklerinden sonra CreateGpuBrowser çağrısı eksik."
}
if ($browserText -match "ExternalBeginFrameEnabled = true") {
    throw "v0.11.2 doğrulaması başarısız: eski external begin-frame yolu hâlâ etkin."
}
if ($browserText -notmatch "windowInfo.Width" -or $browserText -notmatch "windowInfo.Height") {
    throw "v0.11.2 doğrulaması başarısız: CEF başlangıç boyutu verilmemiş."
}
if ($graphicsText -notmatch "OnAcceleratedPaint") {
    throw "v0.11.2 doğrulaması başarısız: CEF accelerated paint yolu bulunamadı."
}
if ($graphicsText -match "SendExternalBeginFrame") {
    throw "v0.11.2 doğrulaması başarısız: manuel external frame çağrısı bulundu."
}
if ($graphicsText -notmatch 'new InputElement\("POSITION"') {
    throw "v0.11.2 doğrulaması başarısız: standart POSITION input layout eksik."
}
if ($graphicsText -notmatch "CullMode = CullMode.None") {
    throw "v0.11.2 doğrulaması başarısız: PC sunum rasterizer culling kapatılmamış."
}
if ($graphicsText -notmatch "CopyResource\(cefTexture, _xrSharedTexture\)") {
    throw "v0.11.2 doğrulaması başarısız: CEF -> uygulama-owned GPU texture kopyası bulunamadı."
}
if ($sharedText -notmatch "OpenSharedResource") {
    throw "v0.11.2 doğrulaması başarısız: XR shared GPU texture açma yolu bulunamadı."
}
if ($xrText -notmatch "XR_ACTION_TYPE_POSE_INPUT" -or
    $xrText -notmatch "XR_ACTION_TYPE_FLOAT_INPUT" -or
    $xrText -notmatch "/interaction_profiles/oculus/touch_controller") {
    throw "v0.11.2 doğrulaması başarısız: Meta Touch OpenXR input yolu eksik."
}
if ($xrText -notmatch "XrCompositionLayerProjection") {
    throw "v0.11.2 doğrulaması başarısız: projection layer bulunamadı."
}
if ($xrText -notmatch "rightEye" -and $xrText -notmatch "eye == 1") {
    throw "v0.11.2 doğrulaması başarısız: per-eye stereo yönlendirmesi bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.11.2] OpenXR GPU-direct configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.11.2] OpenXR GPU-direct build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.11.2] CEF/Windows x64 app publish..."
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

# Important: no inner ZIP here. GitHub Actions uploads this directory directly,
# therefore the downloadable Actions artifact is the one and only ZIP layer.
Write-Host ""
Write-Host "[GGQ-PC v0.11.2] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
Write-Host "A:      CEF D3D11 shared texture -> GPU-to-GPU -> OpenXR (screen capture yok)"
Write-Host "CEF:    GeoGebra gerçek initialAddress; about:blank erken Load yolu kaldırıldı"
Write-Host "PC:     POSITION shader + culling kapalı"
Write-Host "B:      Exp46 L/R -> per-eye projection"
Write-Host "INPUT:  Right Touch aim/trigger -> CEF GeoGebra"
Write-Host "XR:     Companion kapanırsa otomatik yeniden başlatılır"
Write-Host "PAKET:  Tek ZIP katmanı (Actions artifact doğrudan klasörü paketler)"
