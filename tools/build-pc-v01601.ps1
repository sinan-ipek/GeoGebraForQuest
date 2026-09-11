$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$baseScript = Join-Path $PSScriptRoot 'build-pc-v01600.ps1'
if (-not (Test-Path $baseScript)) {
  throw 'build-pc-v01600.ps1 missing'
}

$text = Get-Content $baseScript -Raw
$old = "pc/StereoGpuTexturePublisher.cs"
$new = "pc/GpuSharedTexturePublisher.cs"
if (-not $text.Contains($old)) {
  throw 'v0.16.1 adapter: legacy publisher verifier marker missing'
}
$text = $text.Replace($old, $new)
Set-Content -Path $baseScript -Value $text -Encoding utf8

Write-Host '[v0.16.1] Corrected GPU publisher verifier path.'
& $baseScript
exit $LASTEXITCODE
