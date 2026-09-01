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
                $"GeoGebraForQuest PC v0.4.0 Exp46 SBS Overlay startup\r\n" +
                $"Time: {DateTimeOffset.Now:O}\r\n" +
                $"OS: {Environment.OSVersion}\r\n" +
                $"64-bit OS: {Environment.Is64BitOperatingSystem}\r\n" +
                $"64-bit process: {Environment.Is64BitProcess}\r\n" +
                $"BaseDirectory: {AppContext.BaseDirectory}\r\n\r\n");
        }
        catch
        {
            // Logging must never prevent the application from attempting to start.
        }

        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
        {
            var ex = args.ExceptionObject as Exception
                ?? new Exception(args.ExceptionObject?.ToString() ?? "Unknown AppDomain exception");
            WriteException("AppDomain.UnhandledException", ex);
        };

        try
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (_, args) =>
            {
                ShowFatal("Windows Forms thread exception", args.Exception);
            };

            Log("Application.SetHighDpiMode");
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);

            Log("Application.EnableVisualStyles");
            Application.EnableVisualStyles();

            Log("Application.SetCompatibleTextRenderingDefault");
            Application.SetCompatibleTextRenderingDefault(false);

            Log("Creating MainForm");
            using var mainForm = new MainForm();
            mainForm.Text = "GeoGebraForQuest PC · v0.4.0 · Exp46 SBS Overlay";
            Log("MainForm created successfully");

            Application.Run(mainForm);
            Log("Application.Run returned normally");
        }
        catch (Exception ex)
        {
            ShowFatal("Startup exception", ex);
        }
    }

    private static void Log(string message)
    {
        try
        {
            Directory.CreateDirectory(LogDirectory);
            File.AppendAllText(
                LogPath,
                $"[{DateTimeOffset.Now:O}] {message}\r\n");
        }
        catch
        {
        }
    }

    private static void WriteException(string stage, Exception exception)
    {
        try
        {
            Directory.CreateDirectory(LogDirectory);
            File.AppendAllText(
                LogPath,
                $"\r\n[{DateTimeOffset.Now:O}] FATAL: {stage}\r\n" +
                exception +
                "\r\n");
        }
        catch
        {
        }
    }

    private static void ShowFatal(string stage, Exception exception)
    {
        WriteException(stage, exception);

        var message =
            "GeoGebraForQuest PC başlatılamadı.\n\n" +
            $"Aşama: {stage}\n\n" +
            $"{exception.GetType().FullName}: {exception.Message}\n\n" +
            "Ayrıntılı kayıt:\n" + LogPath;

        try
        {
            MessageBox.Show(
                message,
                "GeoGebraForQuest PC v0.4.0 - Başlatma Hatası",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        catch
        {
            try
            {
                File.WriteAllText(
                    Path.Combine(AppContext.BaseDirectory, "GeoGebraForQuestPC-FATAL.txt"),
                    message + "\r\n\r\n" + exception);
            }
            catch
            {
            }
        }
    }
}
