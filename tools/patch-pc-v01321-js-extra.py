from pathlib import Path


def req(text, needle, label):
    if needle not in text:
        raise SystemExit(label)


p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

fields = '''  var perfEncodeMsSum = 0;
  var perfEncodeMsMax = 0;
'''
req(s, fields, 'v0.13.21 JS extra: perf fields missing')
s = s.replace(fields, fields + '''  var perfCaptureMsSum = 0;
  var perfCaptureMsMax = 0;
  var perfCaptureCount = 0;
''', 1)

sample = '''      avgEncodeMs: completed ? perfEncodeMsSum / completed : 0,
      maxEncodeMs: perfEncodeMsMax,
'''
req(s, sample, 'v0.13.21 JS extra: sample marker missing')
s = s.replace(sample, sample + '''      avgCaptureMs: perfCaptureCount ? perfCaptureMsSum / perfCaptureCount : 0,
      maxCaptureMs: perfCaptureMsMax,
      captureCount: perfCaptureCount,
''', 1)

reset = '''    perfEncodeMsSum = 0;
    perfEncodeMsMax = 0;
'''
req(s, reset, 'v0.13.21 JS extra: reset marker missing')
s = s.replace(reset, reset + '''    perfCaptureMsSum = 0;
    perfCaptureMsMax = 0;
    perfCaptureCount = 0;
''', 1)

left = '''      leftCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );'''
req(s, left, 'v0.13.21 JS extra: left drawImage marker missing')
s = s.replace(left, '''      var perfCaptureStartedAt = performance.now();
      leftCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );''', 1)

right = '''      rightCaptureContext.drawImage(
        eyes.right,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );'''
req(s, right, 'v0.13.21 JS extra: right drawImage marker missing')
s = s.replace(right, right + '''
      var perfCaptureMs = Math.max(0, performance.now() - perfCaptureStartedAt);
      perfCaptureCount++;
      perfCaptureMsSum += perfCaptureMs;
      perfCaptureMsMax = Math.max(perfCaptureMsMax, perfCaptureMs);''', 1)

p.write_text(s, encoding='utf-8')
print('v0.13.21 JS capture/resize timing telemetry applied')
