$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$baseScript = Join-Path $PSScriptRoot 'build-pc-v01600.ps1'
if (-not (Test-Path $baseScript)) {
  throw 'build-pc-v01600.ps1 missing'
}

$publisherUrl = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/57150449dd223d179a7d1ff844e50d3485afd51b/pc/StereoGpuTexturePublisher.cs'
Invoke-WebRequest $publisherUrl -OutFile 'pc/StereoGpuTexturePublisher.cs'
if (-not (Test-Path 'pc/StereoGpuTexturePublisher.cs')) {
  throw 'v0.16.1 adapter: StereoGpuTexturePublisher.cs download failed'
}
$publisher = Get-Content 'pc/StereoGpuTexturePublisher.cs' -Raw
if (-not $publisher.Contains('GeoGebraForQuestPC_B_GPU_v1')) {
  throw 'v0.16.1 adapter: B GPU publisher mapping marker missing'
}

Write-Host '[v0.16.1] Restored pinned B GPU metadata publisher.'
& $baseScript
exit $LASTEXITCODE
