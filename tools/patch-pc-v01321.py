from pathlib import Path
import re


def req(text, needle, label):
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# 1) JS telemetry: capture/encode cadence, busy skips, dimensions, payload size.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

marker = '  var identicalWarningSent = false;\n'
req(s, marker, 'v0.13.21 JS telemetry insertion marker missing')
s = s.replace(marker, marker + r'''

  // v0.13.21 performance telemetry. Aggregated in RAM and emitted once/second
  // so diagnostics do not perturb the capture path materially.
  var perfWindowStartedAt = performance.now();
  var perfEncodeStarted = 0;
  var perfEncodeCompleted = 0;
  var perfEncodeFailed = 0;
  var perfBusySkips = 0;
  var perfEncodeMsSum = 0;
  var perfEncodeMsMax = 0;
  var perfPayloadCharsSum = 0;
  var perfPayloadCharsMax = 0;

  function emitPerformanceSample() {
    var now = performance.now();
    var elapsed = Math.max(1, now - perfWindowStartedAt);
    var completed = perfEncodeCompleted;
    var sample = {
      kind: 'js-stereo',
      elapsedMs: elapsed,
      targetIntervalMs: CAPTURE_INTERVAL_MS,
      targetFps: 1000 / CAPTURE_INTERVAL_MS,
      encodeStarted: perfEncodeStarted,
      encodeCompleted: completed,
      encodeFailed: perfEncodeFailed,
      busySkips: perfBusySkips,
      actualEncodeFps: completed * 1000 / elapsed,
      avgEncodeMs: completed ? perfEncodeMsSum / completed : 0,
      maxEncodeMs: perfEncodeMsMax,
      avgPayloadChars: completed ? perfPayloadCharsSum / completed : 0,
      maxPayloadChars: perfPayloadCharsMax,
      leftWidth: leftCaptureCanvas.width || 0,
      leftHeight: leftCaptureCanvas.height || 0,
      rightWidth: rightCaptureCanvas.width || 0,
      rightHeight: rightCaptureCanvas.height || 0,
      encodingInFlight: !!encodingInFlight,
      pendingStereoSerial: pendingStereoSerial == null ? -1 : pendingStereoSerial,
      pendingAgeMs: pendingStereoRequestedAt ? Math.max(0, now - pendingStereoRequestedAt) : 0
    };
    bridge('performanceSample', JSON.stringify(sample));
    perfWindowStartedAt = now;
    perfEncodeStarted = 0;
    perfEncodeCompleted = 0;
    perfEncodeFailed = 0;
    perfBusySkips = 0;
    perfEncodeMsSum = 0;
    perfEncodeMsMax = 0;
    perfPayloadCharsSum = 0;
    perfPayloadCharsMax = 0;
  }
  setInterval(emitPerformanceSample, 1000);
''', 1)

# Count common busy-gate patterns if present.
s = s.replace('if (encodingInFlight) return;', 'if (encodingInFlight) { perfBusySkips++; return; }')
s = s.replace('if (encodingInFlight) {\n      return;\n    }', 'if (encodingInFlight) {\n      perfBusySkips++;\n      return;\n    }')

start_marker = '''      encodingInFlight = true;\n      pendingStereoSerial = null;\n      pendingStereoRequestedAt = 0;\n\n      Promise.all(['''
req(s, start_marker, 'v0.13.21 encode start marker missing')
s = s.replace(start_marker, '''      encodingInFlight = true;\n      var perfEncodePairStartedAt = performance.now();\n      perfEncodeStarted++;\n      pendingStereoSerial = null;\n      pendingStereoRequestedAt = 0;\n\n      Promise.all([''', 1)

