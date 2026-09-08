from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.25 stereo-path proof build.
# Keep v0.13.24 transport/visual behavior unchanged and instrument BOTH ends:
#   JS: verify Exp46 LEFT and RIGHT canvases are actually different before IPC.
#   XR: verify active SBS frames arrive, contain different halves, and are uploaded.
# No visible DOM overlay, no eye swapping, no artificial disparity.
# ---------------------------------------------------------------------------

# 1) JS: sampled left/right difference before the ArrayBuffer is posted.
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

vars_marker = '  var perfLastEyeWidth = 0;\n  var perfLastEyeHeight = 0;\n'
req(s, vars_marker, 'v0.13.25 JS perf vars marker missing')
s = s.replace(vars_marker, vars_marker + '''  var perfStereoDiffCount = 0;\n  var perfStereoDiffMeanSum = 0;\n  var perfStereoDiffMeanMax = 0;\n  var perfStereoDiffChangedPctSum = 0;\n  var perfStereoDiffChangedPctMax = 0;\n''', 1)

sample_marker = '''      eyeWidth: perfLastEyeWidth,\n      eyeHeight: perfLastEyeHeight\n'''
req(s, sample_marker, 'v0.13.25 JS telemetry sample marker missing')
s = s.replace(sample_marker, '''      eyeWidth: perfLastEyeWidth,\n      eyeHeight: perfLastEyeHeight,\n      avgStereoDiffMean: perfStereoDiffCount ? perfStereoDiffMeanSum / perfStereoDiffCount : 0,\n      maxStereoDiffMean: perfStereoDiffMeanMax,\n      avgStereoDiffChangedPct: perfStereoDiffCount ? perfStereoDiffChangedPctSum / perfStereoDiffCount : 0,\n      maxStereoDiffChangedPct: perfStereoDiffChangedPctMax\n''', 1)

reset_marker = '    perfAckTimeouts = 0;\n  }\n  setInterval(emitPerformanceSample, 1000);\n'
req(s, reset_marker, 'v0.13.25 JS perf reset marker missing')
s = s.replace(reset_marker, '''    perfAckTimeouts = 0;\n    perfStereoDiffCount = 0;\n    perfStereoDiffMeanSum = 0;\n    perfStereoDiffMeanMax = 0;\n    perfStereoDiffChangedPctSum = 0;\n    perfStereoDiffChangedPctMax = 0;\n  }\n  setInterval(emitPerformanceSample, 1000);\n''', 1)

capture_marker = '  function beginRawStereoCapture(serial, requestedAt) {\n'
req(s, capture_marker, 'v0.13.25 JS raw capture marker missing')
helper = r'''  function measureRawStereoDifference(bytes, eyeWidth, eyeHeight) {
    if (!bytes || eyeWidth < 2 || eyeHeight < 2) return { mean: 0, changedPct: 0 };
    var sbsWidth = eyeWidth * 2;
    var stepX = Math.max(1, Math.floor(eyeWidth / 40));
    var stepY = Math.max(1, Math.floor(eyeHeight / 30));
    var samples = 0;
    var changed = 0;
    var sum = 0;
    for (var y = Math.floor(stepY * 0.5); y < eyeHeight; y += stepY) {
      for (var x = Math.floor(stepX * 0.5); x < eyeWidth; x += stepX) {
        var li = (y * sbsWidth + x) * 4;
        var ri = (y * sbsWidth + eyeWidth + x) * 4;
        var d = Math.abs(bytes[li] - bytes[ri]) +
                Math.abs(bytes[li + 1] - bytes[ri + 1]) +
                Math.abs(bytes[li + 2] - bytes[ri + 2]);
        sum += d / 3;
        if (d >= 18) changed++;
        samples++;
      }
    }
    return {
      mean: samples ? sum / samples : 0,
      changedPct: samples ? changed * 100 / samples : 0
    };
  }

'''
s = s.replace(capture_marker, helper + capture_marker, 1)

image_marker = '''      if (!image || !image.data || image.data.byteLength !== expectedBytes) {\n        throw new Error('raw SBS byte length uyuşmuyor');\n      }\n\n      pendingStereoSerial = null;'''
req(s, image_marker, 'v0.13.25 JS image marker missing')
s = s.replace(image_marker, '''      if (!image || !image.data || image.data.byteLength !== expectedBytes) {\n        throw new Error('raw SBS byte length uyuşmuyor');\n      }\n\n      var stereoDiff = measureRawStereoDifference(image.data, eyeWidth, eyeHeight);\n      perfStereoDiffCount++;\n      perfStereoDiffMeanSum += stereoDiff.mean;\n      perfStereoDiffMeanMax = Math.max(perfStereoDiffMeanMax, stereoDiff.mean);\n      perfStereoDiffChangedPctSum += stereoDiff.changedPct;\n      perfStereoDiffChangedPctMax = Math.max(perfStereoDiffChangedPctMax, stereoDiff.changedPct);\n\n      pendingStereoSerial = null;''', 1)

# Durable runtime label only.
s = s.replace('// GeoGebraForQuest PC v0.12.3 XR-Behind Native runtime.',
              '// GeoGebraForQuest PC v0.13.25 stereo-path proof runtime.', 1)
p.write_text(s, encoding='utf-8')


# 2) XR: independently compare the two halves of the final SBS bytes.
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

