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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.1.0-exp46-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"
$zip = Join-Path $distRoot "GeoGebraForQuest-PC-v0.1.0-exp46-win-x64.zip"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK bulunamadı."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake bulunamadı."
}
if (-not (Test-Path $boot)) {
    throw "Exp46 patched GeoGebra Web3D paketi yok. Önce Linux/CI build-web3d aşamasını çalıştırın."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC] OpenXR companion configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) { throw "OpenXR CMake configure başarısız." }

Write-Host "[GGQ-PC] OpenXR companion build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "OpenXR companion build başarısız." }

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC] Windows x64 app publish..."
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

# Depending on OpenXR-SDK CMake options, loader may be dynamic or linked without a sidecar.
$loader = Get-ChildItem -Path $xrBuild -Filter "openxr_loader.dll" -Recurse | Select-Object -First 1
if ($loader) {
    Copy-Item $loader.FullName (Join-Path $xrOut "openxr_loader.dll") -Force
    Write-Host "[GGQ-PC] Bundled OpenXR loader: $($loader.FullName)"
} else {
    Write-Host "[GGQ-PC] No loader DLL sidecar produced; XR target is using its configured loader linkage."
}

$sourceInfo = Join-Path $publishDir "assets\web\GeoGebra\GGQ_SOURCE_BUILD.txt"
if (-not (Test-Path $sourceInfo)) {
    throw "GGQ_SOURCE_BUILD.txt publish paketinde bulunamadı."
}

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $publishDir "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "[GGQ-PC] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "ZIP:    $zip"
Write-Host "APP:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
Write-Host "XR:     $(Join-Path $xrOut 'GeoGebraForQuestPC.XR.exe')"
