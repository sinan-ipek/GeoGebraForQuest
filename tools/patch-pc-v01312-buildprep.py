from pathlib import Path

# v0.13.12 build-prep is intentionally a no-op.
# The main v0.13.12 patch now owns the XR package copy block and expects the
# original v0.13.11 form:
#   Copy-Item $xrExe.FullName (Join-Path $xrOut "GeoGebraForQuestPC.XR.exe") -Force
# Normalizing that block here caused the following main patch to fail its
# deterministic marker check. Keep this file for workflow compatibility only.

p = Path('pc/build.ps1')
if not p.exists():
    raise SystemExit('v0.13.12 buildprep: pc/build.ps1 missing')

print('v0.13.12 buildprep: no-op; main patch owns XR package copy block')
