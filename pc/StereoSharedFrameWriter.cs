using System.Drawing.Imaging;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;

namespace GeoGebraForQuest.PC;

internal sealed class StereoSharedFrameWriter : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_Stereo_v1";

    private const int Magic = 0x47515150; // PQQG, little-endian marker used only for validation.
    private const int ProtocolVersion = 1;
    private const long HeaderSize = 128;
    private const int MaxEyeWidth = 2048;
    private const int MaxEyeHeight = 2048;
    private const long MaxEyeBytes = (long)MaxEyeWidth * MaxEyeHeight * 4;
    private const long Capacity = HeaderSize + MaxEyeBytes * 2;
    private const long LeftOffset = HeaderSize;
    private const long RightOffset = HeaderSize + MaxEyeBytes;

    private readonly MemoryMappedFile _mapping;
    private readonly MemoryMappedViewAccessor _view;
    private readonly object _sync = new();
    private long _sequence;
    private bool _disposed;

    public StereoSharedFrameWriter()
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
        _view.Write(60, Environment.ProcessId);
        _view.Flush();
    }

    public void WriteFrames(
        Bitmap leftSource,
        Bitmap rightSource,
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        long frameNumber)
    {
        if (_disposed || applicationClientSize.Width < 1 || applicationClientSize.Height < 1) return;

        lock (_sync)
        {
            using var left = PrepareBitmap(leftSource);
            using var right = PrepareBitmap(rightSource, left.Width, left.Height);

            var finalLeft = left;
            var finalRight = right;
            Bitmap? resizedLeft = null;
            Bitmap? resizedRight = null;

            try
            {
                if (left.Width > MaxEyeWidth || left.Height > MaxEyeHeight)
                {
                    var scale = Math.Min(
                        MaxEyeWidth / (double)left.Width,
                        MaxEyeHeight / (double)left.Height);
                    var width = Math.Max(2, (int)Math.Round(left.Width * scale));
                    var height = Math.Max(2, (int)Math.Round(left.Height * scale));
                    resizedLeft = ResizeBitmap(left, width, height);
                    resizedRight = ResizeBitmap(right, width, height);
                    finalLeft = resizedLeft;
                    finalRight = resizedRight;
                }

                var stride = checked(finalLeft.Width * 4);
                var evenSequence = Interlocked.Add(ref _sequence, 2);
                var oddSequence = evenSequence - 1;

                // Seqlock: odd means writer active; even means a complete frame is available.
                _view.Write(8, oddSequence);
                _view.Write(16, 1); // active
                _view.Write(20, applicationClientSize.Width);
                _view.Write(24, applicationClientSize.Height);
                _view.Write(28, stereoPanelClientBounds.Left);
                _view.Write(32, stereoPanelClientBounds.Top);
                _view.Write(36, stereoPanelClientBounds.Width);
                _view.Write(40, stereoPanelClientBounds.Height);
                _view.Write(44, finalLeft.Width);
                _view.Write(48, finalLeft.Height);
                _view.Write(52, stride);
                _view.Write(56, frameNumber);
                _view.Write(60, Environment.ProcessId);

                WriteBitmap(finalLeft, LeftOffset, stride);
                WriteBitmap(finalRight, RightOffset, stride);

                Thread.MemoryBarrier();
                _view.Write(8, evenSequence);
                _view.Flush();
            }
            finally
            {
                resizedLeft?.Dispose();
                resizedRight?.Dispose();
            }
        }
    }

    public void SetInactive(Rectangle stereoPanelClientBounds, Size applicationClientSize)
    {
        if (_disposed) return;

        lock (_sync)
        {
            var evenSequence = Interlocked.Add(ref _sequence, 2);
            var oddSequence = evenSequence - 1;
            _view.Write(8, oddSequence);
            _view.Write(16, 0);
            _view.Write(20, applicationClientSize.Width);
            _view.Write(24, applicationClientSize.Height);
            _view.Write(28, stereoPanelClientBounds.Left);
            _view.Write(32, stereoPanelClientBounds.Top);
            _view.Write(36, stereoPanelClientBounds.Width);
            _view.Write(40, stereoPanelClientBounds.Height);
            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
            _view.Flush();
        }
    }

    private void WriteBitmap(Bitmap bitmap, long destinationOffset, int packedStride)
    {
        var rect = new Rectangle(0, 0, bitmap.Width, bitmap.Height);
        var data = bitmap.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            var row = new byte[packedStride];
            for (var y = 0; y < bitmap.Height; y++)
            {
                var sourceY = data.Stride >= 0 ? y : bitmap.Height - 1 - y;
                var source = IntPtr.Add(data.Scan0, sourceY * Math.Abs(data.Stride));
                Marshal.Copy(source, row, 0, packedStride);
                _view.WriteArray(destinationOffset + (long)y * packedStride, row, 0, packedStride);
            }
        }
        finally
        {
            bitmap.UnlockBits(data);
        }
    }

    private static Bitmap PrepareBitmap(Bitmap source, int? targetWidth = null, int? targetHeight = null)
    {
        var width = targetWidth ?? source.Width;
        var height = targetHeight ?? source.Height;
        if (source.Width != width || source.Height != height)
        {
            return ResizeBitmap(source, width, height);
        }

        var result = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(result);
        graphics.DrawImageUnscaled(source, 0, 0);
        return result;
    }

    private static Bitmap ResizeBitmap(Image source, int width, int height)
    {
        var result = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(result);
        graphics.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceCopy;
        graphics.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighQuality;
        graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
        graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality;
        graphics.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
        graphics.DrawImage(source, new Rectangle(0, 0, width, height));
        return result;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try
        {
            _view.Write(16, 0);
            _view.Flush();
        }
        catch
        {
        }
        _view.Dispose();
        _mapping.Dispose();
    }
}
