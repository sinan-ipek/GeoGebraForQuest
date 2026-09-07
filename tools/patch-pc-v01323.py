from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


def sub1(pattern: str, repl: str, text: str, label: str, flags=0) -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f"{label}: replacements={n}")
    return out


# ---------------------------------------------------------------------------
# v0.13.23: eliminate B JPEG/Base64/Bitmap transport without touching XR.
#
# B capture becomes:
#   Exp46 stereo renderer -> temporary LEFT overlay -> CEF shared D3D11 texture
#   -> GPU [L|R] SBS texture -> one staging readback -> existing raw SBS MMF -> XR.
#
# The current v0.13.22 geometry/menu/modal policy is kept. A stays on its proven
# direct CEF GPU -> shared D3D11 -> OpenXR path. XR's SBS consumer is unchanged.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1) JavaScript: preserve geometry/overlay detection but replace JPEG capture
#    with a two-phase CEF GPU compositor handshake.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

# v0.13.20 had intentionally raised this to 16 ms for the JPEG experiment.
if '  var CAPTURE_INTERVAL_MS = 16;' in s:
    s = s.replace('  var CAPTURE_INTERVAL_MS = 16;', '  var CAPTURE_INTERVAL_MS = 33;', 1)
elif '  var CAPTURE_INTERVAL_MS = 33;' not in s:
    raise SystemExit('v0.13.23 JS capture interval marker missing')
s = s.replace('  // v0.13.20: controlled ~60 fps stereo-B capture cadence test.\n',
              '  // v0.13.23: raw two-phase B transport; starts are capped near 30 Hz.\n', 1)

state_start = s.find('  var pendingStereoSerial = null;')
bridge_start = s.find('  function bridge(name, value) {', state_start)
if state_start < 0 or bridge_start < 0:
    raise SystemExit('v0.13.23 JS state/bridge markers missing')

new_state = r'''  var transportState = 'idle';
  var transportBaseline = -1;
  var transportSerial = -1;
  var transportStartedAt = 0;
  var phasePostedAt = 0;
  var nextStereoRequestAt = 0;
  var lastAckAt = performance.now();
  var overlay = null;
  var overlayContext = null;

  var PHASE_TIMEOUT_MS = 350;
  var SERIAL_TIMEOUT_MS = 250;

  // v0.13.23 raw/GPU transport telemetry. No JPEG payload counters remain.
  var perfWindowStartedAt = performance.now();
  var perfRequestCount = 0;
  var perfRequestFailed = 0;
  var perfReadyCount = 0;
  var perfRequestToReadyMsSum = 0;
  var perfRequestToReadyMsMax = 0;
  var perfRequestIntervalCount = 0;
  var perfRequestIntervalMsSum = 0;
  var perfRequestIntervalMsMax = 0;
  var perfLastRequestAt = 0;
  var perfLeftPhaseCount = 0;
  var perfRightPhaseCount = 0;
  var perfLeftAckCount = 0;
  var perfRightAckCount = 0;
  var perfLeftAckMsSum = 0;
  var perfLeftAckMsMax = 0;
  var perfRightAckMsSum = 0;
  var perfRightAckMsMax = 0;
  var perfCycleCount = 0;
  var perfCycleMsSum = 0;
  var perfCycleMsMax = 0;
  var perfSerialTimeouts = 0;
  var perfPhaseTimeouts = 0;

  function emitPerformanceSample() {
    var now = performance.now();
    var elapsed = Math.max(1, now - perfWindowStartedAt);
    var sample = {
      kind: 'js-stereo-raw',
      elapsedMs: elapsed,
      targetIntervalMs: CAPTURE_INTERVAL_MS,
      targetFps: 1000 / CAPTURE_INTERVAL_MS,
      requestCount: perfRequestCount,
      requestFailed: perfRequestFailed,
      actualRequestFps: perfRequestCount * 1000 / elapsed,
      readyCount: perfReadyCount,
      actualReadyFps: perfReadyCount * 1000 / elapsed,
      avgRequestToReadyMs: perfReadyCount ? perfRequestToReadyMsSum / perfReadyCount : 0,
      maxRequestToReadyMs: perfRequestToReadyMsMax,
      avgRequestIntervalMs: perfRequestIntervalCount ? perfRequestIntervalMsSum / perfRequestIntervalCount : 0,
      maxRequestIntervalMs: perfRequestIntervalMsMax,
      leftPhaseCount: perfLeftPhaseCount,
      rightPhaseCount: perfRightPhaseCount,
      leftAckCount: perfLeftAckCount,
      rightAckCount: perfRightAckCount,
      avgLeftAckMs: perfLeftAckCount ? perfLeftAckMsSum / perfLeftAckCount : 0,
      maxLeftAckMs: perfLeftAckMsMax,
      avgRightAckMs: perfRightAckCount ? perfRightAckMsSum / perfRightAckCount : 0,
      maxRightAckMs: perfRightAckMsMax,
      cycleCount: perfCycleCount,
      actualCycleFps: perfCycleCount * 1000 / elapsed,
      avgCycleMs: perfCycleCount ? perfCycleMsSum / perfCycleCount : 0,
      maxCycleMs: perfCycleMsMax,
      serialTimeouts: perfSerialTimeouts,
      phaseTimeouts: perfPhaseTimeouts,
      transportState: transportState,
      pendingStereoSerial: transportSerial,
      pendingAgeMs: transportStartedAt ? Math.max(0, now - transportStartedAt) : 0
    };
    bridge('performanceSample', JSON.stringify(sample));

    perfWindowStartedAt = now;
    perfRequestCount = 0;
    perfRequestFailed = 0;
    perfReadyCount = 0;
    perfRequestToReadyMsSum = 0;
    perfRequestToReadyMsMax = 0;
    perfRequestIntervalCount = 0;
    perfRequestIntervalMsSum = 0;
    perfRequestIntervalMsMax = 0;
    perfLeftPhaseCount = 0;
    perfRightPhaseCount = 0;
    perfLeftAckCount = 0;
    perfRightAckCount = 0;
    perfLeftAckMsSum = 0;
    perfLeftAckMsMax = 0;
    perfRightAckMsSum = 0;
    perfRightAckMsMax = 0;
    perfCycleCount = 0;
    perfCycleMsSum = 0;
    perfCycleMsMax = 0;
    perfSerialTimeouts = 0;
    perfPhaseTimeouts = 0;
  }
  setInterval(emitPerformanceSample, 1000);

'''
s = s[:state_start] + new_state + s[bridge_start:]

