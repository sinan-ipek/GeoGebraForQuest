from pathlib import Path
import runpy

# Compatibility alias used by the v0.13.28 workflow.
# The actual, proven v0.13.27 fix is kept in patch-pc-v01327-xr-compilefix.py.
target = Path(__file__).with_name('patch-pc-v01327-xr-compilefix.py')
if not target.exists():
    raise SystemExit('v0.13.27 XR compilefix target missing')
runpy.run_path(str(target), run_name='__main__')
