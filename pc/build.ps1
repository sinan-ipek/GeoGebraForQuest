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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.6.0-exp46-projection-stereo-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$zip = Join-Path $distRoot "GeoGebraForQuest-PC-v0.6.0-exp46-projection-stereo-win-x64.zip"
$projectionSource = Join-Path $xrSource "main-v06.cpp"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK bulunamadı."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake bulunamadı."
}
if (-not (Test-Path $boot)) {
    throw "Exp46 patched GeoGebra Web3D paketi yok. Önce CI asset extraction adımını çalıştırın."
}
if (-not (Test-Path $projectionSource)) {
    throw "v0.6 projection stereo XR kaynağı bulunamadı."
}

$projectionText = Get-Content $projectionSource -Raw
if ($projectionText -notmatch "XrCompositionLayerProjection") {
    throw "v0.6 doğrulaması başarısız: projection layer bulunamadı."
}
if ($projectionText -match "XrCompositionLayerQuad") {
    throw "v0.6 doğrulaması başarısız: XR kaynağında Quad layer kalmış."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.6] OpenXR PRIMARY_STEREO projection configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC v0.6] OpenXR PRIMARY_STEREO projection build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.6] Windows x64 app publish..."
& dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained $selfContained `
    -o $appPublish `
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

$pcStereo = Join-Path $publishDir "pc-stereo-layout.js"
if (-not (Test-Path $pcStereo)) {
    throw "pc-stereo-layout.js publish paketinde bulunamadı."
}

$pcStereoText = Get-Content $pcStereo -Raw
if ($pcStereoText -notmatch "CAPTURE_MAX_EYE_WIDTH = 2048") {
    throw "High-Res stereo runtime doğrulaması başarısız: 2048 px eye-width ayarı bulunamadı."
}
if ($pcStereoText -notmatch "CAPTURE_JPEG_QUALITY = 0.95") {
    throw "High-Res stereo runtime doğrulaması başarısız: JPEG kalite ayarı bulunamadı."
}

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $publishDir "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "[GGQ-PC v0.6] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "ZIP:    $zip"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