namespace_marker = 'namespace {\n\nconstexpr XrViewConfigurationType kViewConfiguration =\n'
req(s, namespace_marker, 'v0.13.25 XR namespace marker missing')
diag_helper = r'''namespace {

struct StereoDifferenceStats {
    double meanAbs{};
    double changedPct{};
};

StereoDifferenceStats MeasureStereoDifference(const SbsSnapshot& frame) {
    StereoDifferenceStats stats{};
    if (!frame.active || frame.eyeWidth < 2 || frame.eyeHeight < 2 ||
        frame.sbsStride < frame.eyeWidth * 2 * 4 || frame.sbs.empty()) {
        return stats;
    }
    const int stepX = std::max(1, frame.eyeWidth / 40);
    const int stepY = std::max(1, frame.eyeHeight / 30);
    std::uint64_t samples = 0;
    std::uint64_t changed = 0;
    double sum = 0.0;
    for (int y = stepY / 2; y < frame.eyeHeight; y += stepY) {
        const auto* row = frame.sbs.data() + static_cast<std::size_t>(y) * frame.sbsStride;
        for (int x = stepX / 2; x < frame.eyeWidth; x += stepX) {
            const auto* l = row + static_cast<std::size_t>(x) * 4;
            const auto* r = row + static_cast<std::size_t>(frame.eyeWidth + x) * 4;
            const int d = std::abs(static_cast<int>(l[0]) - static_cast<int>(r[0])) +
                          std::abs(static_cast<int>(l[1]) - static_cast<int>(r[1])) +
                          std::abs(static_cast<int>(l[2]) - static_cast<int>(r[2]));
            sum += static_cast<double>(d) / 3.0;
            if (d >= 18) ++changed;
            ++samples;
        }
    }
    if (samples) {
        stats.meanAbs = sum / static_cast<double>(samples);
        stats.changedPct = static_cast<double>(changed) * 100.0 / static_cast<double>(samples);
    }
    return stats;
}

constexpr XrViewConfigurationType kViewConfiguration =
'''
s = s.replace(namespace_marker, diag_helper, 1)

fields_marker = '    SbsSnapshot sbsFrame_{};\n\n    XrInputWriter inputWriter_;\n'
req(s, fields_marker, 'v0.13.25 XR fields marker missing')
s = s.replace(fields_marker, '''    SbsSnapshot sbsFrame_{};\n    std::uint64_t stereoDiagFrames_{};\n    std::chrono::steady_clock::time_point stereoDiagHeartbeat_{std::chrono::steady_clock::now()};\n\n    XrInputWriter inputWriter_;\n''', 1)

# Instrument after the existing B upload timing accounting. This is intentionally
# sampled/logged only every 30 B updates so it cannot meaningfully affect cadence.
upload_counter = '                perfBUploadCalls_++;\n'
req(s, upload_counter, 'v0.13.25 XR B upload timing marker missing')
s = s.replace(upload_counter, upload_counter + '''                ++stereoDiagFrames_;\n                if (stereoDiagFrames_ == 1 || (stereoDiagFrames_ % 30) == 0) {\n                    const auto diff = MeasureStereoDifference(sbsFrame_);\n                    std::ostringstream bdiag;\n                    bdiag << std::fixed << std::setprecision(3)\n                          << "B SBS consumed seq=" << sbsSequence_\n                          << " frame=" << sbsFrame_.frameNumber\n                          << " eye=" << sbsFrame_.eyeWidth << "x" << sbsFrame_.eyeHeight\n                          << " fmt=" << sbsFrame_.pixelFormat\n                          << " bytes=" << sbsFrame_.sbs.size()\n                          << " diffMean=" << diff.meanAbs\n                          << " diffChangedPct=" << diff.changedPct;\n                    Log(bdiag.str());\n                }\n''', 1)

refresh_marker = '        RefreshSources();\n\n        std::array<XrCompositionLayerProjectionView, 2> projectionViews'
req(s, refresh_marker, 'v0.13.25 XR RefreshSources marker missing')
s = s.replace(refresh_marker, '''        RefreshSources();\n\n        const auto stereoDiagNow = std::chrono::steady_clock::now();\n        if (std::chrono::duration_cast<std::chrono::seconds>(\n                stereoDiagNow - stereoDiagHeartbeat_).count() >= 5) {\n            stereoDiagHeartbeat_ = stereoDiagNow;\n            std::ostringstream heartbeat;\n            heartbeat << "B heartbeat active=" << (sbsFrame_.active ? 1 : 0)\n                      << " textureValid=" << (sbsTexture_.Valid() ? 1 : 0)\n                      << " seq=" << sbsSequence_\n                      << " eye=" << sbsFrame_.eyeWidth << "x" << sbsFrame_.eyeHeight\n                      << " fmt=" << sbsFrame_.pixelFormat\n                      << " bytes=" << sbsFrame_.sbs.size();\n            Log(heartbeat.str());\n        }\n\n        std::array<XrCompositionLayerProjectionView, 2> projectionViews''', 1)

# Fix stale XR log labels while here; behavior is unchanged.
s = s.replace('GeoGebraForQuest PC v0.11 initialized:', 'GeoGebraForQuest PC v0.13.25 initialized:')
s = s.replace('GeoGebraForQuest PC v0.11 XR starting, host pid=', 'GeoGebraForQuest PC v0.13.25 XR starting, host pid=')
s = s.replace('L"GeoGebraForQuest PC v0.11"', 'L"GeoGebraForQuest PC v0.13.25"')
p.write_text(s, encoding='utf-8')


# 3) Package/version/cache labels.
for name in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(name)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.24-raw-arraybuffer', '0.13.25-stereo-proof')
    s = s.replace('v0.13.24', 'v0.13.25')
    if name.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.25</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.25.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.25.0</AssemblyVersion>', s, count=1)
    if name.endswith('build.ps1'):
        s = s.replace('GeoGebraForQuest-PC-v0.13.24-raw-arraybuffer-win-x64',
                      'GeoGebraForQuest-PC-v0.13.25-stereo-proof-win-x64')
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.25 stereo-path proof diagnostics applied')
