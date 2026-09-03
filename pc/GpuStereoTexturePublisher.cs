using System.IO.MemoryMappedFiles;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed class GpuStereoTexturePublisher : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_B_GPU_v1";
    public const int Magic = 0x47514247; // "GBQG"
    public const int ProtocolVersion = 1;

    private const int Capacity = 96;

    private readonly MemoryMappedFile _mapping;
    private readonly MemoryMappedViewAccessor _view;
    private readonly object _sync = new();
    private long _sequence;
    private bool _disposed;

    public GpuStereoTexturePublisher()
    {
        _mapping = MemoryMappedFile.CreateOrOpen(
            MappingName,
            Capacity,
            MemoryMappedFileAccess.ReadWrite);
        _view = _mapping.CreateViewAccessor(0, Capacity, MemoryMappedFileAccess.ReadWrite);

        _view.Write(0, Magic);
        _view.Write(4, ProtocolVersion);
        _view.Write(8, 0L);
        _view.Write(16, 0);
        _view.Write(68, Environment.ProcessId);
        _view.Flush();
    }

    public void Publish(
        IntPtr sharedHandle,
        int clientWidth,
        int clientHeight,
        Rectangle panel,
        int eyeWidth,
        int eyeHeight,
        Format format,
        long frameNumber)
    {
        if (_disposed ||
            sharedHandle == IntPtr.Zero ||
            clientWidth < 2 || clientHeight < 2 ||
            panel.Width < 2 || panel.Height < 2 ||
            eyeWidth < 2 || eyeHeight < 2)
        {
            return;
        }

        lock (_sync)
        {
            var even = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, even - 1);
            _view.Write(16, 1);
            _view.Write(20, clientWidth);
            _view.Write(24, clientHeight);
            _view.Write(28, panel.Left);
            _view.Write(32, panel.Top);
            _view.Write(36, panel.Width);
            _view.Write(40, panel.Height);
            _view.Write(44, eyeWidth);
            _view.Write(48, eyeHeight);
            _view.Write(52, (int)format);
            _view.Write(56, sharedHandle.ToInt64());
            _view.Write(64, unchecked((int)frameNumber));
            _view.Write(68, Environment.ProcessId);
            Thread.MemoryBarrier();
            _view.Write(8, even);
            _view.Flush();
        }
    }

    public void SetInactive(Rectangle panel, Size clientSize)
    {
        if (_disposed) return;

        lock (_sync)
        {
            var even = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, even - 1);
            _view.Write(16, 0);
            _view.Write(20, Math.Max(0, clientSize.Width));
            _view.Write(24, Math.Max(0, clientSize.Height));
            _view.Write(28, panel.Left);
            _view.Write(32, panel.Top);
            _view.Write(36, panel.Width);
            _view.Write(40, panel.Height);
            _view.Write(44, 0);
            _view.Write(48, 0);
            _view.Write(52, 0);
            _view.Write(56, 0L);
            _view.Write(64, 0);
            _view.Write(68, Environment.ProcessId);
            Thread.MemoryBarrier();
            _view.Write(8, even);
            _view.Flush();
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        try { SetInactive(Rectangle.Empty, Size.Empty); } catch { }
        _disposed = true;
        _view.Dispose();
        _mapping.Dispose();
    }
}
