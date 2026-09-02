using System.Diagnostics;

namespace GeoGebraForQuest.PC;

internal sealed class XrCompanionManager : IDisposable
{
    private readonly object _sync = new();
    private Process? _process;
    private bool _disposed;
    private bool _wantRunning;
    private int _restartGeneration;

    public event Action<string>? StatusChanged;

    public bool IsRunning
    {
        get
        {
            lock (_sync)
            {
                return _process is { HasExited: false };
            }
        }
    }

    public bool Start()
    {
        lock (_sync)
        {
            if (_disposed) return false;
            _wantRunning = true;
            if (_process is { HasExited: false }) return true;
            return StartCoreLocked();
        }
    }

    private bool StartCoreLocked()
    {
        var executable = Path.Combine(
            AppContext.BaseDirectory,
            "xr",
            "GeoGebraForQuestPC.XR.exe");
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

            var process = new Process
            {
                StartInfo = info,
                EnableRaisingEvents = true
            };
            process.Exited += (_, _) => HandleExited(process);

            if (!process.Start())
            {
                process.Dispose();
                StatusChanged?.Invoke("OpenXR yardımcı programı başlatılamadı");
                return false;
            }

            _process = process;
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

    private void HandleExited(Process process)
    {
        var code = -1;
        try { code = process.ExitCode; } catch { }

        int generation;
        bool restart;
        lock (_sync)
        {
            if (ReferenceEquals(_process, process))
                _process = null;

            restart = !_disposed && _wantRunning;
            generation = ++_restartGeneration;
        }

        try { process.Dispose(); } catch { }

        if (!restart)
        {
            StatusChanged?.Invoke(code == 0
                ? "Quest/OpenXR bağlantısı kapandı"
                : $"Quest/OpenXR yardımcı programı kapandı ({code})");
            return;
        }

        StatusChanged?.Invoke(code == 0
            ? "Quest/OpenXR yeniden bağlanıyor…"
            : $"OpenXR kapandı ({code}); yeniden başlatılıyor…");

        _ = Task.Run(async () =>
        {
            await Task.Delay(900).ConfigureAwait(false);
            lock (_sync)
            {
                if (_disposed || !_wantRunning || generation != _restartGeneration)
                    return;
                if (_process is { HasExited: false }) return;
                StartCoreLocked();
            }
        });
    }

    public void Stop()
    {
        Process? process;
        lock (_sync)
        {
            _wantRunning = false;
            ++_restartGeneration;
            process = _process;
            _process = null;
        }

        if (process is not null)
        {
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
                try { process.Dispose(); } catch { }
            }
        }

        StatusChanged?.Invoke("Quest/OpenXR bağlantısı durduruldu");
    }

    public void Dispose()
    {
        lock (_sync)
        {
            if (_disposed) return;
            _disposed = true;
        }
        Stop();
    }
}