# Replace the old stereo-eye DataURL bridge with a direct host message helper.
s = sub1(
    r"  function bridgeStereoEyes\(leftDataUrl, rightDataUrl\) \{.*?\n  \}\n\n",
    r'''  function postHost(message) {
    try {
      if (window.CefSharp && typeof window.CefSharp.PostMessage === 'function') {
        window.CefSharp.PostMessage(message);
        return;
      }
      if (window.cefSharp && typeof window.cefSharp.postMessage === 'function') {
        window.cefSharp.postMessage(message);
      }
    } catch (_) {}
  }

''',
    s,
    'v0.13.23 JS bridgeStereoEyes replacement',
    re.S)

# reportInactive still calls resetStereoRequestState; make that reset the new transport.
s = sub1(
    r"  function resetStereoRequestState\(\) \{.*?\n  \}\n",
    r'''  function resetStereoRequestState() {
    resetTransport(CAPTURE_INTERVAL_MS, true);
  }
''',
    s,
    'v0.13.23 JS resetStereoRequestState replacement',
    re.S)

capture_start = s.find('  function getRendererEyeCanvases() {')
observer_start = s.find('  if (window.ResizeObserver) {', capture_start)
if capture_start < 0 or observer_start < 0:
    raise SystemExit('v0.13.23 JS capture/observer markers missing')

