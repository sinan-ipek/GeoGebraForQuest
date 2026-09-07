from pathlib import Path
import re


def req(text, needle, label):
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) JS: split the B pipeline into request -> stereo-ready -> capture -> JPEG
#    -> bridge stages, plus actual request cadence and RAF waiting states.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

field_marker = '''  var perfPayloadCharsSum = 0;
  var perfPayloadCharsMax = 0;
'''
req(s, field_marker, 'v0.13.22 JS field marker missing')
s = s.replace(field_marker, field_marker + '''  var perfRequestCount = 0;
  var perfRequestFailed = 0;
  var perfRequestCallMsSum = 0;
  var perfRequestCallMsMax = 0;
  var perfReadyCount = 0;
  var perfRequestToReadyMsSum = 0;
  var perfRequestToReadyMsMax = 0;
  var perfRequestIntervalCount = 0;
  var perfRequestIntervalMsSum = 0;
  var perfRequestIntervalMsMax = 0;
  var perfLastRequestAt = 0;
  var perfPendingRafFrames = 0;
  var perfEncodingRafFrames = 0;
  var perfIntervalWaitRafFrames = 0;
  var perfPendingPolls = 0;
  var perfSerialDeltaSum = 0;
  var perfSerialDeltaMax = 0;
  var perfBridgeCount = 0;
  var perfBridgeMsSum = 0;
  var perfBridgeMsMax = 0;
  var perfCycleCount = 0;
  var perfCycleMsSum = 0;
  var perfCycleMsMax = 0;
''', 1)

sample_marker = '''      maxPayloadChars: perfPayloadCharsMax,
      leftWidth: leftCaptureCanvas.width || 0,'''
req(s, sample_marker, 'v0.13.22 JS sample marker missing')
s = s.replace(sample_marker, '''      maxPayloadChars: perfPayloadCharsMax,
      requestCount: perfRequestCount,
      requestFailed: perfRequestFailed,
      actualRequestFps: perfRequestCount * 1000 / elapsed,
      avgRequestCallMs: perfRequestCount ? perfRequestCallMsSum / perfRequestCount : 0,
      maxRequestCallMs: perfRequestCallMsMax,
      readyCount: perfReadyCount,
      actualReadyFps: perfReadyCount * 1000 / elapsed,
      avgRequestToReadyMs: perfReadyCount ? perfRequestToReadyMsSum / perfReadyCount : 0,
      maxRequestToReadyMs: perfRequestToReadyMsMax,
      avgRequestIntervalMs: perfRequestIntervalCount ? perfRequestIntervalMsSum / perfRequestIntervalCount : 0,
      maxRequestIntervalMs: perfRequestIntervalMsMax,
      pendingRafFrames: perfPendingRafFrames,
      encodingRafFrames: perfEncodingRafFrames,
      intervalWaitRafFrames: perfIntervalWaitRafFrames,
      pendingPolls: perfPendingPolls,
      avgSerialDelta: perfReadyCount ? perfSerialDeltaSum / perfReadyCount : 0,
      maxSerialDelta: perfSerialDeltaMax,
      avgBridgeMs: perfBridgeCount ? perfBridgeMsSum / perfBridgeCount : 0,
      maxBridgeMs: perfBridgeMsMax,
      avgCycleMs: perfCycleCount ? perfCycleMsSum / perfCycleCount : 0,
      maxCycleMs: perfCycleMsMax,
      leftWidth: leftCaptureCanvas.width || 0,''', 1)

reset_marker = '''    perfPayloadCharsSum = 0;
    perfPayloadCharsMax = 0;
'''
req(s, reset_marker, 'v0.13.22 JS reset marker missing')
s = s.replace(reset_marker, reset_marker + '''    perfRequestCount = 0;
    perfRequestFailed = 0;
    perfRequestCallMsSum = 0;
    perfRequestCallMsMax = 0;
    perfReadyCount = 0;
    perfRequestToReadyMsSum = 0;
    perfRequestToReadyMsMax = 0;
    perfRequestIntervalCount = 0;
    perfRequestIntervalMsSum = 0;
    perfRequestIntervalMsMax = 0;
    perfPendingRafFrames = 0;
    perfEncodingRafFrames = 0;
    perfIntervalWaitRafFrames = 0;
    perfPendingPolls = 0;
    perfSerialDeltaSum = 0;
    perfSerialDeltaMax = 0;
    perfBridgeCount = 0;
    perfBridgeMsSum = 0;
    perfBridgeMsMax = 0;
    perfCycleCount = 0;
    perfCycleMsSum = 0;
    perfCycleMsMax = 0;
''', 1)

