from pathlib import Path
import re


def req(text, needle, label):
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# JS: split the stereo pipeline into request -> eye-ready -> capture -> JPEG
# -> FileReader -> bridge -> complete, and measure scheduler/rAF behavior.
# This patch runs after v0.13.21 + js-extra.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

field_marker = '  var perfCaptureCount = 0;\n'
req(s, field_marker, 'v0.13.22 JS field marker missing')
s = s.replace(field_marker, field_marker + r'''
  var perfRafTicks = 0;
  var perfRafWhileEncoding = 0;
  var perfRafWhilePending = 0;
  var perfRafNoGeometry = 0;
  var perfRequestAttempts = 0;
  var perfRequestAccepted = 0;
  var perfRequestFailed = 0;
  var perfReadyCount = 0;
  var perfRequestToReadyMsSum = 0;
  var perfRequestToReadyMsMax = 0;
  var perfReadySerialDeltaSum = 0;
  var perfReadySerialDeltaMax = 0;
  var perfToBlobCount = 0;
  var perfToBlobMsSum = 0;
  var perfToBlobMsMax = 0;
  var perfFileReaderCount = 0;
  var perfFileReaderMsSum = 0;
  var perfFileReaderMsMax = 0;
  var perfBridgeCount = 0;
  var perfBridgeMsSum = 0;
  var perfBridgeMsMax = 0;
  var perfFullCycleCount = 0;
  var perfFullCycleMsSum = 0;
  var perfFullCycleMsMax = 0;
''', 1)

sample_marker = '''      captureCount: perfCaptureCount,
      avgPayloadChars: completed ? perfPayloadCharsSum / completed : 0,'''
req(s, sample_marker, 'v0.13.22 JS sample marker missing')
s = s.replace(sample_marker, '''      captureCount: perfCaptureCount,
      rafTicks: perfRafTicks,
      rafWhileEncoding: perfRafWhileEncoding,
      rafWhilePending: perfRafWhilePending,
      rafNoGeometry: perfRafNoGeometry,
      requestAttempts: perfRequestAttempts,
      requestAccepted: perfRequestAccepted,
      requestFailed: perfRequestFailed,
      readyCount: perfReadyCount,
      avgRequestToReadyMs: perfReadyCount ? perfRequestToReadyMsSum / perfReadyCount : 0,
      maxRequestToReadyMs: perfRequestToReadyMsMax,
      avgReadySerialDelta: perfReadyCount ? perfReadySerialDeltaSum / perfReadyCount : 0,
      maxReadySerialDelta: perfReadySerialDeltaMax,
      avgToBlobMs: perfToBlobCount ? perfToBlobMsSum / perfToBlobCount : 0,
      maxToBlobMs: perfToBlobMsMax,
      avgFileReaderMs: perfFileReaderCount ? perfFileReaderMsSum / perfFileReaderCount : 0,
      maxFileReaderMs: perfFileReaderMsMax,
      avgBridgeMs: perfBridgeCount ? perfBridgeMsSum / perfBridgeCount : 0,
      maxBridgeMs: perfBridgeMsMax,
      avgFullCycleMs: perfFullCycleCount ? perfFullCycleMsSum / perfFullCycleCount : 0,
      maxFullCycleMs: perfFullCycleMsMax,
      avgPayloadChars: completed ? perfPayloadCharsSum / completed : 0,''', 1)

reset_marker = '''    perfCaptureMsMax = 0;
    perfCaptureCount = 0;
    perfPayloadCharsSum = 0;'''
req(s, reset_marker, 'v0.13.22 JS reset marker missing')
s = s.replace(reset_marker, '''    perfCaptureMsMax = 0;
    perfCaptureCount = 0;
    perfRafTicks = 0;
    perfRafWhileEncoding = 0;
    perfRafWhilePending = 0;
    perfRafNoGeometry = 0;
    perfRequestAttempts = 0;
    perfRequestAccepted = 0;
    perfRequestFailed = 0;
    perfReadyCount = 0;
    perfRequestToReadyMsSum = 0;
    perfRequestToReadyMsMax = 0;
    perfReadySerialDeltaSum = 0;
    perfReadySerialDeltaMax = 0;
    perfToBlobCount = 0;
    perfToBlobMsSum = 0;
    perfToBlobMsMax = 0;
    perfFileReaderCount = 0;
    perfFileReaderMsSum = 0;
    perfFileReaderMsMax = 0;
    perfBridgeCount = 0;
    perfBridgeMsSum = 0;
    perfBridgeMsMax = 0;
    perfFullCycleCount = 0;
    perfFullCycleMsSum = 0;
    perfFullCycleMsMax = 0;
    perfPayloadCharsSum = 0;''', 1)