new_transport = r'''  function getRendererEyeCanvases() {
    var left = document.getElementById('ggq-renderer-left-eye');
    var right = document.getElementById('ggq-renderer-right-eye');
    if (!left || !right) return null;
    if (left.width < 2 || left.height < 2 || right.width < 2 || right.height < 2) {
      return null;
    }
    return { left: left, right: right };
  }

  function ensureOverlay() {
    if (overlay && overlay.isConnected && overlayContext) return true;

    overlay = document.createElement('canvas');
    overlay.id = 'ggq-pc-raw-left-eye-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.position = 'fixed';
    overlay.style.margin = '0';
    overlay.style.padding = '0';
    overlay.style.border = '0';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '2147483646';
    overlay.style.display = 'none';
    overlay.style.background = 'transparent';
    overlay.style.transform = 'translateZ(0)';

    overlayContext = overlay.getContext('2d', {
      alpha: true,
      desynchronized: true
    });
    if (!overlayContext) {
      overlay = null;
      return false;
    }
    overlayContext.imageSmoothingEnabled = true;
    overlayContext.imageSmoothingQuality = 'high';
    (document.body || document.documentElement).appendChild(overlay);
    return true;
  }

  function hideOverlay() {
    if (overlay) overlay.style.display = 'none';
  }

  function showLeftOverlay() {
    var geometry = geometryState;
    var eyes = getRendererEyeCanvases();
    if (!geometry || !geometry.rect || !eyes || !ensureOverlay()) return false;

    var sourceWidth = Math.min(eyes.left.width, eyes.right.width);
    var sourceHeight = Math.min(eyes.left.height, eyes.right.height);
    if (sourceWidth < 2 || sourceHeight < 2) return false;

    if (overlay.width !== sourceWidth) overlay.width = sourceWidth;
    if (overlay.height !== sourceHeight) overlay.height = sourceHeight;

    overlay.style.left = geometry.rect.left + 'px';
    overlay.style.top = geometry.rect.top + 'px';
    overlay.style.width = geometry.rect.width + 'px';
    overlay.style.height = geometry.rect.height + 'px';

    overlayContext.imageSmoothingEnabled = true;
    overlayContext.imageSmoothingQuality = 'high';
    overlayContext.clearRect(0, 0, sourceWidth, sourceHeight);
    overlayContext.drawImage(
      eyes.left,
      0, 0, sourceWidth, sourceHeight,
      0, 0, sourceWidth, sourceHeight
    );
    overlay.style.display = 'block';
    return true;
  }

  function postPhase(eye, serial) {
    phasePostedAt = performance.now();
    if (eye === 'left') perfLeftPhaseCount++; else perfRightPhaseCount++;
    postHost({ type: 'stereoGpuPhase', eye: eye, serial: serial });
  }

  function resetTransport(delayMs, notifyHost) {
    var wasActive = transportState !== 'idle';
    hideOverlay();
    transportState = 'idle';
    transportBaseline = -1;
    transportSerial = -1;
    transportStartedAt = 0;
    phasePostedAt = 0;
    nextStereoRequestAt = performance.now() +
      (typeof delayMs === 'number' ? delayMs : CAPTURE_INTERVAL_MS);
    if (wasActive && notifyHost) {
      postHost({ type: 'stereoGpuCancel' });
    }
  }

  function readStereoFrameSerial() {
    try {
      if (typeof window.ggqGetStereoFrameSerial !== 'function') return -1;
      var serial = Number(window.ggqGetStereoFrameSerial());
      return isFinite(serial) ? serial : -1;
    } catch (_) {
      return -1;
    }
  }

  function requestStereoPair(now) {
    try {
      if (typeof window.ggqRequestStereoFrame !== 'function') {
        perfRequestFailed++;
        return false;
      }
      if (perfLastRequestAt > 0) {
        var interval = Math.max(0, now - perfLastRequestAt);
        perfRequestIntervalCount++;
        perfRequestIntervalMsSum += interval;
        perfRequestIntervalMsMax = Math.max(perfRequestIntervalMsMax, interval);
      }
      perfLastRequestAt = now;

      var baseline = Number(window.ggqRequestStereoFrame());
      perfRequestCount++;
      if (!isFinite(baseline) || baseline < 0) {
        perfRequestFailed++;
        return false;
      }

      transportBaseline = baseline;
      transportSerial = -1;
      transportStartedAt = now;
      transportState = 'wait-serial';
      return true;
    } catch (_) {
      perfRequestFailed++;
      return false;
    }
  }

  window.ggqPcGpuTransport = {
    ack: function (eye, serial) {
      serial = Number(serial);
      if (!isFinite(serial) || serial !== transportSerial) return false;

      var now = performance.now();
      var ackMs = phasePostedAt ? Math.max(0, now - phasePostedAt) : 0;
      lastAckAt = now;

      if (eye === 'left' && transportState === 'left-wait-ack') {
        perfLeftAckCount++;
        perfLeftAckMsSum += ackMs;
        perfLeftAckMsMax = Math.max(perfLeftAckMsMax, ackMs);
        hideOverlay();
        transportState = 'right-wait-ack';
        requestAnimationFrame(function () {
          if (transportState === 'right-wait-ack') postPhase('right', transportSerial);
        });
        return true;
      }

      if (eye === 'right' && transportState === 'right-wait-ack') {
        perfRightAckCount++;
        perfRightAckMsSum += ackMs;
        perfRightAckMsMax = Math.max(perfRightAckMsMax, ackMs);
        var cycleStartedAt = transportStartedAt;
        var cycleMs = cycleStartedAt ? Math.max(0, now - cycleStartedAt) : 0;
        perfCycleCount++;
        perfCycleMsSum += cycleMs;
        perfCycleMsMax = Math.max(perfCycleMsMax, cycleMs);

        transportState = 'idle';
        transportBaseline = -1;
        transportSerial = -1;
        transportStartedAt = 0;
        phasePostedAt = 0;
        nextStereoRequestAt = Math.max(now + 1, cycleStartedAt + CAPTURE_INTERVAL_MS);
        return true;
      }
      return false;
    },

    cancel: function () {
      resetTransport(CAPTURE_INTERVAL_MS, false);
      return true;
    }
  };

  function transportLoop(now) {
    if (!geometryState) {
      if (transportState !== 'idle') resetTransport(CAPTURE_INTERVAL_MS, true);
      nextStereoRequestAt = Math.max(nextStereoRequestAt, now + CAPTURE_INTERVAL_MS);
      requestAnimationFrame(transportLoop);
      return;
    }

    if ((transportState === 'left-wait-ack' || transportState === 'right-wait-ack') &&
        now - lastAckAt > PHASE_TIMEOUT_MS) {
      perfPhaseTimeouts++;
      resetTransport(CAPTURE_INTERVAL_MS, true);
    }

    if (transportState === 'wait-serial') {
      var serial = readStereoFrameSerial();
      if (serial > transportBaseline) {
        var readyMs = Math.max(0, now - transportStartedAt);
        perfReadyCount++;
        perfRequestToReadyMsSum += readyMs;
        perfRequestToReadyMsMax = Math.max(perfRequestToReadyMsMax, readyMs);
        transportSerial = serial;
        if (showLeftOverlay()) {
          transportState = 'left-wait-ack';
          lastAckAt = now;
          requestAnimationFrame(function () {
            if (transportState === 'left-wait-ack') postPhase('left', transportSerial);
          });
        } else {
          resetTransport(CAPTURE_INTERVAL_MS, true);
        }
      } else if (now - transportStartedAt > SERIAL_TIMEOUT_MS) {
        perfSerialTimeouts++;
        resetTransport(CAPTURE_INTERVAL_MS, true);
      }
    } else if (transportState === 'idle' && now >= nextStereoRequestAt) {
      if (!requestStereoPair(now)) nextStereoRequestAt = now + CAPTURE_INTERVAL_MS;
    }

    requestAnimationFrame(transportLoop);
  }

'''
s = s[:capture_start] + new_transport + s[observer_start:]
s = s.replace('  requestAnimationFrame(captureLoop);', '  requestAnimationFrame(transportLoop);', 1)

s = s.replace(
    '// GeoGebraForQuest PC v0.12.3 XR-Behind Native runtime.',
    '// GeoGebraForQuest PC v0.13.23 no-JPEG raw SBS runtime.', 1)
if 'canvasToDataUrlAsync' in s or "'image/jpeg'" in s or 'bridgeStereoEyes' in s:
    raise SystemExit('v0.13.23 JS still contains JPEG/DataURL transport')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Existing SBS MMF writer: add a direct tightly-packed BGRA byte path.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')
