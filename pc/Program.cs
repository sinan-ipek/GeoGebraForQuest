using CefSharp;
using CefSharp.OffScreen;

namespace GeoGebraForQuest.PC;

internal static class Program
{
    private static readonly string LogDirectory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "GeoGebraForQuestPC");

    private static readonly string LogPath = Path.Combine(LogDirectory, "startup.log");

    [STAThread]
    private static void Main()
    {
        try
        {
            Directory.CreateDirectory(LogDirectory);
            File.WriteAllText(
                LogPath,
                $"GeoGebraForQuest PC v0.11.0 CEF GPU Direct startup\r\n" +
                $"Time: {DateTimeOffset.Now:O}\r\n" +
                $"OS: {Environment.OSVersion}\r\n" +
                $"64-bit process: {Environment.Is64BitProcess}\r\n" +
                $"BaseDirectory: {AppContext.BaseDirectory}\r\n\r\n");
        }
        catch
        {
        }

        try
        {
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            CefSharpSettings.SubprocessExitIfParentProcessClosed = true;

            var cefCache = Path.Combine(LogDirectory, "CEF");
            Directory.CreateDirectory(cefCache);

            var settings = new CefSettings
            {
                CachePath = cefCache,
                WindowlessRenderingEnabled = true,
                LogFile = Path.Combine(LogDirectory, "cef.log"),
                LogSeverity = LogSeverity.Warning
            };
            settings.EnableAudio();
            settings.CefCommandLineArgs["use-angle"] = "d3d11";
            settings.CefCommandLineArgs["autoplay-policy"] = "no-user-gesture-required";
            settings.CefCommandLineArgs["disable-gpu-shader-disk-cache"] = "1";

            if (!Cef.Initialize(settings, performDependencyCheck: true, browserProcessHandler: null))
            {
                throw new InvalidOperationException($"Cef.Initialize başarısız. ExitCode={Cef.GetExitCode()}");
            }

            using var mainForm = new MainForm();
            Application.Run(mainForm);
        }
        catch (Exception ex)
        {
            try
            {
                File.AppendAllText(LogPath, $"\r\nFATAL\r\n{ex}\r\n");
            }
            catch
            {
            }

            try
            {
                MessageBox.Show(
                    ex.ToString(),
                    "GeoGebraForQuest PC v0.11.0 - Başlatma Hatası",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch
            {
            }
        }
        finally
        {
            try
            {
                if (Cef.IsInitialized == true)
                {
                    Cef.Shutdown();
                }
            }
            catch
            {
            }
        }
    }
}
