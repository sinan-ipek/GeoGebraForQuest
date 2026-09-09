using System.IO.Compression;

namespace GeoGebraForQuest.PC;

internal static class LogBundle
{
    public static void Create()
    {
        try
        {
            var baseDir = AppContext.BaseDirectory;
            var xrDir = Path.Combine(baseDir, "xr");
            var zipPath = Path.Combine(baseDir, "log.zip");
            var tempPath = zipPath + ".tmp";

            var files = new List<string>();
            AddIfExists(files, Path.Combine(baseDir, "GeoGebraForQuestPC.Performance.Host.csv"));
            AddIfExists(files, Path.Combine(baseDir, "GeoGebraForQuestPC.Performance.JS.jsonl"));
            AddIfExists(files, Path.Combine(xrDir, "GeoGebraForQuestPC.Performance.XR.csv"));

            AddMatchingLogs(files, baseDir);
            if (Directory.Exists(xrDir)) AddMatchingLogs(files, xrDir);

            files = files
                .Where(File.Exists)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();

            if (files.Count == 0) return;

            try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch { }

            using (var archive = ZipFile.Open(tempPath, ZipArchiveMode.Create))
            {
                var usedNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var file in files)
                {
                    var entryName = Path.GetFileName(file);
                    if (!usedNames.Add(entryName))
                    {
                        var parent = Path.GetFileName(Path.GetDirectoryName(file));
                        entryName = string.IsNullOrWhiteSpace(parent)
                            ? entryName
                            : parent + "-" + entryName;
                    }

                    archive.CreateEntryFromFile(
                        file,
                        entryName,
                        CompressionLevel.Optimal);
                }
            }

            if (File.Exists(zipPath)) File.Delete(zipPath);
            File.Move(tempPath, zipPath);
        }
        catch
        {
            // Logging must never prevent normal application shutdown.
        }
    }

    private static void AddIfExists(List<string> files, string path)
    {
        if (File.Exists(path)) files.Add(path);
    }

    private static void AddMatchingLogs(List<string> files, string directory)
    {
        if (!Directory.Exists(directory)) return;

        foreach (var file in Directory.EnumerateFiles(directory, "GeoGebraForQuestPC.*", SearchOption.TopDirectoryOnly))
        {
            var extension = Path.GetExtension(file);
            if (extension.Equals(".csv", StringComparison.OrdinalIgnoreCase) ||
                extension.Equals(".jsonl", StringComparison.OrdinalIgnoreCase) ||
                extension.Equals(".log", StringComparison.OrdinalIgnoreCase) ||
                extension.Equals(".txt", StringComparison.OrdinalIgnoreCase))
            {
                files.Add(file);
            }
        }
    }
}