marker = '    public void SetInactive(Rectangle stereoPanelClientBounds, Size applicationClientSize)\n'
req(s, marker, 'v0.13.23 raw writer insertion marker missing')
raw_method = r'''    public void WriteRawSbs(
        byte[] sbsBgra,
        int eyeWidth,
        int eyeHeight,
        int sbsStride,
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        long frameNumber)
    {
        if (_disposed ||
            sbsBgra is null ||
            applicationClientSize.Width < 1 || applicationClientSize.Height < 1 ||
            stereoPanelClientBounds.Width < 2 || stereoPanelClientBounds.Height < 2 ||
            eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > MaxEyeWidth || eyeHeight > MaxEyeHeight)
        {
            return;
        }

        var tightStride = checked(eyeWidth * 2 * 4);
        if (sbsStride != tightStride) throw new ArgumentException("Raw SBS stride must be tightly packed.");
        var totalBytes = checked(tightStride * eyeHeight);
        if (sbsBgra.Length < totalBytes) throw new ArgumentException("Raw SBS buffer is too small.");

        lock (_sync)
        {
            var evenSequence = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, evenSequence - 1);
            _view.Write(16, 1);
            _view.Write(20, applicationClientSize.Width);
            _view.Write(24, applicationClientSize.Height);
            _view.Write(28, stereoPanelClientBounds.Left);
            _view.Write(32, stereoPanelClientBounds.Top);
            _view.Write(36, stereoPanelClientBounds.Width);
            _view.Write(40, stereoPanelClientBounds.Height);
            _view.Write(44, eyeWidth);
            _view.Write(48, eyeHeight);
            _view.Write(52, tightStride);
            _view.Write(56, unchecked((int)frameNumber));
            _view.Write(60, Environment.ProcessId);

            _view.WriteArray(SbsOffset, sbsBgra, 0, totalBytes);
            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s.replace(marker, raw_method + marker, 1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Host telemetry: retain legacy counters for compatibility, add raw GPU copy,
#    staging readback and MMF publish timings.
# ---------------------------------------------------------------------------
Path('pc/PerformanceTelemetry.cs').write_text(r'''using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace GeoGebraForQuest.PC;

internal sealed class HostPerformanceTelemetry : IDisposable
{
    private readonly object _sync = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly Process _process = Process.GetCurrentProcess();
    private readonly StreamWriter _host;
    private readonly StreamWriter _js;

    private long _lastWriteMs;
    private TimeSpan _lastCpu;
    private long _received;
    private long _replaced;
    private long _decoded;
    private long _published;
    private double _decodeMsSum;
    private double _decodeMsMax;
    private double _publishMsSum;
    private double _publishMsMax;
    private int _eyeWidth;
    private int _eyeHeight;
    private long _lastLeftChars;
    private long _lastRightChars;
    private long _rawFrames;
    private double _rawGpuCopyMsSum;
    private double _rawGpuCopyMsMax;
    private double _rawReadbackMsSum;
    private double _rawReadbackMsMax;
    private double _rawPublishMsSum;
    private double _rawPublishMsMax;
    private int _rawEyeWidth;
    private int _rawEyeHeight;
    private long _rawSbsBytes;
    private bool _disposed;

    public HostPerformanceTelemetry()
    {
        var hostPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.Host.csv");
        var jsPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.JS.jsonl");
        _host = new StreamWriter(new FileStream(hostPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite, 4096, FileOptions.SequentialScan), new UTF8Encoding(false));
        _js = new StreamWriter(new FileStream(jsPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite, 4096, FileOptions.SequentialScan), new UTF8Encoding(false));
        _host.WriteLine(
            "elapsed_s,utc,received_pairs,pending_replaced,decoded_pairs,published_pairs," +
            "avg_decode_ms,max_decode_ms,avg_publish_ms,max_publish_ms," +
            "eye_width,eye_height,left_dataurl_chars,right_dataurl_chars," +
            "raw_frames,avg_gpu_copy_ms,max_gpu_copy_ms,avg_readback_ms,max_readback_ms," +
            "avg_raw_publish_ms,max_raw_publish_ms,raw_eye_width,raw_eye_height,raw_sbs_bytes," +
            "working_set_mb,private_mb,gc_heap_mb,cpu_percent");
        _host.Flush();
        _lastCpu = _process.TotalProcessorTime;
    }

    public void RecordReceived(int leftChars, int rightChars, bool replaced)
    {
        lock (_sync) { _received++; if (replaced) _replaced++; _lastLeftChars = leftChars; _lastRightChars = rightChars; MaybeWriteLocked(); }
    }

    public void RecordDecoded(double ms, int width, int height)
    {
        lock (_sync) { _decoded++; _decodeMsSum += ms; _decodeMsMax = Math.Max(_decodeMsMax, ms); _eyeWidth = width; _eyeHeight = height; MaybeWriteLocked(); }
    }

    public void RecordPublished(double ms)
    {
        lock (_sync) { _published++; _publishMsSum += ms; _publishMsMax = Math.Max(_publishMsMax, ms); MaybeWriteLocked(); }
    }

