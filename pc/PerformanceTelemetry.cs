using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace GeoGebraForQuest.PC;

internal sealed class HostPerformanceTelemetry : IDisposable
{
    private readonly object _sync = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly Process _process = Process.GetCurrentProcess();
    private readonly string _hostPath;
    private readonly string _jsPath;
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
    private bool _disposed;

    public HostPerformanceTelemetry()
    {
        _hostPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.Host.csv");
        _jsPath = Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.JS.jsonl");

        _host = new StreamWriter(new FileStream(
            _hostPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite,
            4096, FileOptions.SequentialScan), new UTF8Encoding(false));
        _js = new StreamWriter(new FileStream(
            _jsPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite,
            4096, FileOptions.SequentialScan), new UTF8Encoding(false));

        _host.WriteLine(
            "elapsed_s,utc,received_pairs,pending_replaced,decoded_pairs,published_pairs," +
            "avg_decode_ms,max_decode_ms,avg_publish_ms,max_publish_ms," +
            "eye_width,eye_height,left_dataurl_chars,right_dataurl_chars," +
            "working_set_mb,private_mb,gc_heap_mb,cpu_percent");
        _host.Flush();
        _lastCpu = _process.TotalProcessorTime;
    }

    public void RecordReceived(int leftChars, int rightChars, bool replaced)
    {
        lock (_sync)
        {
            _received++;
            if (replaced) _replaced++;
            _lastLeftChars = leftChars;
            _lastRightChars = rightChars;
            MaybeWriteLocked();
        }
    }

    public void RecordDecoded(double ms, int width, int height)
    {
        lock (_sync)
        {
            _decoded++;
            _decodeMsSum += ms;
            _decodeMsMax = Math.Max(_decodeMsMax, ms);
            _eyeWidth = width;
            _eyeHeight = height;
            MaybeWriteLocked();
        }
    }

    public void RecordPublished(double ms)
    {
        lock (_sync)
        {
            _published++;
            _publishMsSum += ms;
            _publishMsMax = Math.Max(_publishMsMax, ms);
            MaybeWriteLocked();
        }
    }

    public void RecordJsSample(string json)
    {
        lock (_sync)
        {
            if (_disposed) return;
            _js.Write('{');
            _js.Write("\"hostElapsedMs\":");
            _js.Write(_clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture));
            _js.Write(",\"sample\":");
            _js.Write(string.IsNullOrWhiteSpace(json) ? "null" : json);
            _js.WriteLine('}');
            _js.Flush();
            MaybeWriteLocked();
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

        static string F(double value) => value.ToString("0.###", CultureInfo.InvariantCulture);

        _host.Write(F(nowMs / 1000.0));
        _host.Write(',');
        _host.Write(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture));
        _host.Write(',');
        _host.Write(_received);
        _host.Write(',');
        _host.Write(_replaced);
        _host.Write(',');
        _host.Write(_decoded);
        _host.Write(',');
        _host.Write(_published);
        _host.Write(',');
        _host.Write(F(avgDecode));
        _host.Write(',');
        _host.Write(F(_decodeMsMax));
        _host.Write(',');
        _host.Write(F(avgPublish));
        _host.Write(',');
        _host.Write(F(_publishMsMax));
        _host.Write(',');
        _host.Write(_eyeWidth);
        _host.Write(',');
        _host.Write(_eyeHeight);
        _host.Write(',');
        _host.Write(_lastLeftChars);
        _host.Write(',');
        _host.Write(_lastRightChars);
        _host.Write(',');
        _host.Write(F(_process.WorkingSet64 / 1048576.0));
        _host.Write(',');
        _host.Write(F(_process.PrivateMemorySize64 / 1048576.0));
        _host.Write(',');
        _host.Write(F(GC.GetTotalMemory(false) / 1048576.0));
        _host.Write(',');
        _host.WriteLine(F(cpuPercent));
        _host.Flush();

        _lastWriteMs = nowMs;
        _lastCpu = cpuNow;
        _received = 0;
        _replaced = 0;
        _decoded = 0;
        _published = 0;
        _decodeMsSum = 0;
        _decodeMsMax = 0;
        _publishMsSum = 0;
        _publishMsMax = 0;
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            MaybeWriteLocked(force: true);
            _disposed = true;
            _host.Dispose();
            _js.Dispose();
        }
    }
}
