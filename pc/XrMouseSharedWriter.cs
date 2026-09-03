using System.IO.MemoryMappedFiles;

namespace GeoGebraForQuest.PC;

internal sealed class XrMouseSharedWriter : IDisposable
{
    private const string MapName = "Local\\GeoGebraForQuestPC_Mouse_v1";
    private const int MappingSize = 64;
    private const int Magic = 0x47514D53; // GQMS
    private const int ProtocolVersion = 1;

    private readonly object _lock = new();
    private MemoryMappedFile? _mapping;
    private MemoryMappedViewAccessor? _view;
    private long _sequence;
    private bool _disposed;

    public XrMouseSharedWriter()
    {
        EnsureOpen();
        Publish(false, 0.0f, 0.0f);
    }

    public void Publish(bool valid, float u, float v)
    {
        if (_disposed) return;

        lock (_lock)
        {
            EnsureOpen();
            if (_view is null) return;

            u = Math.Clamp(u, 0.0f, 1.0f);
            v = Math.Clamp(v, 0.0f, 1.0f);

            _sequence += 2;
            var oddSequence = _sequence - 1;

            _view.Write(8, oddSequence);
            _view.Write(16, valid ? 1 : 0);
            _view.Write(20, u);
            _view.Write(24, v);
            Thread.MemoryBarrier();
            _view.Write(8, _sequence);
        }
    }

    private void EnsureOpen()
    {
        if (_disposed || _view is not null) return;

        _mapping = MemoryMappedFile.CreateOrOpen(
            MapName,
            MappingSize,
            MemoryMappedFileAccess.ReadWrite);
        _view = _mapping.CreateViewAccessor(
            0,
            MappingSize,
            MemoryMappedFileAccess.ReadWrite);

        _view.Write(0, Magic);
        _view.Write(4, ProtocolVersion);
        _view.Write(8, 0L);
        _view.Write(16, 0);
        _view.Write(20, 0.0f);
        _view.Write(24, 0.0f);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        lock (_lock)
        {
            try
            {
                if (_view is not null)
                {
                    _sequence += 2;
                    _view.Write(8, _sequence - 1);
                    _view.Write(16, 0);
                    Thread.MemoryBarrier();
                    _view.Write(8, _sequence);
                }
            }
            catch { }

            _view?.Dispose();
            _view = null;
            _mapping?.Dispose();
            _mapping = null;
        }
    }
}

internal sealed partial class MainForm
{
    private readonly XrMouseSharedWriter _xrMousePointer = new();

    private void PublishMousePointerToXr(Point point, bool valid)
    {
        if (!valid || ClientSize.Width < 2 || ClientSize.Height < 2)
        {
            _xrMousePointer.Publish(false, 0.0f, 0.0f);
            return;
        }

        var u = Math.Clamp(point.X / (float)Math.Max(1, ClientSize.Width - 1), 0.0f, 1.0f);
        var v = Math.Clamp(point.Y / (float)Math.Max(1, ClientSize.Height - 1), 0.0f, 1.0f);
        _xrMousePointer.Publish(true, u, v);
    }
}