    public void RecordRawFrame(double gpuCopyMs, double readbackMs, double publishMs, int eyeWidth, int eyeHeight, int sbsBytes)
    {
        lock (_sync)
        {
            _rawFrames++;
            _rawGpuCopyMsSum += gpuCopyMs; _rawGpuCopyMsMax = Math.Max(_rawGpuCopyMsMax, gpuCopyMs);
            _rawReadbackMsSum += readbackMs; _rawReadbackMsMax = Math.Max(_rawReadbackMsMax, readbackMs);
            _rawPublishMsSum += publishMs; _rawPublishMsMax = Math.Max(_rawPublishMsMax, publishMs);
            _rawEyeWidth = eyeWidth; _rawEyeHeight = eyeHeight; _rawSbsBytes = sbsBytes;
            MaybeWriteLocked();
        }
    }

    public void RecordJsSample(string json)
    {
        lock (_sync)
        {
            if (_disposed) return;
            _js.Write('{'); _js.Write("\"hostElapsedMs\":");
            _js.Write(_clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture));
            _js.Write(",\"sample\":"); _js.Write(string.IsNullOrWhiteSpace(json) ? "null" : json); _js.WriteLine('}');
            _js.Flush(); MaybeWriteLocked();
        }
    }

    private void MaybeWriteLocked(bool force = false)
    {
        if (_disposed) return;
        var nowMs = _clock.ElapsedMilliseconds;
        if (!force && nowMs - _lastWriteMs < 1000) return;
        _process.Refresh();
        var cpuNow = _process.TotalProcessorTime;
        var intervalMs = Math.Max(1, nowMs - _lastWriteMs);
        var cpuMs = (cpuNow - _lastCpu).TotalMilliseconds;
        var cpuPercent = 100.0 * cpuMs / intervalMs / Math.Max(1, Environment.ProcessorCount);
        var avgDecode = _decoded > 0 ? _decodeMsSum / _decoded : 0.0;
        var avgPublish = _published > 0 ? _publishMsSum / _published : 0.0;
        var avgGpuCopy = _rawFrames > 0 ? _rawGpuCopyMsSum / _rawFrames : 0.0;
        var avgReadback = _rawFrames > 0 ? _rawReadbackMsSum / _rawFrames : 0.0;
        var avgRawPublish = _rawFrames > 0 ? _rawPublishMsSum / _rawFrames : 0.0;
        static string F(double value) => value.ToString("0.###", CultureInfo.InvariantCulture);

        _host.Write(F(nowMs / 1000.0)); _host.Write(',');
        _host.Write(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)); _host.Write(',');
        _host.Write(_received); _host.Write(','); _host.Write(_replaced); _host.Write(','); _host.Write(_decoded); _host.Write(','); _host.Write(_published); _host.Write(',');
        _host.Write(F(avgDecode)); _host.Write(','); _host.Write(F(_decodeMsMax)); _host.Write(','); _host.Write(F(avgPublish)); _host.Write(','); _host.Write(F(_publishMsMax)); _host.Write(',');
        _host.Write(_eyeWidth); _host.Write(','); _host.Write(_eyeHeight); _host.Write(','); _host.Write(_lastLeftChars); _host.Write(','); _host.Write(_lastRightChars); _host.Write(',');
        _host.Write(_rawFrames); _host.Write(','); _host.Write(F(avgGpuCopy)); _host.Write(','); _host.Write(F(_rawGpuCopyMsMax)); _host.Write(',');
        _host.Write(F(avgReadback)); _host.Write(','); _host.Write(F(_rawReadbackMsMax)); _host.Write(','); _host.Write(F(avgRawPublish)); _host.Write(','); _host.Write(F(_rawPublishMsMax)); _host.Write(',');
        _host.Write(_rawEyeWidth); _host.Write(','); _host.Write(_rawEyeHeight); _host.Write(','); _host.Write(_rawSbsBytes); _host.Write(',');
        _host.Write(F(_process.WorkingSet64 / 1048576.0)); _host.Write(','); _host.Write(F(_process.PrivateMemorySize64 / 1048576.0)); _host.Write(',');
        _host.Write(F(GC.GetTotalMemory(false) / 1048576.0)); _host.Write(','); _host.WriteLine(F(cpuPercent)); _host.Flush();

        _lastWriteMs = nowMs; _lastCpu = cpuNow;
        _received = _replaced = _decoded = _published = 0;
        _decodeMsSum = _decodeMsMax = _publishMsSum = _publishMsMax = 0;
        _rawFrames = 0;
        _rawGpuCopyMsSum = _rawGpuCopyMsMax = 0;
        _rawReadbackMsSum = _rawReadbackMsMax = 0;
        _rawPublishMsSum = _rawPublishMsMax = 0;
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            MaybeWriteLocked(force: true); _disposed = true; _host.Dispose(); _js.Dispose();
        }
    }
}
''', encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) MainForm state/message bridge for two-phase GPU capture.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')
field_marker = '    private readonly List<IDisposable> _retiredSharedResources = new();\n'
req(s, field_marker, 'v0.13.23 MainForm raw field marker missing')
raw_fields = r'''

    // v0.13.23 B transport: CEF GPU surface -> GPU SBS -> staging readback -> raw MMF.
    private readonly object _stereoRawLock = new();
    private Texture2D? _stereoRawGpuTexture;
    private Texture2D? _stereoRawReadbackTexture;
    private int _stereoRawEyeWidth;
    private int _stereoRawEyeHeight;
    private Format _stereoRawFormat = Format.Unknown;
    private byte[]? _stereoRawBuffer;
    private RawStereoPhase _stereoRawPhase;
    private long _stereoRawPhaseSerial;
    private bool _stereoRawLeftCaptured;
    private bool _suppressBasePresentation;
    private double _stereoRawLeftCopyMs;

    private enum RawStereoPhase { None, Left, Right }
