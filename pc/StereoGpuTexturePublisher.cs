using System.IO.MemoryMappedFiles;
using SharpDX.DXGI;

namespace GeoGebraForQuest.PC;

internal sealed class StereoGpuTexturePublisher : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_B_GPU_v1";
    public const int Magic = 0x47514247; // "GBQG"
    public const int ProtocolVersion = 1;
    private const int Capacity = 128;

    private readonly MemoryMappedFile _mapping;
    private readonly MemoryMappedViewAccessor _view;
    private readonly object _sync = new();
    private long _sequence;
    private bool _disposed;

    public StereoGpuTexturePublisher()
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
        _view.Write(88, Environment.ProcessId);
        _view.Flush();
    }

    public void Publish(
        IntPtr sharedHandle,
        int textureWidth,
        int textureHeight,
        Format format,
        Size clientSize,
        Rectangle stereoPanel,
        Rectangle stagePixels,
        long frameNumber)
    {
        if (_disposed || sharedHandle == IntPtr.Zero ||
            textureWidth < 2 || textureHeight < 2 ||
            clientSize.Width < 2 || clientSize.Height < 2 ||
            stereoPanel.Width < 2 || stereoPanel.Height < 2 ||
            stagePixels.Width < 4 || stagePixels.Height < 2)
        {
            return;
        }

        lock (_sync)
        {
            var even = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, even - 1);
            _view.Write(16, 1);
            _view.Write(20, textureWidth);
            _view.Write(24, textureHeight);
            _view.Write(28, (int)format);
            _view.Write(32, sharedHandle.ToInt64());
            _view.Write(40, clientSize.Width);
            _view.Write(44, clientSize.Height);
            _view.Write(48, stereoPanel.Left);
            _view.Write(52, stereoPanel.Top);
            _view.Write(56, stereoPanel.Width);
            _view.Write(60, stereoPanel.Height);
            _view.Write(64, stagePixels.Left);
            _view.Write(68, stagePixels.Top);
            _view.Write(72, stagePixels.Width);
            _view.Write(76, stagePixels.Height);
            _view.Write(80, frameNumber);
            _view.Write(88, Environment.ProcessId);
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
