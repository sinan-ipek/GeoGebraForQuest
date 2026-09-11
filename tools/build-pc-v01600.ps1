$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host '[v0.16.0] Preparing Exp46 web assets...'
New-Item -ItemType Directory -Force -Path '.exp46' | Out-Null
gh release download 'v0.9.30-exp46-hover-target-grip-focus' `
  --repo 'sinan-ipek/GeoGebraForQuest' `
  --pattern 'GeoGebraForQuest-v0.9.30-exp46-hover-target-grip-focus-debug.apk' `
  --dir '.exp46'
$apk = Get-ChildItem '.exp46' -Filter '*.apk' | Select-Object -First 1
if (-not $apk) { throw 'Exp46 APK missing' }
Copy-Item $apk.FullName '.exp46/exp46.zip' -Force
Expand-Archive '.exp46/exp46.zip' '.exp46/unpacked' -Force
$source = '.exp46/unpacked/assets/web'
if (Test-Path 'app/src/main/assets/web') {
  Remove-Item 'app/src/main/assets/web' -Recurse -Force
}
New-Item -ItemType Directory -Force -Path 'app/src/main/assets' | Out-Null
Copy-Item $source 'app/src/main/assets/web' -Recurse -Force

Write-Host '[v0.16.0] Preparing stereo splash artwork...'
$leftSplash = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/v0.9.22-splash-20fps/app/src/main/res/drawable-nodpi/stereo_splash_left.webp'
$rightSplash = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/v0.9.22-splash-20fps/app/src/main/res/drawable-nodpi/stereo_splash_right.webp'
Invoke-WebRequest $leftSplash -OutFile 'pc-xr/stereo_splash_left.webp'
Invoke-WebRequest $rightSplash -OutFile 'pc-xr/stereo_splash_right.webp'
python -m pip install --disable-pip-version-check --quiet pillow
@'
from PIL import Image
for side in ('left', 'right'):
    src = f'pc-xr/stereo_splash_{side}.webp'
    dst = f'pc-xr/stereo_splash_{side}.png'
    with Image.open(src) as im:
        im.convert('RGBA').save(dst, 'PNG')
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'Splash conversion failed' }

Write-Host '[v0.16.0] Applying known-working v0.13.22 stack...'
$patches = @(
  'patch-pc-v013.py',
  'patch-pc-v013-buildfix.py',
  'patch-pc-v0131.py',
  'patch-pc-v0132.py',
  'patch-pc-v0133-adapter.py',
  'patch-pc-v0133.py',
  'patch-pc-v0133-adapter.py',
  'patch-pc-v0134.py',
  'patch-pc-v0134-buildfix.py',
  'patch-pc-v0135.py',
  'patch-pc-v0135-buildfix.py',
  'patch-pc-v0136.py',
  'patch-pc-v0136-buildfix.py',
  'patch-pc-v0137.py',
  'patch-pc-v0137-buildfix.py',
  'patch-pc-v0138-prep.py',
  'patch-pc-v0138-prep2.py',
  'patch-pc-v0138.py',
  'patch-pc-v0138-buildfix.py',
  'patch-pc-v0139-direct.py',
  'patch-pc-v0139-buildfix.py',
  'patch-pc-v01310.py',
  'patch-pc-v01310-buildfix.py',
  'patch-pc-v01311.py',
  'patch-pc-v01311-extra.py',
  'patch-pc-v01311-postfix.py',
  'patch-pc-v01312-prep.py',
  'patch-pc-v01312-buildprep.py',
  'patch-pc-v01312.py',
  'patch-pc-v01313.py',
  'patch-pc-v01314.py',
  'patch-pc-v01315.py',
  'patch-pc-v01316.py',
  'patch-pc-v01317.py',
  'patch-pc-v01318-prep.py',
  'patch-pc-v01318.py',
  'patch-pc-v01318-buildfix.py',
  'patch-pc-v01319.py',
  'patch-pc-v01320.py',
  'patch-pc-v01321.py',
  'patch-pc-v01321-js-extra.py',
  'patch-pc-v01321-extra.py',
  'patch-pc-v01321-compilefix.py',
  'patch-pc-v01321-buildfix.py',
  'patch-pc-v01322.py',
  'patch-pc-v01322-compilefix.py'
)
foreach ($patch in $patches) {
  python (Join-Path 'tools' $patch)
  if ($LASTEXITCODE -ne 0) { throw "Failed: $patch" }
}

Write-Host '[v0.16.0] Importing proven v0.13.24 raw transport layer...'
$base1324 = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/6ec8b49d1a23f2eca3a2a3feba220a59589aa545/tools'
Invoke-WebRequest "$base1324/patch-pc-v01324.py" -OutFile 'tools/patch-pc-v01324-imported.py'
Invoke-WebRequest "$base1324/patch-pc-v01324-buildfix.py" -OutFile 'tools/patch-pc-v01324-buildfix-imported.py'
python tools/patch-pc-v01324-imported.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.24 transport patch failed' }
python tools/patch-pc-v01324-buildfix-imported.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.24 buildfix failed' }

Write-Host '[v0.16.0] Applying v0.13.27 through v0.13.35 stereo chain...'
python tools/patch-pc-v01327.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.27 failed' }
python tools/patch-pc-v01327-buildfix.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.27 buildfix failed' }
python tools/patch-pc-v01327-xr-compilefix.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.27 XR compilefix failed' }
python tools/patch-pc-v01328.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.28 failed' }
$runtimeUrl = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/checkpoint-v0.13.22-working-stereo/pc/pc-stereo-layout.js'
Invoke-WebRequest $runtimeUrl -OutFile 'pc/pc-stereo-layout.js'
python tools/patch-pc-v01329.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.29 failed' }
python tools/patch-pc-v01331.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.31 failed' }
python tools/patch-pc-v01335.py
if ($LASTEXITCODE -ne 0) { throw 'v0.13.35 failed' }

Write-Host '[v0.16.0] Installing pinned v0.14.1 GPU metadata/XR plumbing...'
$base14 = 'https://raw.githubusercontent.com/sinan-ipek/GeoGebraForQuest/57150449dd223d179a7d1ff844e50d3485afd51b/tools'
Invoke-WebRequest "$base14/patch-pc-v0141-prep.py" -OutFile 'tools/patch-pc-v0141-prep.py'
Invoke-WebRequest "$base14/patch-pc-v0141-host.py" -OutFile 'tools/patch-pc-v0141-host.py'
Invoke-WebRequest "$base14/patch-pc-v0141-xr.py" -OutFile 'tools/patch-pc-v0141-xr.py'

# Deliberately do NOT download patch-pc-v0142-prep.py here. The pinned v0.14.1
# prep checks for that file and would mutate the old v0.14.2 host rewrite. v0.16
# carries the relevant safety contracts in its own integration driver instead.
python tools/patch-pc-v0141-prep.py
if ($LASTEXITCODE -ne 0) { throw 'v0.14.1 prep failed' }
python tools/patch-pc-v0141-host.py
if ($LASTEXITCODE -ne 0) { throw 'v0.14.1 host plumbing failed' }
python tools/patch-pc-v0141-xr.py
if ($LASTEXITCODE -ne 0) { throw 'v0.14.1 XR plumbing failed' }

Write-Host '[v0.16.0] Applying direct GPU eye-pair integration driver...'
python tools/patch-pc-v01600-driver.py
if ($LASTEXITCODE -ne 0) { throw 'v0.16.0 integration driver failed' }

Write-Host '[v0.16.0] Verifying architecture...'
$runtime = Get-Content 'pc/pc-stereo-layout.js' -Raw
$graphics = Get-Content 'pc/MainFormV11.Graphics.cs' -Raw
$browser = Get-Content 'pc/D3DChromiumWebBrowser.cs' -Raw
$gpuHost = Get-Content 'pc/MainFormV141.GpuStereo.cs' -Raw
$publisher = Get-Content 'pc/StereoGpuTexturePublisher.cs' -Raw
$inputStereo = Get-Content 'pc/MainFormV11.InputStereo.cs' -Raw
$main = Get-Content 'pc/MainFormV11.cs' -Raw
$shared = Get-Content 'pc-xr/v11-shared.hpp' -Raw
$xr = Get-Content 'pc-xr/main-v11.cpp' -Raw
$render = Get-Content 'pc-xr/v11-render.hpp' -Raw
$index = Get-Content 'app/src/main/assets/web/index.html' -Raw
$project = Get-Content 'pc/GeoGebraForQuest.PC.csproj' -Raw
$build = Get-Content 'pc/build.ps1' -Raw

if ($runtime.Contains('getImageData(')) { throw 'CPU getImageData still present' }
if ($runtime.Contains('stereoRawPair')) { throw 'raw pixel IPC still present' }
if ($runtime.Contains('ggqRawStereoAck')) { throw 'raw ACK path still present' }
if ($runtime.Contains('readPixels(')) { throw 'WebGL readPixels present' }
if ($runtime.Contains('ggq-gpu-stereo-stage-v0141')) { throw 'v0.14 full-SBS stage leaked in' }
if (-not $runtime.Contains('ggq-gpu-left-eye-overlay-v0160')) { throw 'LEFT eye overlay missing' }
if (-not $runtime.Contains('window.ggqGpuResumeAfterCleanA')) { throw 'clean-A resume missing' }
if (-not $runtime.Contains('window.ggqGpuSetSuspended')) { throw 'GPU suspend bridge missing' }
if (-not $runtime.Contains('gpuStereoStageHidden')) { throw 'LEFT hidden bridge missing' }
if ($index.Contains('ggq-gpu-fullframe-sbs-v01339')) { throw 'failed v0.13.39 FBO bridge leaked in' }
if ($index.Contains('ggqGpuBindEyeFramebuffer')) { throw 'failed WebGL FBO interception leaked in' }
if (-not $graphics.Contains('TryConsumeGpuStereoV141PaintLocked')) { throw 'accelerated-paint GPU latch missing' }
if (-not $graphics.Contains('CompleteGpuStereoV141CleanAPaintLocked(aGpuPublishedV142)')) { throw 'clean-A success gate missing' }
if (-not $graphics.Contains('v0.13.35: D3D immediate-context state is global')) { throw 'PC viewport guard lost' }
if ($graphics.IndexOf('PaintElementType.Popup') -gt $graphics.IndexOf('TryConsumeGpuStereoV141PaintLocked')) { throw 'popup-first ordering lost' }
if (-not $browser.Contains('SharedTextureEnabled = true')) { throw 'CEF shared texture disabled' }
if (-not $browser.Contains('WindowlessFrameRate = 120')) { throw 'CEF 120 request missing' }
if (-not $gpuHost.Contains('CopySubresourceRegion(')) { throw 'GPU region copy missing' }
if (-not $gpuHost.Contains('AwaitCleanAPublish')) { throw 'clean-A gate missing' }
if (-not $gpuHost.Contains('2W x H direct GPU pair')) { throw 'cropped pair publisher missing' }
if (-not $gpuHost.Contains('_stereoGpuWorkingTexture')) { throw 'working GPU pair texture missing' }
if (-not $gpuHost.Contains('private void DeactivateGpuStereoV141()')) { throw 'GPU B deactivate helper missing' }
if (-not $gpuHost.Contains('private void SetGpuStereoV141UiSuspended(bool suspended)')) { throw 'GPU UI suspend helper missing' }
if (-not $inputStereo.Contains('DeactivateGpuStereoV141();')) { throw 'stereoInactive does not deactivate GPU-B' }
if (-not $inputStereo.Contains('SetGpuStereoV141UiSuspended(suspended);')) { throw 'UI suspend does not reach GPU-B' }
if (-not $main.Contains('Quest virtual keyboard disabled')) { throw 'Quest virtual keyboard still enabled' }
if (-not $publisher.Contains('GeoGebraForQuestPC_B_GPU_v1')) { throw 'B GPU metadata publisher missing' }
if (-not $shared.Contains('StereoGpuFrameInfoReader')) { throw 'XR B metadata reader missing' }
if (-not $xr.Contains('stereoGpuTexture_.Update')) { throw 'XR GPU B consumer missing' }
if (-not $xr.Contains('sbsFrame_.pixelFormat = 5')) { throw 'GPU B format marker missing' }
if (-not $render.Contains('pairFrame->pixelFormat == 5')) { throw 'FullSbs GPU sampling missing' }
if (-not $render.Contains('rightEye ? 0.5f : 0.0f')) { throw 'physical L/R eye mapping lost' }
if (-not $project.Contains('<Version>0.16.0</Version>')) { throw 'v0.16.0 version missing' }
if (-not $build.Contains('v0.16.0-gpu-eye-pair')) { throw 'v0.16.0 package label missing' }

Write-Host '[v0.16.0] Architecture verification passed.'
Write-Host '[v0.16.0] Building Windows package...'
& .\pc\build.ps1
if ($LASTEXITCODE -ne 0) { throw 'pc/build.ps1 failed' }

$dist = 'dist/GeoGebraForQuest-PC-v0.16.0-gpu-eye-pair-win-x64'
if (-not (Test-Path "$dist/GeoGebraForQuestPC.exe")) { throw 'Main EXE missing' }
if (-not (Test-Path "$dist/xr/GeoGebraForQuestPC.XR.exe")) { throw 'XR EXE missing' }

Write-Host '[v0.16.0] Windows package verified.'