'''
s = s.replace(field_marker, field_marker + raw_fields, 1)

s = sub1(
    r"                updateStereoEyes: function \(left, right\) \{\n                  post\(\{ type: 'stereoEyes', left: String\(left \|\| ''\), right: String\(right \|\| ''\) \}\);\n                \},\n",
    '', s, 'v0.13.23 MainForm updateStereoEyes removal')

s = sub1(
    r'''                case "stereoEyes":\n.*?                    break;\n                case "performanceSample":''',
    r'''                case "stereoGpuPhase":
                    HandleStereoGpuPhase(root);
                    break;
                case "stereoGpuCancel":
                    ResetStereoRawPhaseState();
                    break;
                case "performanceSample":''',
    s, 'v0.13.23 MainForm stereo message replacement', re.S)

layout_marker = '    private void HandleStereoLayout(string? payload)\n'
req(s, layout_marker, 'v0.13.23 HandleStereoLayout marker missing')
phase_handler = r'''    private void HandleStereoGpuPhase(JsonElement root)
    {
        if (_browser is null || _closing || _stereoUiSuspended) return;
        if (!root.TryGetProperty("eye", out var eyeNode) || !root.TryGetProperty("serial", out var serialNode) ||
            !serialNode.TryGetInt64(out var serial) || serial < 0) return;
        var eye = eyeNode.GetString();
        lock (_stereoRawLock)
        {
            if (eye == "left")
            {
                _stereoRawPhase = RawStereoPhase.Left; _stereoRawPhaseSerial = serial; _stereoRawLeftCaptured = false;
                _suppressBasePresentation = true; _stereoRawLeftCopyMs = 0;
            }
            else if (eye == "right")
            {
                if (!_stereoRawLeftCaptured || _stereoRawPhaseSerial != serial)
                {
                    _stereoRawPhase = RawStereoPhase.None; _suppressBasePresentation = false;
                    _ = CancelStereoRawTransportAsync(); return;
                }
                _stereoRawPhase = RawStereoPhase.Right;
            }
            else return;
        }
        try { _browser.GetBrowserHost()?.Invalidate(PaintElementType.View); } catch { }
    }

    private void ResetStereoRawPhaseState()
    {
        lock (_stereoRawLock)
        {
            _stereoRawPhase = RawStereoPhase.None; _stereoRawPhaseSerial = 0; _stereoRawLeftCaptured = false;
            _suppressBasePresentation = false; _stereoRawLeftCopyMs = 0;
        }
    }

'''
s = s.replace(layout_marker, phase_handler + layout_marker, 1)
shutdown_marker = '            _xrSharedTexture?.Dispose();\n'
req(s, shutdown_marker, 'v0.13.23 raw texture shutdown marker missing')
s = s.replace(shutdown_marker, shutdown_marker + '            _stereoRawReadbackTexture?.Dispose();\n            _stereoRawGpuTexture?.Dispose();\n', 1)
s = re.sub(r'(pc-stereo-layout\.js\?v=)[^"\']+', r'\g<1>0.13.23-no-jpeg-raw-sbs', s, count=1)
s = s.replace('GeoGebraForQuest PC v0.12.3 · XR Behind Native', 'GeoGebraForQuest PC v0.13.23 · No-JPEG Raw SBS')
s = s.replace('GeoGebraForQuest PC v0.13.22', 'GeoGebraForQuest PC v0.13.23')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) Replace the old decode worker section with raw transport control helpers.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.InputStereo.cs')
s = p.read_text(encoding='utf-8')
start = s.find('    private volatile bool _stereoUiSuspended;')
end = s.find('    private void RequestResize()', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.23 InputStereo replace markers missing')
new_input_top = r'''    private volatile bool _stereoUiSuspended;

    private void SetStereoInactive()
    {
        Rectangle rect; Size size;
        lock (_geometryLock) { rect = _stereo3DRenderBounds; size = _browserSize; _stereo3DActive = false; }
        ResetStereoRawPhaseState();
        _sharedStereoFrames.SetInactive(rect, size);
        _ = CancelStereoRawTransportAsync();
    }

    private void SetStereoUiSuspended(bool suspended)
    {
        _stereoUiSuspended = suspended;
        if (!suspended) return;
        Rectangle rect; Size size;
        lock (_geometryLock) { rect = _stereo3DRenderBounds; size = _browserSize; }
        ResetStereoRawPhaseState();
        _sharedStereoFrames.SetInactive(rect, size);
        _ = CancelStereoRawTransportAsync();
    }

    private async Task AckStereoRawPhaseAsync(string eye, long serial)
    {
        var browser = _browser; if (browser is null || _closing) return;
        try
        {
            var eyeJson = JsonSerializer.Serialize(eye);
            await browser.EvaluateScriptAsync($$"""
                (function(){
                  if (!window.ggqPcGpuTransport || typeof window.ggqPcGpuTransport.ack !== 'function') return false;
                  return window.ggqPcGpuTransport.ack({{eyeJson}}, {{serial}});
                })();
                """);
        }
        catch { }
    }

    private async Task CancelStereoRawTransportAsync()
    {
        var browser = _browser; if (browser is null || _closing) return;
        try
        {
            await browser.EvaluateScriptAsync("""
                (function(){
                  if (!window.ggqPcGpuTransport || typeof window.ggqPcGpuTransport.cancel !== 'function') return false;
                  return window.ggqPcGpuTransport.cancel();
                })();
                """);
        }
        catch { }
    }

