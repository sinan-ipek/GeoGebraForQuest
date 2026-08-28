param(
    [switch]$KeepWork
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dest = Join-Path $root "app\src\main\assets\web\GeoGebra"
$work = Join-Path $root ".geogebra-source-work-pc"
$src = Join-Path $work "geogebra"
$commit = "1d19a6ba1ed9fe4815d2cddc9b085c83d156f875"

function Require-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Gerekli komut bulunamadı: $name"
    }
}

Require-Command "git"
Require-Command "java"

$pythonMode = $null
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $pythonMode = "py"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonMode = "python"
} else {
    throw "Python 3 bulunamadı. Python 3 kurun ve PATH'e ekleyin."
}

function Invoke-PythonPatch([string]$scriptName) {
    $script = Join-Path $root "tools\$scriptName"
    Write-Host "[GGQ-PC] patch: $scriptName"
    if ($pythonMode -eq "py") {
        & py -3 $script $src
    } else {
        & python $script $src
    }
    if ($LASTEXITCODE -ne 0) { throw "$scriptName başarısız oldu." }
}

if (Test-Path $work) {
    Remove-Item $work -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $work | Out-Null

Write-Host "[GGQ-PC] GeoGebra source clone @ $commit"
& git clone --filter=blob:none --no-checkout https://github.com/geogebra/geogebra.git $src
if ($LASTEXITCODE -ne 0) { throw "GeoGebra clone başarısız." }

& git -C $src fetch --depth 1 origin $commit
if ($LASTEXITCODE -ne 0) { throw "GeoGebra commit fetch başarısız." }

& git -C $src checkout --detach $commit
if ($LASTEXITCODE -ne 0) { throw "GeoGebra checkout başarısız." }

# Quest v0.9.29 ile aynı Web3D stereo kaynak hattı.
Invoke-PythonPatch "patch-geogebra-quest.py"
Invoke-PythonPatch "patch-geogebra-quest-v097.py"
Invoke-PythonPatch "patch-geogebra-quest-v0913.py"
Invoke-PythonPatch "patch-geogebra-quest-v0918.py"
Invoke-PythonPatch "patch-geogebra-quest-v0919.py"
Invoke-PythonPatch "patch-geogebra-quest-v0927.py"
Invoke-PythonPatch "patch-geogebra-quest-v0928.py"

$webDir = Join-Path $src "source\web"
$gradle = Join-Path $src "gradlew.bat"
if (-not (Test-Path $gradle)) { throw "gradlew.bat bulunamadı: $gradle" }

Write-Host "[GGQ-PC] Patched GeoGebra Web3D derleniyor..."
Push-Location $webDir
try {
    & $gradle `
        :web:gwtCompile `
        :web:copyHtml `
        :web:mergeDeploy `
        "-Pgmodule=org.geogebra.web.Web3D" `
        "-PdeployggbRoot=./" `
        --no-daemon `
        --stacktrace
    if ($LASTEXITCODE -ne 0) { throw "GeoGebra Gradle build başarısız." }
} finally {
    Pop-Location
}

$war = Join-Path $src "source\web\web\war"
$deploy = Join-Path $war "deployggb.js"
$boot = Join-Path $war "web3d\web3d.nocache.js"
$css = Join-Path $war "css\bundles\bundle.css"

if (-not (Test-Path $deploy)) { throw "deployggb.js eksik." }
if (-not (Test-Path $boot)) { throw "web3d.nocache.js eksik." }
if (-not (Test-Path $css)) { throw "bundle.css eksik." }

if (Test-Path $dest) {
    Remove-Item $dest -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $war "*") $dest -Recurse -Force

$marker = @"
GeoGebraForQuest PC source build
version=0.1.0
upstream_commit=$commit
source_pipeline=GeoGebraForQuest v0.9.29-compatible patched Web3D
projection=PROJECTION_GLASSES full-colour stereo
renderer_eye_canvases=ggq-renderer-left-eye,ggq-renderer-right-eye
pc_bridge=WebView2 web message bridge
pc_stereo_preview=SBS native panel
quest_output=not enabled in PC v0.1.0
"@
Set-Content -Path (Join-Path $dest "GGQ_PC_SOURCE_BUILD.txt") -Value $marker -Encoding UTF8

Write-Host ""
Write-Host "[GGQ-PC] Tamam: $dest"
Write-Host "[GGQ-PC] deployggb.js: $deploy"
Write-Host "[GGQ-PC] web3d bootstrap: $boot"

if (-not $KeepWork) {
    Write-Host "[GGQ-PC] Geçici source çalışma klasörü temizleniyor..."
    Remove-Item $work -Recurse -Force
}
