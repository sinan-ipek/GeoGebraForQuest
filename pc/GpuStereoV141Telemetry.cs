using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace GeoGebraForQuest.PC;

internal sealed class GpuStereoV141Telemetry : IDisposable
{
    private readonly object _sync = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly StreamWriter _csv;
    private bool _disposed;

    public GpuStereoV141Telemetry()
    {
        _csv = new StreamWriter(
            Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC.Performance.GPU-v0141.csv"),
            append: false,
            new UTF8Encoding(false));
        _csv.AutoFlush = true;
        _csv.WriteLine(
            "elapsed_ms,event,serial,texture_w,texture_h,stage_w,stage_h,copy_submit_ms,detail");
    }

    public void Event(
        string name,
        long serial = -1,
        int textureWidth = 0,
        int textureHeight = 0,
        int stageWidth = 0,
        int stageHeight = 0,
        double copySubmitMs = 0,
        string detail = "")
    {
        if (_disposed) return;
        lock (_sync)
        {
            if (_disposed) return;
            _csv.WriteLine(string.Join(",", new[]
            {
                _clock.Elapsed.TotalMilliseconds.ToString("F3", CultureInfo.InvariantCulture),
                Csv(name),
                serial.ToString(CultureInfo.InvariantCulture),
                textureWidth.ToString(CultureInfo.InvariantCulture),
                textureHeight.ToString(CultureInfo.InvariantCulture),
                stageWidth.ToString(CultureInfo.InvariantCulture),
                stageHeight.ToString(CultureInfo.InvariantCulture),
                copySubmitMs.ToString("F3", CultureInfo.InvariantCulture),
                Csv(detail)
            }));
        }
    }

    private static string Csv(string value) =>
        "\"" + (value ?? string.Empty).Replace("\"", "\"\"") + "\"";

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            _disposed = true;
            _csv.Dispose();
        }
    }
}
