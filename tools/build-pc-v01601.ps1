$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$baseScript = Join-Path $PSScriptRoot 'build-pc-v01600.ps1'
if (-not (Test-Path $baseScript)) {
  throw 'build-pc-v01600.ps1 missing'
}

$pinnedBase = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/57150449dd223d179a7d1ff844e50d3485afd51b/pc'

$publisherUrl = "$pinnedBase/StereoGpuTexturePublisher.cs"
Invoke-WebRequest $publisherUrl -OutFile 'pc/StereoGpuTexturePublisher.cs'
if (-not (Test-Path 'pc/StereoGpuTexturePublisher.cs')) {
  throw 'v0.16.1 adapter: StereoGpuTexturePublisher.cs download failed'
}
$publisher = Get-Content 'pc/StereoGpuTexturePublisher.cs' -Raw
if (-not $publisher.Contains('GeoGebraForQuestPC_B_GPU_v1')) {
  throw 'v0.16.1 adapter: B GPU publisher mapping marker missing'
}

$telemetryUrl = "$pinnedBase/GpuStereoV141Telemetry.cs"
Invoke-WebRequest $telemetryUrl -OutFile 'pc/GpuStereoV141Telemetry.cs'
if (-not (Test-Path 'pc/GpuStereoV141Telemetry.cs')) {
  throw 'v0.16.3 adapter: GpuStereoV141Telemetry.cs download failed'
}
$telemetry = Get-Content 'pc/GpuStereoV141Telemetry.cs' -Raw
if (-not $telemetry.Contains('class GpuStereoV141Telemetry')) {
  throw 'v0.16.3 adapter: GPU stereo telemetry class marker missing'
}

$logBundleUrl = "$pinnedBase/LogBundle.cs"
Invoke-WebRequest $logBundleUrl -OutFile 'pc/LogBundle.cs'
if (-not (Test-Path 'pc/LogBundle.cs')) {
  throw 'v0.16.4 adapter: LogBundle.cs download failed'
}
$logBundle = Get-Content 'pc/LogBundle.cs' -Raw
if (-not $logBundle.Contains('static class LogBundle')) {
  throw 'v0.16.4 adapter: LogBundle class marker missing'
}

$baseText = Get-Content $baseScript -Raw
$verifyMarker = "Write-Host '[v0.16.0] Verifying architecture...'"
if (-not $baseText.Contains($verifyMarker)) {
  throw 'v0.16.2 adapter: architecture verification marker missing'
}
if (-not $baseText.Contains('patch-pc-v01602-buildguard.py')) {
  $guardBlock = @"
Write-Host '[v0.16.2] Updating inherited cache-busting build guard...'
python tools/patch-pc-v01602-buildguard.py
if (`$LASTEXITCODE -ne 0) { throw 'v0.16.2 cache-busting buildguard failed' }

"@
  $baseText = $baseText.Replace($verifyMarker, $guardBlock + $verifyMarker)
  Set-Content -Path $baseScript -Value $baseText -Encoding utf8
}

Write-Host '[v0.16.1] Restored pinned B GPU metadata publisher.'
Write-Host '[v0.16.3] Restored pinned GPU stereo telemetry source.'
Write-Host '[v0.16.4] Restored pinned log bundle source.'
Write-Host '[v0.16.2] Wired cache-busting build guard updater.'
& $baseScript
exit $LASTEXITCODE