then_marker = '''      ]).then(function (urls) {\n        var leftDataUrl = urls[0];\n        var rightDataUrl = urls[1];'''
req(s, then_marker, 'v0.13.21 encode completion marker missing')
s = s.replace(then_marker, '''      ]).then(function (urls) {\n        var leftDataUrl = urls[0];\n        var rightDataUrl = urls[1];\n        var perfEncodeMs = Math.max(0, performance.now() - perfEncodePairStartedAt);\n        var perfPayloadChars = (leftDataUrl ? leftDataUrl.length : 0) +\n          (rightDataUrl ? rightDataUrl.length : 0);\n        perfEncodeCompleted++;\n        perfEncodeMsSum += perfEncodeMs;\n        perfEncodeMsMax = Math.max(perfEncodeMsMax, perfEncodeMs);\n        perfPayloadCharsSum += perfPayloadChars;\n        perfPayloadCharsMax = Math.max(perfPayloadCharsMax, perfPayloadChars);''', 1)

# Count the first Promise catch following the stereo encode block.
pos = s.find('Promise.all([')
if pos >= 0:
    catch_pos = s.find('.catch(function (error) {', pos)
    if catch_pos >= 0:
        insert = catch_pos + len('.catch(function (error) {')
        s = s[:insert] + '\n        perfEncodeFailed++;' + s[insert:]

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) C# bridge + host telemetry hooks.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

field_marker = '    private readonly XrCompanionManager _xrCompanion = new();\n'
req(s, field_marker, 'v0.13.21 host telemetry field marker missing')
s = s.replace(field_marker, field_marker + '    private readonly HostPerformanceTelemetry _performanceTelemetry = new();\n', 1)

bridge_marker = '''                updateStereoEyes: function (left, right) {\n                  post({ type: 'stereoEyes', left: String(left || ''), right: String(right || '') });\n                },'''
req(s, bridge_marker, 'v0.13.21 bridge marker missing')
s = s.replace(bridge_marker, bridge_marker + '''\n                performanceSample: function (json) {\n                  post({ type: 'performanceSample', payload: String(json || '') });\n                },''', 1)

switch_marker = '''                case "runtimeError":\n                    if (root.TryGetProperty("message", out var message))'''
req(s, switch_marker, 'v0.13.21 message switch marker missing')
s = s.replace(switch_marker, '''                case "performanceSample":\n                    if (root.TryGetProperty("payload", out var perfPayload))\n                        _performanceTelemetry.RecordJsSample(perfPayload.GetString() ?? "null");\n                    break;\n                case "runtimeError":\n                    if (root.TryGetProperty("message", out var message))''', 1)

shutdown_marker = '        _sharedStereoFrames.Dispose();\n'
req(s, shutdown_marker, 'v0.13.21 shutdown marker missing')
s = s.replace(shutdown_marker, shutdown_marker + '        _performanceTelemetry.Dispose();\n', 1)
p.write_text(s, encoding='utf-8')


p = Path('pc/MainFormV11.InputStereo.cs')
s = p.read_text(encoding='utf-8')

queue_marker = '        lock (_pendingFrameLock) _pendingFrames = (left, right);\n'
req(s, queue_marker, 'v0.13.21 queue marker missing')
s = s.replace(queue_marker, '''        bool replaced;\n        lock (_pendingFrameLock)\n        {\n            replaced = _pendingFrames is not null;\n            _pendingFrames = (left, right);\n        }\n        _performanceTelemetry.RecordReceived(left.Length, right.Length, replaced);\n''', 1)

parallel_marker = '''                    Parallel.Invoke(\n                        () => left = DecodeDataUrl(pair.Value.Left),\n                        () => right = DecodeDataUrl(pair.Value.Right));'''
req(s, parallel_marker, 'v0.13.21 decode timing marker missing')
s = s.replace(parallel_marker, '''                    var decodeWatch = System.Diagnostics.Stopwatch.StartNew();\n                    Parallel.Invoke(\n                        () => left = DecodeDataUrl(pair.Value.Left),\n                        () => right = DecodeDataUrl(pair.Value.Right));\n                    decodeWatch.Stop();''', 1)

valid_marker = '''                    if (left is null || right is null)\n                        throw new InvalidDataException("Stereo göz karelerinden biri decode edilemedi.");'''
req(s, valid_marker, 'v0.13.21 decoded marker missing')
s = s.replace(valid_marker, valid_marker + '''\n\n                    _performanceTelemetry.RecordDecoded(\n                        decodeWatch.Elapsed.TotalMilliseconds, left.Width, left.Height);''', 1)

