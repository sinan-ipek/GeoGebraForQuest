from pathlib import Path

p = Path('pc/build.ps1')
t = p.read_text(encoding='utf-8')
t = t.replace('CAPTURE_JPEG_QUALITY = 0\\.99', 'CAPTURE_JPEG_QUALITY = 1\\.0')
t = t.replace('CAPTURE_JPEG_QUALITY = 0.99', 'CAPTURE_JPEG_QUALITY = 1.0')
p.write_text(t, encoding='utf-8')

p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
t = t.replace('private Rect _cefPopupRect;', 'private CefSharp.Structs.Rect _cefPopupRect;')
p.write_text(t, encoding='utf-8')

print('v0.13 build validation and popup Rect namespace fixed')
