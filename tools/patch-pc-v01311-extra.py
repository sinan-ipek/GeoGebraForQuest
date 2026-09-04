from pathlib import Path
import re

# Native audio player: explicitly target Quest/Oculus/Meta playback endpoint when available.
Path('pc/QuestTonePlayer.cs').write_text(r'''using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace GeoGebraForQuest.PC;

internal sealed class QuestTonePlayer : IDisposable
{
    private readonly object _sync = new();
    private WasapiOut? _output;
    private BufferedWaveProvider? _buffer;
    private bool _failed;

    public void PlayClick()
    {
        lock (_sync)
        {
            try
            {
                EnsureOutput();
                if (_buffer is null) return;

                const int sampleRate = 48000;
                const double duration = 0.035;
                const double frequency = 880.0;
                var count = (int)(sampleRate * duration);
                var bytes = new byte[count * 2];
                for (var i = 0; i < count; i++)
                {
                    var env = 1.0 - (double)i / count;
                    var sample = Math.Sin(2.0 * Math.PI * frequency * i / sampleRate) * 0.22 * env;
                    var s = (short)(sample * short.MaxValue);
                    bytes[i * 2] = (byte)(s & 0xff);
                    bytes[i * 2 + 1] = (byte)((s >> 8) & 0xff);
                }
                _buffer.AddSamples(bytes, 0, bytes.Length);
            }
            catch
            {
                _failed = true;
            }
        }
    }

    private void EnsureOutput()
    {
        if (_output is not null || _failed) return;

        using var enumerator = new MMDeviceEnumerator();
        var devices = enumerator.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active).ToList();
        var quest = devices.FirstOrDefault(d =>
            d.FriendlyName.Contains("Quest", StringComparison.OrdinalIgnoreCase) ||
            d.FriendlyName.Contains("Oculus", StringComparison.OrdinalIgnoreCase) ||
            d.FriendlyName.Contains("Meta", StringComparison.OrdinalIgnoreCase));
        quest ??= enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);

        _buffer = new BufferedWaveProvider(new WaveFormat(48000, 16, 1))
        {
            DiscardOnBufferOverflow = true,
            BufferDuration = TimeSpan.FromMilliseconds(300)
        };
        _output = new WasapiOut(quest, AudioClientShareMode.Shared, false, 20);
        _output.Init(_buffer);
        _output.Play();
    }

    public void Dispose()
    {
        lock (_sync)
        {
            try { _output?.Stop(); } catch { }
            _output?.Dispose();
            _output = null;
            _buffer = null;
        }
    }
}
''', encoding='utf-8')

Path('pc/SplashForm.cs').write_text(r'''namespace GeoGebraForQuest.PC;

internal sealed class SplashForm : Form
{
    public SplashForm()
    {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = false;
        TopMost = true;
        BackColor = Color.FromArgb(15, 20, 28);
        ClientSize = new Size(620, 300);
        DoubleBuffered = true;

        var title = new Label
        {
            Dock = DockStyle.Top,
            Height = 165,
            Text = "GeoGebraForQuest PC",
            ForeColor = Color.White,
            TextAlign = ContentAlignment.BottomCenter,
            Font = new Font("Segoe UI", 30f, FontStyle.Bold)
        };
        var sub = new Label
        {
            Dock = DockStyle.Top,
            Height = 55,
            Text = "Quest bağlantısı ve GeoGebra hazırlanıyor…",
            ForeColor = Color.FromArgb(0, 221, 245),
            TextAlign = ContentAlignment.MiddleCenter,
            Font = new Font("Segoe UI", 12f, FontStyle.Regular)
        };
        var version = new Label
        {
            Dock = DockStyle.Fill,
            Text = "v0.13.11",
            ForeColor = Color.Gainsboro,
            TextAlign = ContentAlignment.TopCenter,
            Font = new Font("Segoe UI", 10f)
        };
        Controls.Add(version);
        Controls.Add(sub);
        Controls.Add(title);
    }
}
''', encoding='utf-8')

# Program: show splash during CEF init and close it immediately before main window.
p = Path('pc/Program.cs')
t = p.read_text(encoding='utf-8')
marker = '''            Application.SetCompatibleTextRenderingDefault(false);\n\n            CefSharpSettings.SubprocessExitIfParentProcessClosed = true;'''
repl = '''            Application.SetCompatibleTextRenderingDefault(false);\n\n            using var splash = new SplashForm();\n            splash.Show();\n            splash.Refresh();\n            Application.DoEvents();\n\n            CefSharpSettings.SubprocessExitIfParentProcessClosed = true;'''
if marker not in t:
    raise SystemExit('Program splash insertion marker missing')
t = t.replace(marker, repl, 1)
marker2 = '''            using var mainForm = new MainForm();\n            Application.Run(mainForm);'''
repl2 = '''            using var mainForm = new MainForm();\n            splash.Close();\n            Application.Run(mainForm);'''
if marker2 not in t:
    raise SystemExit('Program main form marker missing')
t = t.replace(marker2, repl2, 1)
p.write_text(t, encoding='utf-8')

# Add NAudio package.
p = Path('pc/GeoGebraForQuest.PC.csproj')
t = p.read_text(encoding='utf-8')
needle = '    <PackageReference Include="CefSharp.OffScreen.NETCore" Version="133.4.21" />'
if needle not in t:
    raise SystemExit('CefSharp package marker missing')
t = t.replace(needle, needle + '\n    <PackageReference Include="NAudio" Version="2.2.1" />', 1)
p.write_text(t, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.11 native Quest audio + splash files applied')
