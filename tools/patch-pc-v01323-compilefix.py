from pathlib import Path

# v0.13.23 compile fixes after the no-JPEG transport rewrite.

p = Path('pc/MainFormV11.Graphics.cs')
s = p.read_text(encoding='utf-8')
s = s.replace(
    '        bool active; Rectangle rect; Size clientSize;\n',
    '        bool active; System.Drawing.Rectangle rect; System.Drawing.Size clientSize;\n',
    1)
s = s.replace(
    'MapMode.Read, MapFlags.None)',
    'MapMode.Read, SharpDX.Direct3D11.MapFlags.None)',
    1)
s = s.replace(
    '            new Rectangle(left, top, eyeWidth, eyeHeight), clientSize, frame);',
    '            new System.Drawing.Rectangle(left, top, eyeWidth, eyeHeight), clientSize, frame);',
    1)
p.write_text(s, encoding='utf-8')

p = Path('pc/MainFormV11.InputStereo.cs')
s = p.read_text(encoding='utf-8')
marker = '    private volatile bool _stereoUiSuspended;\n'
if marker not in s:
    raise SystemExit('v0.13.23 compilefix: stereoUiSuspended marker missing')
fields = '''    private volatile bool _stereoUiSuspended;\n    private long _xrLastValidMs;\n    private bool _xrADown;\n    private bool _xrGripDown;\n    private long _xrLastWheelMs;\n'''
s = s.replace(marker, fields, 1)
p.write_text(s, encoding='utf-8')

print('v0.13.23 C# compile ambiguities and XR input fields fixed')