# Request attempts and accepted requests.
request_sig = '''  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') return false;
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) return false;'''
req(s, request_sig, 'v0.13.22 requestStereoPair marker missing')
s = s.replace(request_sig, '''  function requestStereoPair(now) {
    perfRequestAttempts++;
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') {
        perfRequestFailed++;
        return false;
      }
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) {
        perfRequestFailed++;
        return false;
      }
      perfRequestAccepted++;''', 1)

request_catch = '''    } catch (_) {
      return false;
    }
  }

  function computeCaptureSize'''
req(s, request_catch, 'v0.13.22 request catch marker missing')
s = s.replace(request_catch, '''    } catch (_) {
      perfRequestFailed++;
      return false;
    }
  }

  function computeCaptureSize''', 1)

# Split canvas.toBlob and FileReader latency per eye. Both calls share these
# aggregate counters; count is therefore eye-images, not stereo pairs.
blob_sig = '''  function canvasToDataUrlAsync(canvas) {
    return new Promise(function (resolve, reject) {
      if (!canvas || typeof canvas.toBlob !== 'function') {'''
req(s, blob_sig, 'v0.13.22 toBlob function marker missing')
s = s.replace(blob_sig, '''  function canvasToDataUrlAsync(canvas) {
    return new Promise(function (resolve, reject) {
      var perfBlobStartedAt = performance.now();
      if (!canvas || typeof canvas.toBlob !== 'function') {''', 1)

blob_cb = '''      canvas.toBlob(function (blob) {
        if (!blob) {'''
req(s, blob_cb, 'v0.13.22 toBlob callback marker missing')
s = s.replace(blob_cb, '''      canvas.toBlob(function (blob) {
        var perfBlobMs = Math.max(0, performance.now() - perfBlobStartedAt);
        perfToBlobCount++;
        perfToBlobMsSum += perfBlobMs;
        perfToBlobMsMax = Math.max(perfToBlobMsMax, perfBlobMs);
        if (!blob) {''', 1)

reader_marker = '''        var reader = new FileReader();
        reader.onload = function () { resolve(String(reader.result || '')); };'''
req(s, reader_marker, 'v0.13.22 FileReader marker missing')
s = s.replace(reader_marker, '''        var reader = new FileReader();
        var perfReaderStartedAt = performance.now();
        reader.onload = function () {
          var perfReaderMs = Math.max(0, performance.now() - perfReaderStartedAt);
          perfFileReaderCount++;
          perfFileReaderMsSum += perfReaderMs;
          perfFileReaderMsMax = Math.max(perfFileReaderMsMax, perfReaderMs);
          resolve(String(reader.result || ''));
        };''', 1)

# Eye-ready timing is the point at which the renderer serial advances after our
# explicit request. This isolates GeoGebra/renderer latency from JPEG transport.
poll_marker = '''    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    return beginAsyncStereoCapture(serial, requestedAt);'''
req(s, poll_marker, 'v0.13.22 poll marker missing')
s = s.replace(poll_marker, '''    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    var perfReadyMs = Math.max(0, now - requestedAt);
    var perfSerialDelta = Math.max(0, serial - pendingStereoSerial);
    perfReadyCount++;
    perfRequestToReadyMsSum += perfReadyMs;
    perfRequestToReadyMsMax = Math.max(perfRequestToReadyMsMax, perfReadyMs);
    perfReadySerialDeltaSum += perfSerialDelta;
    perfReadySerialDeltaMax = Math.max(perfReadySerialDeltaMax, perfSerialDelta);
    return beginAsyncStereoCapture(serial, requestedAt);''', 1)

# Measure the synchronous JS->CEF bridge call. This is important because the two
# Base64 strings can exceed hundreds of KB and serialization itself may stall JS.
bridge_marker = '''        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        lastDeliveredStereoSerial = serial;

        var now = performance.now();
        var renderLatency = Math.max(0, now - requestedAt);'''
