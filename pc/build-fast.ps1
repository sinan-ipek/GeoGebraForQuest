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
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.13.34-gpu-fbo-sbs-win-x64"
$appPublish = Join-Path $root ".pc-app-publish"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET SDK bulunamadı."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake bulunamadı."
}
if (-not (Test-Path $boot)) {
    throw "GeoGebra Web3D runtime bulunamadı."
}
if (-not (Test-Path $project)) {
    throw "PC project bulunamadı."
}
if (-not (Test-Path (Join-Path $xrSource "CMakeLists.txt"))) {
    throw "XR CMakeLists.txt bulunamadı."
}

foreach ($dir in @($publishDir, $appPublish, $xrBuild)) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host "[GGQ-PC v0.13.34 FAST] OpenXR configure..."
& cmake -S $xrSource -B $xrBuild -A x64
if ($LASTEXITCODE -ne 0) {
    throw "OpenXR CMake configure başarısız."
}

Write-Host "[GGQ-PC v0.13.34 FAST] OpenXR build..."
& cmake --build $xrBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) {
    throw "OpenXR companion build başarısız."
}

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC v0.13.34 FAST] Windows app publish..."
& dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained $selfContained `
    -o $appPublish `
    -p:Platform=x64 `
    -p:PublishReadyToRun=true
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish başarısız."
}

Copy-Item (Join-Path $appPublish "*") $publishDir -Recurse -Force

$xrOut = Join-Path $publishDir "xr"
New-Item -ItemType Directory -Force -Path $xrOut | Out-Null

$xrExe = Get-ChildItem -Path $xrBuild -Filter "GeoGebraForQuestPC.XR.exe" -Recurse | Select-Object -First 1
if (-not $xrExe) {
    throw "GeoGebraForQuestPC.XR.exe bulunamadı."
}
Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force

$loader = Get-ChildItem -Path $xrBuild -Filter "openxr_loader.dll" -Recurse | Select-Object -First 1
if ($loader) {
    Copy-Item $loader.FullName (Join-Path $xrOut "openxr_loader.dll") -Force
}

$sourceInfo = Join-Path $publishDir "assets\web\GeoGebra\GGQ_SOURCE_BUILD.txt"
$appExe = Join-Path $publishDir "GeoGebraForQuestPC.exe"
$xrPublishedExe = Join-Path $xrOut "GeoGebraForQuestPC.XR.exe"

if (-not (Test-Path $sourceInfo)) {
    throw "GGQ_SOURCE_BUILD.txt publish paketinde bulunamadı."
}
if (-not (Test-Path $appExe)) {
    throw "GeoGebraForQuestPC.exe publish paketinde bulunamadı."
}
if (-not (Test-Path $xrPublishedExe)) {
    throw "OpenXR helper publish paketinde bulunamadı."
}

Write-Host ""
Write-Host "[GGQ-PC v0.13.34 FAST] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "APP:    $appExe"
Write-Host "XR:     $xrPublishedExe"
