param(
    [switch]$RebuildGeoGebra,
    [switch]$FrameworkDependent
)

$ErrorActionPreference = "Stop"

$pcDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $pcDir
$boot = Join-Path $root "app\src\main\assets\web\GeoGebra\web3d\web3d.nocache.js"
$project = Join-Path $pcDir "GeoGebraForQuest.PC.csproj"
$distRoot = Join-Path $root "dist"
$publishDir = Join-Path $distRoot "GeoGebraForQuest-PC-v0.1.0-win-x64"
$zip = Join-Path $distRoot "GeoGebraForQuest-PC-v0.1.0-win-x64.zip"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK bulunamadı. https://dotnet.microsoft.com/download/dotnet/8.0"
}

if ($RebuildGeoGebra -or -not (Test-Path $boot)) {
    Write-Host "[GGQ-PC] Patched GeoGebra Web3D paketi hazırlanıyor..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "tools\build-geogebra-pc.ps1")
    if ($LASTEXITCODE -ne 0) { throw "GeoGebra Web3D build başarısız." }
}

if (Test-Path $publishDir) {
    Remove-Item $publishDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

$selfContained = if ($FrameworkDependent) { "false" } else { "true" }

Write-Host "[GGQ-PC] Windows x64 publish..."
& dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained $selfContained `
    -o $publishDir `
    -p:PublishReadyToRun=true

if ($LASTEXITCODE -ne 0) { throw "dotnet publish başarısız." }

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $publishDir "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "[GGQ-PC] BUILD TAMAM"
Write-Host "Klasör: $publishDir"
Write-Host "ZIP:    $zip"
Write-Host "EXE:    $(Join-Path $publishDir 'GeoGebraForQuestPC.exe')"