'''
s = s[:start] + new_input_top + s[end:]
if 'DecodeDataUrl' in s or 'QueueStereoFrames' in s or 'DecodeStereoLoop' in s:
    raise SystemExit('v0.13.23 InputStereo still contains JPEG decode worker')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) D3D accelerated paint: two GPU rectangle copies, one staging readback, raw MMF.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.Graphics.cs')
s = p.read_text(encoding='utf-8')
paint_start = s.find('    public void OnAcceleratedPaint(')
ensure_start = s.find('    private void EnsurePcTextureLocked(', paint_start)
if paint_start < 0 or ensure_start < 0:
    raise SystemExit('v0.13.23 Graphics paint markers missing')

new_graphics = r'''    public void OnAcceleratedPaint(
        PaintElementType type,
        Rect dirtyRect,
        AcceleratedPaintInfo acceleratedPaintInfo)
    {
        if (_closing || type != PaintElementType.View || _device is null || _device1 is null) return;
        try
        {
            string? ackEye = null; long ackSerial = 0; bool cancelTransport = false; bool updateBase = true;
            lock (_d3dLock)
            {
                using var cefTexture = _device1.OpenSharedResource1<Texture2D>(acceleratedPaintInfo.SharedTextureHandle);
                RawStereoPhase phase; long phaseSerial; bool suppressBase;
                lock (_stereoRawLock) { phase = _stereoRawPhase; phaseSerial = _stereoRawPhaseSerial; suppressBase = _suppressBasePresentation; }

                if (phase != RawStereoPhase.None)
                {
                    var captured = CaptureStereoRawPhaseLocked(cefTexture, phase, phaseSerial);
                    if (phase == RawStereoPhase.Left)
                    {
                        updateBase = false;
                        if (captured)
                        {
                            lock (_stereoRawLock)
                            {
                                if (_stereoRawPhase == RawStereoPhase.Left && _stereoRawPhaseSerial == phaseSerial)
                                { _stereoRawLeftCaptured = true; _stereoRawPhase = RawStereoPhase.None; }
                            }
                            ackEye = "left"; ackSerial = phaseSerial;
                        }
                        else { ResetStereoRawPhaseState(); cancelTransport = true; }
                    }
                    else
                    {
                        if (captured)
                        {
                            lock (_stereoRawLock)
                            {
                                if (_stereoRawPhaseSerial == phaseSerial)
                                { _stereoRawPhase = RawStereoPhase.None; _stereoRawLeftCaptured = false; _suppressBasePresentation = false; }
                            }
                            ackEye = "right"; ackSerial = phaseSerial;
                        }
                        else { ResetStereoRawPhaseState(); cancelTransport = true; }
                        updateBase = true;
                    }
                }
                else if (suppressBase) updateBase = false;

                if (updateBase) UpdateBaseTextureLocked(cefTexture);
            }
            if (ackEye is not null) _ = AckStereoRawPhaseAsync(ackEye, ackSerial);
            if (cancelTransport) _ = CancelStereoRawTransportAsync();
        }
        catch (Exception ex)
        {
            ResetStereoRawPhaseState();
            if (!_closing)
            {
                _gpuPaintStatus = "GPU paint: " + ShortError(ex); BeginInvokeSafe(UpdateWindowTitle); _ = CancelStereoRawTransportAsync();
            }
        }
    }

    private void UpdateBaseTextureLocked(Texture2D cefTexture)
    {
        if (_device is null) return;
        EnsurePcTextureLocked(cefTexture.Description);
        var next = _currentPcTexture ^ 1; var target = _pcTextures[next]; if (target is null) return;
        _device.ImmediateContext.CopyResource(cefTexture, target); _currentPcTexture = next;
        try
        {
            if (TryQueueGpuPublishLocked(cefTexture))
            {
                _device.ImmediateContext.Flush(); CompleteGpuPublishLocked(cefTexture.Description);
                if (_gpuShareStatus != "A-share GPU") { _gpuShareStatus = "A-share GPU"; BeginInvokeSafe(UpdateWindowTitle); }
            }
        }
        catch (Exception shareError)
        {
            try { _xrSharedMutex?.Release(0); } catch { }
            var status = "A-share: " + ShortError(shareError);
            if (!string.Equals(_gpuShareStatus, status, StringComparison.Ordinal)) { _gpuShareStatus = status; BeginInvokeSafe(UpdateWindowTitle); }
        }
        var frame = Interlocked.Increment(ref _gpuFrameNumber); if ((frame % 120) == 0) BeginInvokeSafe(UpdateWindowTitle);
    }

    private bool CaptureStereoRawPhaseLocked(Texture2D cefTexture, RawStereoPhase phase, long serial)
    {
        if (_device is null) return false;
        bool active; Rectangle rect; Size clientSize;
        lock (_geometryLock) { active = _stereo3DActive && !_stereoUiSuspended; rect = _stereo3DRenderBounds; clientSize = _browserSize; }
        if (!active || rect.Width < 2 || rect.Height < 2) return false;
        var source = cefTexture.Description;
        if (source.Format != Format.B8G8R8A8_UNorm && source.Format != Format.B8G8R8A8_UNorm_SRgb)
        { _gpuPaintStatus = "B raw format: " + source.Format; return false; }

        var left = Math.Clamp(rect.Left, 0, source.Width - 1); var top = Math.Clamp(rect.Top, 0, source.Height - 1);
        var right = Math.Clamp(rect.Right, left + 1, source.Width); var bottom = Math.Clamp(rect.Bottom, top + 1, source.Height);
        var eyeWidth = right - left; var eyeHeight = bottom - top;
        if (eyeWidth < 2 || eyeHeight < 2 || eyeWidth > 2048 || eyeHeight > 2048) return false;
        EnsureStereoRawTexturesLocked(eyeWidth, eyeHeight, source.Format);
        if (_stereoRawGpuTexture is null || _stereoRawReadbackTexture is null) return false;

        var copyWatch = System.Diagnostics.Stopwatch.StartNew();
        var sourceRegion = new ResourceRegion(left, top, 0, right, bottom, 1);
        var destinationX = phase == RawStereoPhase.Left ? 0 : eyeWidth;
        _device.ImmediateContext.CopySubresourceRegion(cefTexture, 0, sourceRegion, _stereoRawGpuTexture, 0, destinationX, 0, 0);
        copyWatch.Stop();
        if (phase == RawStereoPhase.Left)
        { lock (_stereoRawLock) _stereoRawLeftCopyMs = copyWatch.Elapsed.TotalMilliseconds; return true; }

        bool leftReady; double leftCopyMs;
        lock (_stereoRawLock) { leftReady = _stereoRawLeftCaptured && _stereoRawPhaseSerial == serial; leftCopyMs = _stereoRawLeftCopyMs; }
        if (!leftReady) return false;

        var readbackWatch = System.Diagnostics.Stopwatch.StartNew();
        _device.ImmediateContext.CopyResource(_stereoRawGpuTexture, _stereoRawReadbackTexture);
        var mapped = _device.ImmediateContext.MapSubresource(_stereoRawReadbackTexture, 0, MapMode.Read, MapFlags.None);
        try
        {
            var tightStride = checked(eyeWidth * 2 * 4); var totalBytes = checked(tightStride * eyeHeight);
            if (_stereoRawBuffer is null || _stereoRawBuffer.Length < totalBytes) _stereoRawBuffer = new byte[totalBytes];
            for (var y = 0; y < eyeHeight; y++)
                Marshal.Copy(IntPtr.Add(mapped.DataPointer, y * mapped.RowPitch), _stereoRawBuffer, y * tightStride, tightStride);
        }
        finally { _device.ImmediateContext.UnmapSubresource(_stereoRawReadbackTexture, 0); }
        readbackWatch.Stop();

        var sbsStride = checked(eyeWidth * 2 * 4); var sbsBytes = checked(sbsStride * eyeHeight);
        var publishWatch = System.Diagnostics.Stopwatch.StartNew();
        var frame = Interlocked.Increment(ref _stereoFrameNumber);
        _sharedStereoFrames.WriteRawSbs(_stereoRawBuffer!, eyeWidth, eyeHeight, sbsStride,
            new Rectangle(left, top, eyeWidth, eyeHeight), clientSize, frame);
        publishWatch.Stop();
        _performanceTelemetry.RecordRawFrame(leftCopyMs + copyWatch.Elapsed.TotalMilliseconds,
            readbackWatch.Elapsed.TotalMilliseconds, publishWatch.Elapsed.TotalMilliseconds,
            eyeWidth, eyeHeight, sbsBytes);
        _gpuPaintStatus = string.Empty;
        if ((frame % 30) == 0) BeginInvokeSafe(UpdateWindowTitle);
        return true;
    }

    private void EnsureStereoRawTexturesLocked(int eyeWidth, int eyeHeight, Format format)
    {
        if (_device is null) return;
        if (_stereoRawGpuTexture is not null && _stereoRawReadbackTexture is not null &&
            _stereoRawEyeWidth == eyeWidth && _stereoRawEyeHeight == eyeHeight && _stereoRawFormat == format) return;

        _stereoRawReadbackTexture?.Dispose(); _stereoRawGpuTexture?.Dispose();
        _stereoRawReadbackTexture = null; _stereoRawGpuTexture = null;
        var width = checked(eyeWidth * 2);
        _stereoRawGpuTexture = new Texture2D(_device, new Texture2DDescription
        {
            Width = width, Height = eyeHeight, MipLevels = 1, ArraySize = 1, Format = format,
            SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Default,
            BindFlags = BindFlags.None, CpuAccessFlags = CpuAccessFlags.None, OptionFlags = ResourceOptionFlags.None
        });
        _stereoRawReadbackTexture = new Texture2D(_device, new Texture2DDescription
        {
            Width = width, Height = eyeHeight, MipLevels = 1, ArraySize = 1, Format = format,
            SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Staging,
            BindFlags = BindFlags.None, CpuAccessFlags = CpuAccessFlags.Read, OptionFlags = ResourceOptionFlags.None
        });
        _stereoRawEyeWidth = eyeWidth; _stereoRawEyeHeight = eyeHeight; _stereoRawFormat = format; _stereoRawBuffer = null;
    }

'''
s = s[:paint_start] + new_graphics + s[ensure_start:]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 7) Version/package labels.
# ---------------------------------------------------------------------------
for file in ('pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file); s = p.read_text(encoding='utf-8')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.23</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.23.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.23.0</AssemblyVersion>', s, count=1)
    else:
        s = s.replace('GeoGebraForQuest-PC-v0.13.22-pipeline-latency-telemetry-win-x64', 'GeoGebraForQuest-PC-v0.13.23-no-jpeg-raw-sbs-win-x64')
        s = s.replace('0.13.22-pipeline-latency-telemetry', '0.13.23-no-jpeg-raw-sbs')
        s = s.replace('v0.13.22', 'v0.13.23')
    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.23 no-JPEG raw SBS patch applied')
