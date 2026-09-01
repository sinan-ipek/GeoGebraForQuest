using System.Drawing.Imaging;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;

namespace GeoGebraForQuest.PC;

internal sealed class StereoSharedFrameWriter : IDisposable
{
    public const string MappingName = @"Local\GeoGebraForQuestPC_SBS_v2";

    private const int Magic = 0x47515342; // "BSQG" little-endian validation marker.
    private const int ProtocolVersion = 2;
    private const long HeaderSize = 128;
    private const int MaxEyeWidth = 2048;
    private const int MaxEyeHeight = 2048;
    private const long MaxSbsBytes = (long)MaxEyeWidth * 2 * MaxEyeHeight * 4;
    private const long Capacity = HeaderSize + MaxSbsBytes;
    private const long SbsOffset = HeaderSize;

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
        if (_disposed ||
            applicationClientSize.Width < 1 ||
            applicationClientSize.Height < 1 ||
            stereoPanelClientBounds.Width < 2 ||
            stereoPanelClientBounds.Height < 2)
        {
            return;
        }

        lock (_sync)
        {
            using var leftPrepared = PrepareBitmap(leftSource);
            using var rightPrepared = PrepareBitmap(
                rightSource,
                leftPrepared.Width,
                leftPrepared.Height);

            Bitmap finalLeft = leftPrepared;
            Bitmap finalRight = rightPrepared;
            Bitmap? resizedLeft = null;
            Bitmap? resizedRight = null;

            try
            {
                if (finalLeft.Width > MaxEyeWidth || finalLeft.Height > MaxEyeHeight)
                {
                    var scale = Math.Min(
                        MaxEyeWidth / (double)finalLeft.Width,
                        MaxEyeHeight / (double)finalLeft.Height);
                    var width = Math.Max(2, (int)Math.Round(finalLeft.Width * scale));
                    var height = Math.Max(2, (int)Math.Round(finalLeft.Height * scale));

                    resizedLeft = ResizeBitmap(finalLeft, width, height);
                    resizedRight = ResizeBitmap(finalRight, width, height);
                    finalLeft = resizedLeft;
                    finalRight = resizedRight;
                }

                var eyeWidth = finalLeft.Width;
                var eyeHeight = finalLeft.Height;
                var eyeStride = checked(eyeWidth * 4);
                var sbsStride = checked(eyeWidth * 2 * 4);

                var evenSequence = Interlocked.Add(ref _sequence, 2);
                var oddSequence = evenSequence - 1;

                // Seqlock: odd while the SBS image is being replaced,
                // even only after header + complete [L|R] bitmap are ready.
                _view.Write(8, oddSequence);
                _view.Write(16, 1); // active
                _view.Write(20, applicationClientSize.Width);
                _view.Write(24, applicationClientSize.Height);
                _view.Write(28, stereoPanelClientBounds.Left);
                _view.Write(32, stereoPanelClientBounds.Top);
                _view.Write(36, stereoPanelClientBounds.Width);
                _view.Write(40, stereoPanelClientBounds.Height);
                _view.Write(44, eyeWidth);
                _view.Write(48, eyeHeight);
                _view.Write(52, sbsStride);
                _view.Write(56, unchecked((int)frameNumber));
                _view.Write(60, Environment.ProcessId);

                WriteSbsBitmap(finalLeft, finalRight, SbsOffset, eyeStride, sbsStride);

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
            _view.Write(44, 0);
            _view.Write(48, 0);
            _view.Write(52, 0);
            _view.Write(60, Environment.ProcessId);

            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
            _view.Flush();
        }
    }

    private void WriteSbsBitmap(
        Bitmap left,
        Bitmap right,
        long destinationOffset,
        int eyeStride,
        int sbsStride)
    {
        var leftRect = new Rectangle(0, 0, left.Width, left.Height);
        var rightRect = new Rectangle(0, 0, right.Width, right.Height);

        var leftData = left.LockBits(
            leftRect,
            ImageLockMode.ReadOnly,
            PixelFormat.Format32bppArgb);
        var rightData = right.LockBits(
            rightRect,
            ImageLockMode.ReadOnly,
            PixelFormat.Format32bppArgb);

        try
        {
            var row = new byte[sbsStride];

            for (var y = 0; y < left.Height; y++)
            {
                var leftY = leftData.Stride >= 0 ? y : left.Height - 1 - y;
                var rightY = rightData.Stride >= 0 ? y : right.Height - 1 - y;

                var leftPtr = IntPtr.Add(
                    leftData.Scan0,
                    leftY * Math.Abs(leftData.Stride));
                var rightPtr = IntPtr.Add(
                    rightData.Scan0,
                    rightY * Math.Abs(rightData.Stride));

                Marshal.Copy(leftPtr, row, 0, eyeStride);
                Marshal.Copy(rightPtr, row, eyeStride, eyeStride);

                _view.WriteArray(
                    destinationOffset + (long)y * sbsStride,
                    row,
                    0,
                    sbsStride);
            }
        }
        finally
        {
            left.UnlockBits(leftData);
            right.UnlockBits(rightData);
        }
    }

    private static Bitmap PrepareBitmap(
        Bitmap source,
        int? targetWidth = null,
        int? targetHeight = null)
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