# Wrap whichever WriteFrames signature prior patches produced.
m = re.search(r'(?P<indent>\s+)_sharedStereoFrames\.WriteFrames\((?P<args>.*?)\);', s, re.S)
if not m:
    raise SystemExit('v0.13.21 publish timing marker missing')
indent = m.group('indent')
args = m.group('args')
replacement = (indent + 'var publishWatch = System.Diagnostics.Stopwatch.StartNew();' + indent +
               '_sharedStereoFrames.WriteFrames(' + args + ');' + indent +
               'publishWatch.Stop();' + indent +
               '_performanceTelemetry.RecordPublished(publishWatch.Elapsed.TotalMilliseconds);')
s = s[:m.start()] + replacement + s[m.end():]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) XR telemetry: frame cadence, source refresh cost, A/B update cadence,
#    sequence gaps, B bytes/dimensions, swapchain size, predicted display period.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

init_marker = '        baseTexture_.Initialize(device_.Get());\n'
req(s, init_marker, 'v0.13.21 XR init marker missing')
s = s.replace(init_marker, init_marker + '        PerfInitialize();\n', 1)

member_marker = '''    std::array<XrView, 2> views_{{\n        {XR_TYPE_VIEW},\n        {XR_TYPE_VIEW}\n    }};\n'''
req(s, member_marker, 'v0.13.21 XR member marker missing')
telemetry_members = r'''

    std::ofstream perfCsv_;
    std::chrono::steady_clock::time_point perfStarted_{};
    std::chrono::steady_clock::time_point perfWindowStarted_{};
    std::uint64_t perfFrames_{};
    std::uint64_t perfAUpdates_{};
    std::uint64_t perfBUpdates_{};
    std::uint64_t perfBMissed_{};
    double perfFrameMsSum_{};
    double perfFrameMsMax_{};
    double perfRefreshMsSum_{};
    double perfRefreshMsMax_{};
    double perfPredictedDisplayMs_{};
    bool perfShouldRender_{};

    static double PerfMs(std::chrono::steady_clock::time_point a,
                         std::chrono::steady_clock::time_point b) {
        return std::chrono::duration<double, std::milli>(b - a).count();
    }

    void PerfInitialize() {
        char path[MAX_PATH]{};
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        std::string file(path);
        const auto slash = file.find_last_of("\\/");
        if (slash != std::string::npos) file.resize(slash + 1);
        file += "GeoGebraForQuestPC.Performance.XR.csv";
        perfCsv_.open(file, std::ios::out | std::ios::trunc);
        if (perfCsv_.is_open()) {
            perfCsv_ << "elapsed_s,xr_fps,a_updates_fps,b_updates_fps,b_missed_frames,"
                     << "avg_frame_ms,max_frame_ms,avg_refresh_ms,max_refresh_ms,"
                     << "predicted_display_ms,should_render,session_state,"
                     << "swapchain_w,swapchain_h,a_active,b_active,b_eye_w,b_eye_h,b_bytes,"
                     << "gpu_sequence,sbs_sequence" << std::endl;
        }
        perfStarted_ = std::chrono::steady_clock::now();
        perfWindowStarted_ = perfStarted_;
    }

    void PerfAfterFrame(double frameMs) {
        perfFrames_++;
        perfFrameMsSum_ += frameMs;
        perfFrameMsMax_ = std::max(perfFrameMsMax_, frameMs);
        const auto now = std::chrono::steady_clock::now();
        const double windowMs = PerfMs(perfWindowStarted_, now);
        if (windowMs < 1000.0 || !perfCsv_.is_open()) return;

        const double seconds = std::max(0.001, windowMs / 1000.0);
        const double elapsed = PerfMs(perfStarted_, now) / 1000.0;
        const double avgFrame = perfFrames_ ? perfFrameMsSum_ / perfFrames_ : 0.0;
        const double avgRefresh = perfFrames_ ? perfRefreshMsSum_ / perfFrames_ : 0.0;

        perfCsv_ << std::fixed << std::setprecision(3)
                 << elapsed << ','
                 << perfFrames_ / seconds << ','
                 << perfAUpdates_ / seconds << ','
                 << perfBUpdates_ / seconds << ','
                 << perfBMissed_ << ','
                 << avgFrame << ',' << perfFrameMsMax_ << ','
                 << avgRefresh << ',' << perfRefreshMsMax_ << ','
                 << perfPredictedDisplayMs_ << ','
                 << (perfShouldRender_ ? 1 : 0) << ','
                 << SessionStateName(sessionState_) << ','
                 << projectionSwapchain_.Width() << ','
                 << projectionSwapchain_.Height() << ','
                 << (gpuFrame_.active ? 1 : 0) << ','
                 << (sbsFrame_.active ? 1 : 0) << ','
                 << sbsFrame_.eyeWidth << ','
                 << sbsFrame_.eyeHeight << ','
                 << sbsFrame_.sbs.size() << ','
                 << gpuSequence_ << ','
                 << sbsSequence_ << std::endl;
        perfCsv_.flush();

        perfWindowStarted_ = now;
        perfFrames_ = perfAUpdates_ = perfBUpdates_ = perfBMissed_ = 0;
        perfFrameMsSum_ = perfFrameMsMax_ = 0.0;
        perfRefreshMsSum_ = perfRefreshMsMax_ = 0.0;
    }
'''
s = s.replace(member_marker, member_marker + telemetry_members, 1)

