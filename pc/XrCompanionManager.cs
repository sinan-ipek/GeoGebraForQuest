using System.Diagnostics;

namespace GeoGebraForQuest.PC;

internal sealed class XrCompanionManager : IDisposable
{
    private Process? _process;
    private bool _disposed;

    public event Action<string>? StatusChanged;

    public bool IsRunning => _process is { HasExited: false };

    public bool Start()
    {
        if (_disposed) return false;
        if (IsRunning) return true;

        var executable = Path.Combine(AppContext.BaseDirectory, "xr", "GeoGebraForQuestPC.XR.exe");
        if (!File.Exists(executable))
        {
            StatusChanged?.Invoke("OpenXR yardımcı programı bulunamadı");
            return false;
        }

        try
        {
            var info = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = $"--pid {Environment.ProcessId}",
                WorkingDirectory = Path.GetDirectoryName(executable) ?? AppContext.BaseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            _process = new Process
            {
                StartInfo = info,
                EnableRaisingEvents = true
            };
            _process.Exited += (_, _) =>
            {
                var code = -1;
                try { code = _process?.ExitCode ?? -1; } catch { }
                StatusChanged?.Invoke(code == 0
                    ? "Quest/OpenXR bağlantısı kapandı"
                    : $"Quest/OpenXR yardımcı programı kapandı ({code})");
            };

            if (!_process.Start())
            {
                _process.Dispose();
                _process = null;
                StatusChanged?.Invoke("OpenXR yardımcı programı başlatılamadı");
                return false;
            }

            StatusChanged?.Invoke("OpenXR başlatılıyor… Quest Link/Air Link bekleniyor");
            return true;
        }
        catch (Exception ex)
        {
            _process?.Dispose();
            _process = null;
            StatusChanged?.Invoke("OpenXR başlatma hatası: " + ex.Message);
            return false;
        }
    }

    public void Stop()
    {
        var process = _process;
        _process = null;
        if (process is null) return;

        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(1500);
            }
        }
        catch
        {
        }
        finally
        {
            process.Dispose();
        }

        StatusChanged?.Invoke("Quest/OpenXR bağlantısı durduruldu");
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
    }
}