req(s, bridge_marker, 'v0.13.22 bridge timing marker missing')
s = s.replace(bridge_marker, '''        var perfBridgeStartedAt = performance.now();
        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        var perfBridgeMs = Math.max(0, performance.now() - perfBridgeStartedAt);
        perfBridgeCount++;
        perfBridgeMsSum += perfBridgeMs;
        perfBridgeMsMax = Math.max(perfBridgeMsMax, perfBridgeMs);
        lastDeliveredStereoSerial = serial;

        var now = performance.now();
        var renderLatency = Math.max(0, now - requestedAt);
        perfFullCycleCount++;
        perfFullCycleMsSum += renderLatency;
        perfFullCycleMsMax = Math.max(perfFullCycleMsMax, renderLatency);''', 1)

# rAF state accounting. This tells us whether the browser event loop is still
# ticking at headset cadence while encode/bridge work is active.
loop_sig = '''  function captureLoop(now) {
    if (encodingInFlight) {
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!geometryState) {'''
req(s, loop_sig, 'v0.13.22 captureLoop marker missing')
s = s.replace(loop_sig, '''  function captureLoop(now) {
    perfRafTicks++;
    if (encodingInFlight) {
      perfRafWhileEncoding++;
      requestAnimationFrame(captureLoop);
      return;
    }

    if (!geometryState) {
      perfRafNoGeometry++;''', 1)

pending_marker = '''    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);'''
req(s, pending_marker, 'v0.13.22 pending rAF marker missing')
s = s.replace(pending_marker, '''    if (pendingStereoSerial !== null) {
      perfRafWhilePending++;
      pollRequestedStereoPair(now);''', 1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# XR: preserve all restart/session telemetry instead of truncating the CSV.
# Add session_id to every row so multiple OpenXR restarts can be analyzed.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

field_marker = '    std::ofstream perfCsv_;\n'
req(s, field_marker, 'v0.13.22 XR session field marker missing')
s = s.replace(field_marker, field_marker + '    std::string perfSessionId_;\n', 1)

init_old = '''        file += "GeoGebraForQuestPC.Performance.XR.csv";
        perfCsv_.open(file, std::ios::out | std::ios::trunc);
        if (perfCsv_.is_open()) {
            perfCsv_ << "elapsed_s,xr_fps,a_updates_fps,b_updates_fps,b_missed_frames,"'''
req(s, init_old, 'v0.13.22 XR PerfInitialize marker missing')
s = s.replace(init_old, '''        file += "GeoGebraForQuestPC.Performance.XR.csv";
        const auto perfPid = static_cast<unsigned long long>(GetCurrentProcessId());
        const auto perfTick = static_cast<unsigned long long>(GetTickCount64());
        perfSessionId_ = std::to_string(perfPid) + "-" + std::to_string(perfTick);

        bool perfNeedsHeader = true;
        {
            std::ifstream existing(file, std::ios::binary | std::ios::ate);
            if (existing.good() && existing.tellg() > 0) perfNeedsHeader = false;
        }
        perfCsv_.open(file, std::ios::out | std::ios::app);
        if (perfCsv_.is_open() && perfNeedsHeader) {
            perfCsv_ << "session_id,elapsed_s,xr_fps,a_updates_fps,b_updates_fps,b_missed_frames,"''', 1)

row_marker = '''        perfCsv_ << std::fixed << std::setprecision(3)
                 << elapsed << ','
                 << perfFrames_ / seconds << ','
'''
req(s, row_marker, 'v0.13.22 XR row marker missing')
s = s.replace(row_marker, '''        perfCsv_ << std::fixed << std::setprecision(3)
                 << perfSessionId_ << ','
                 << elapsed << ','
                 << perfFrames_ / seconds << ','
''', 1)

# Version/package labels after all previous patches have run.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p2 = Path(file)
    text = p2.read_text(encoding='utf-8')
    text = text.replace('0.13.21-performance-telemetry', '0.13.22-performance-stage-timing')
    text = text.replace('v0.13.21', 'v0.13.22')
    if file.endswith('.csproj'):
        text = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.22</Version>', text, count=1)
        text = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.22.0</FileVersion>', text, count=1)
        text = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.22.0</AssemblyVersion>', text, count=1)
    p2.write_text(text, encoding='utf-8')

p.write_text(s, encoding='utf-8')
print('GeoGebraForQuest PC v0.13.22 stage timing + persistent XR telemetry patch applied')
