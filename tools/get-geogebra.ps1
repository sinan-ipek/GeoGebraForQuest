$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$assets = Join-Path $projectRoot "app\src\main\assets\web"
$dest = Join-Path $assets "GeoGebra"
$tmp = Join-Path $env:TEMP "geogebra-math-apps-bundle.zip"
$unpack = Join-Path $env:TEMP "geogebra-math-apps-bundle-unpacked"
$url = "https://download.geogebra.org/package/geogebra-math-apps-bundle"

Write-Host "GeoGebra Math Apps Bundle indiriliyor..."
Invoke-WebRequest -Uri $url -OutFile $tmp

if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
Expand-Archive -Path $tmp -DestinationPath $unpack -Force

$deploy = Get-ChildItem -Path $unpack -Filter deployggb.js -Recurse | Select-Object -First 1
if (-not $deploy) { throw "Paket içinde deployggb.js bulunamadı." }

$bundleRoot = Split-Path -Parent $deploy.FullName
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $bundleRoot "*") $dest -Recurse -Force

Write-Host "Tamam: $dest"
Write-Host "Artık APK, GeoGebra web motorunu yerel asset olarak paketleyebilir."
