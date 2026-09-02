using System.IO.MemoryMappedFiles;

namespace GeoGebraForQuest.PC;

internal sealed class XrInputSharedReader : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_Input_v1";
    public const int Magic = 0x4751494E; // "NIQG"
    public const int ProtocolVersion = 1;

    private const int Capacity = 64;

    private readonly MemoryMappedFile _mapping;
    private readonly MemoryMappedViewAccessor _view;
    private long _lastSequence;
    private bool _disposed;

    public XrInputSharedReader()
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
        _view.Flush();
    }

    public bool TryRead(out XrPointerSample sample)
    {
        sample = default;
        if (_disposed) return false;

        for (var attempt = 0; attempt < 3; attempt++)
        {
            var first = _view.ReadInt64(8);
            if ((first & 1L) != 0) continue;
            if (first == _lastSequence) return false;

            var valid = _view.ReadInt32(16) != 0;
            var u = _view.ReadSingle(20);
            var v = _view.ReadSingle(24);
            var trigger = _view.ReadInt32(28) != 0;

            Thread.MemoryBarrier();
            var second = _view.ReadInt64(8);
            if (first == second && (second & 1L) == 0)
            {
                _lastSequence = second;
                sample = new XrPointerSample(valid, u, v, trigger);
                return true;
            }
        }

        return false;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _view.Dispose();
        _mapping.Dispose();
    }
}

internal readonly record struct XrPointerSample(bool Valid, float U, float V, bool TriggerDown);