request_old = '''  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') return false;
      var baseline = Number(window.ggqRequestStereoFrame());
      if (!isFinite(baseline) || baseline < 0) return false;
      pendingStereoSerial = baseline;
      pendingStereoRequestedAt = now;
      return true;
    } catch (_) {
      return false;
    }
  }
'''
req(s, request_old, 'v0.13.22 requestStereoPair marker missing')
request_new = '''  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') {
        perfRequestFailed++;
        return false;
      }

      if (perfLastRequestAt > 0) {
        var requestInterval = Math.max(0, now - perfLastRequestAt);
        perfRequestIntervalCount++;
        perfRequestIntervalMsSum += requestInterval;
        perfRequestIntervalMsMax = Math.max(perfRequestIntervalMsMax, requestInterval);
      }
      perfLastRequestAt = now;

      var requestCallStartedAt = performance.now();
      var baseline = Number(window.ggqRequestStereoFrame());
      var requestCallMs = Math.max(0, performance.now() - requestCallStartedAt);
      perfRequestCount++;
      perfRequestCallMsSum += requestCallMs;
      perfRequestCallMsMax = Math.max(perfRequestCallMsMax, requestCallMs);

      if (!isFinite(baseline) || baseline < 0) {
        perfRequestFailed++;
        return false;
      }
      pendingStereoSerial = baseline;
      pendingStereoRequestedAt = now;
      return true;
    } catch (_) {
      perfRequestFailed++;
      return false;
    }
  }
'''
s = s.replace(request_old, request_new, 1)

poll_old = '''  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null || encodingInFlight) return false;

    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    return beginAsyncStereoCapture(serial, requestedAt);
  }
'''
req(s, poll_old, 'v0.13.22 pollRequestedStereoPair marker missing')
poll_new = '''  function pollRequestedStereoPair(now) {
    if (pendingStereoSerial === null || encodingInFlight) return false;

    perfPendingPolls++;
    var serial = readStereoFrameSerial();
    if (serial <= pendingStereoSerial) return false;

    var requestedAt = pendingStereoRequestedAt;
    var readyLatency = Math.max(0, now - requestedAt);
    var serialDelta = Math.max(0, serial - pendingStereoSerial);
    perfReadyCount++;
    perfRequestToReadyMsSum += readyLatency;
    perfRequestToReadyMsMax = Math.max(perfRequestToReadyMsMax, readyLatency);
    perfSerialDeltaSum += serialDelta;
    perfSerialDeltaMax = Math.max(perfSerialDeltaMax, serialDelta);
    return beginAsyncStereoCapture(serial, requestedAt);
  }
'''
s = s.replace(poll_old, poll_new, 1)

bridge_old = '''        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        lastDeliveredStereoSerial = serial;

        var now = performance.now();
        var renderLatency = Math.max(0, now - requestedAt);'''
req(s, bridge_old, 'v0.13.22 bridge timing marker missing')
s = s.replace(bridge_old, '''        var perfBridgeStartedAt = performance.now();
        bridgeStereoEyes(leftDataUrl, rightDataUrl);
        var perfBridgeMs = Math.max(0, performance.now() - perfBridgeStartedAt);
        perfBridgeCount++;
        perfBridgeMsSum += perfBridgeMs;
        perfBridgeMsMax = Math.max(perfBridgeMsMax, perfBridgeMs);
        lastDeliveredStereoSerial = serial;

        var now = performance.now();
        var renderLatency = Math.max(0, now - requestedAt);
        perfCycleCount++;
        perfCycleMsSum += renderLatency;
        perfCycleMsMax = Math.max(perfCycleMsMax, renderLatency);''', 1)

loop_encoding = '''    if (encodingInFlight) {
      requestAnimationFrame(captureLoop);
      return;
    }
'''
req(s, loop_encoding, 'v0.13.22 encoding RAF marker missing')
s = s.replace(loop_encoding, '''    if (encodingInFlight) {
      perfEncodingRafFrames++;
      requestAnimationFrame(captureLoop);
      return;
    }
''', 1)

