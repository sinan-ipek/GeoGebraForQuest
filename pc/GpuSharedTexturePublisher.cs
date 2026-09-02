using System.IO.MemoryMappedFiles;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed class GpuSharedTexturePublisher : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_A_GPU_v1";
    public const int Magic = 0x47514147; // "GAQG"
    public const int ProtocolVersion = 1;

    private const int Capacity = 64;

    private readonly MemoryMappedFile _mapping;
    private readonly MemoryMappedViewAccessor _view;
    private readonly object _sync = new();
    private long _sequence;
    private bool _disposed;

    public GpuSharedTexturePublisher()
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
        _view.Write(40, Environment.ProcessId);
        _view.Flush();
    }

    public void Publish(IntPtr sharedHandle, int width, int height, Format format)
    {
        if (_disposed || sharedHandle == IntPtr.Zero || width < 2 || height < 2) return;

        lock (_sync)
        {
            var even = Interlocked.Add(ref _sequence, 2);
            var odd = even - 1;

            _view.Write(8, odd);
            _view.Write(16, 1);
            _view.Write(20, width);
            _view.Write(24, height);
            _view.Write(28, (int)format);
            _view.Write(32, sharedHandle.ToInt64());
            _view.Write(40, Environment.ProcessId);
            Thread.MemoryBarrier();
            _view.Write(8, even);
            _view.Flush();
        }
    }

    public void SetInactive()
    {
        if (_disposed) return;
        lock (_sync)
        {
            var even = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, even - 1);
            _view.Write(16, 0);
            Thread.MemoryBarrier();
            _view.Write(8, even);
            _view.Flush();
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        try { SetInactive(); } catch { }
        _disposed = true;
        _view.Dispose();
        _mapping.Dispose();
    }
}