run_marker = '            RenderFrame();\n'
req(s, run_marker, 'v0.13.21 XR run marker missing')
s = s.replace(run_marker, '''            const auto perfFrameStart = std::chrono::steady_clock::now();\n            RenderFrame();\n            const auto perfFrameEnd = std::chrono::steady_clock::now();\n            PerfAfterFrame(PerfMs(perfFrameStart, perfFrameEnd));\n''', 1)

refresh_sig = '    void RefreshSources() {\n'
req(s, refresh_sig, 'v0.13.21 RefreshSources signature missing')
s = s.replace(refresh_sig, '''    void RefreshSources() {\n        const auto perfRefreshStart = std::chrono::steady_clock::now();\n        const auto perfGpuBefore = gpuSequence_;\n        const auto perfSbsBefore = sbsSequence_;\n''', 1)

# Insert refresh accounting immediately before RenderFrame function.
refresh_end_marker = '\n    }\n\n    void RenderFrame() {'
pos = s.find(refresh_sig)
end = s.find(refresh_end_marker, pos)
if end < 0:
    raise SystemExit('v0.13.21 RefreshSources end marker missing')
accounting = r'''
        const auto perfRefreshEnd = std::chrono::steady_clock::now();
        const double perfRefreshMs = PerfMs(perfRefreshStart, perfRefreshEnd);
        perfRefreshMsSum_ += perfRefreshMs;
        perfRefreshMsMax_ = std::max(perfRefreshMsMax_, perfRefreshMs);
        if (gpuSequence_ != perfGpuBefore) perfAUpdates_++;
        if (sbsSequence_ != perfSbsBefore) {
            perfBUpdates_++;
            if (perfSbsBefore > 0 && sbsSequence_ > perfSbsBefore + 2) {
                perfBMissed_ += static_cast<std::uint64_t>((sbsSequence_ - perfSbsBefore) / 2 - 1);
            }
        }
'''
s = s[:end] + accounting + s[end:]

wait_marker = '''        CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");\n'''
req(s, wait_marker, 'v0.13.21 xrWaitFrame marker missing')
s = s.replace(wait_marker, wait_marker + '''        perfPredictedDisplayMs_ = static_cast<double>(frameState.predictedDisplayPeriod) / 1000000.0;\n        perfShouldRender_ = frameState.shouldRender == XR_TRUE;\n''', 1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Version/package labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.20-60fps-test', '0.13.21-performance-telemetry')
    s = s.replace('v0.13.20', 'v0.13.21')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.21</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.21.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.21.0</AssemblyVersion>', s, count=1)
    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.20-60fps-test-win-x64',
            'GeoGebraForQuest-PC-v0.13.21-performance-telemetry-win-x64')
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.21 comprehensive performance telemetry patch applied')