loop_pending = '''    if (pendingStereoSerial !== null) {
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }
'''
req(s, loop_pending, 'v0.13.22 pending RAF marker missing')
s = s.replace(loop_pending, '''    if (pendingStereoSerial !== null) {
      perfPendingRafFrames++;
      pollRequestedStereoPair(now);
      requestAnimationFrame(captureLoop);
      return;
    }
''', 1)

loop_interval = '''    if (now < nextStereoRequestAt) {
      requestAnimationFrame(captureLoop);
      return;
    }
'''
req(s, loop_interval, 'v0.13.22 interval wait RAF marker missing')
s = s.replace(loop_interval, '''    if (now < nextStereoRequestAt) {
      perfIntervalWaitRafFrames++;
      requestAnimationFrame(captureLoop);
      return;
    }
''', 1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) XR: never truncate telemetry on a companion restart. Every XR process gets
#    a unique session_id, and all sessions append into one CSV in the xr folder.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

field_marker = '    std::ofstream perfCsv_;\n'
req(s, field_marker, 'v0.13.22 XR session field marker missing')
s = s.replace(field_marker, field_marker + '    std::string perfSessionId_;\n', 1)

start = s.find('    void PerfInitialize() {')
end = s.find('\n    void PerfAfterFrame(double frameMs) {', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.22 PerfInitialize block missing')

new_init = r'''    void PerfInitialize() {
        char path[MAX_PATH]{};
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        std::string file(path);
        const auto slash = file.find_last_of("\\/");
        if (slash != std::string::npos) file.resize(slash + 1);
        file += "GeoGebraForQuestPC.Performance.XR.csv";

        bool writeHeader = true;
        {
            std::ifstream existing(file, std::ios::binary | std::ios::ate);
            if (existing.is_open() && existing.tellg() > 0) writeHeader = false;
        }

        perfSessionId_ = std::to_string(static_cast<unsigned long long>(GetCurrentProcessId())) +
            "-" + std::to_string(static_cast<unsigned long long>(GetTickCount64()));

        perfCsv_.open(file, std::ios::out | std::ios::app);
        if (perfCsv_.is_open() && writeHeader) {
            perfCsv_ << "session_id,pid,elapsed_s,xr_fps,a_updates_fps,b_updates_fps,b_missed_frames,"
                     << "avg_frame_ms,max_frame_ms,avg_refresh_ms,max_refresh_ms,"
                     << "avg_a_update_ms,max_a_update_ms,avg_b_read_ms,max_b_read_ms,"
                     << "avg_b_upload_ms,max_b_upload_ms,avg_wait_frame_ms,max_wait_frame_ms,"
                     << "avg_acquire_ms,max_acquire_ms,avg_render_eyes_ms,max_render_eyes_ms,"
                     << "avg_end_frame_ms,max_end_frame_ms,"
                     << "predicted_display_ms,should_render,session_state,"
                     << "swapchain_w,swapchain_h,a_active,b_active,b_eye_w,b_eye_h,b_bytes,"
                     << "gpu_sequence,sbs_sequence" << std::endl;
        }
        if (perfCsv_.is_open()) perfCsv_.flush();
        std::cout << "v0.13.22 XR telemetry session=" << perfSessionId_
                  << " append=" << (writeHeader ? "new-file" : "existing-file") << std::endl;
        perfStarted_ = std::chrono::steady_clock::now();
        perfWindowStarted_ = perfStarted_;
    }
'''
s = s[:start] + new_init + s[end:]

row_marker = '''        perfCsv_ << std::fixed << std::setprecision(3)
                 << elapsed << ','
'''
req(s, row_marker, 'v0.13.22 XR row prefix marker missing')
s = s.replace(row_marker, '''        perfCsv_ << std::fixed << std::setprecision(3)
                 << perfSessionId_ << ','
                 << GetCurrentProcessId() << ','
                 << elapsed << ','
''', 1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Version/package labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.21-performance-telemetry', '0.13.22-pipeline-latency-telemetry')
    s = s.replace('v0.13.21', 'v0.13.22')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.22</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.22.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.22.0</AssemblyVersion>', s, count=1)
    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.21-performance-telemetry-win-x64',
            'GeoGebraForQuest-PC-v0.13.22-pipeline-latency-telemetry-win-x64')
        s = s.replace(r'0\.13\.21-performance-telemetry', r'0\.13\.22-pipeline-latency-telemetry')
        s = s.replace(r'v0\.13\.21', r'v0\.13\.22')
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.22 pipeline latency telemetry patch applied')
