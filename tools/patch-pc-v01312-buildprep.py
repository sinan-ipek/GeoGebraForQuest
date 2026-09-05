from pathlib import Path

p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
old = '''$xrExe = Get-ChildItem -Path $xrBuild -Filter "GeoGebraForQuestPC.XR.exe" -Recurse | Select-Object -First 1
if (-not $xrExe) { throw "GeoGebraForQuestPC.XR.exe bulunamadı." }
Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force'''
new = '''$xrExe = Get-ChildItem -Path $xrBuild -Filter "GeoGebraForQuestPC.XR.exe" -Recurse | Select-Object -First 1
if (-not $xrExe) { throw "GeoGebraForQuestPC.XR.exe bulunamadı." }
$xrExe = $xrExe.FullName
$xrDist = $xrOut
Copy-Item $xrExe (Join-Path $xrDist "GeoGebraForQuestPC.XR.exe") -Force'''
if old not in t:
    raise SystemExit('v0.13.12 buildprep: XR package block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
print('v0.13.12 buildprep: XR copy marker normalized')
