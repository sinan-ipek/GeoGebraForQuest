using System.Drawing.Drawing2D;

namespace GeoGebraForQuest.PC;

internal sealed class StereoPanelControl : Control
{
    private readonly object _imageLock = new();
    private Bitmap? _left;
    private Bitmap? _right;
    private string _message = "Stereo Panel (B) · 3D grafik bekleniyor";

    public StereoPanelControl()
    {
        DoubleBuffered = true;
        BackColor = Color.White;
        ForeColor = Color.FromArgb(32, 33, 36);
        MinimumSize = new Size(320, 240);
    }

    public void SetMessage(string message)
    {
        _message = message;
        Invalidate();
    }

    public void ClearFrames(string message)
    {
        lock (_imageLock)
        {
            _left?.Dispose();
            _right?.Dispose();
            _left = null;
            _right = null;
        }
        _message = message;
        Invalidate();
    }

    public void SetFrames(Bitmap left, Bitmap right, long frameNumber)
    {
        lock (_imageLock)
        {
            _left?.Dispose();
            _right?.Dispose();
            _left = left;
            _right = right;
        }

        _message = $"Stereo Panel (B) · frame {frameNumber} · {left.Width}×{left.Height} / eye";
        Invalidate();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            lock (_imageLock)
            {
                _left?.Dispose();
                _right?.Dispose();
                _left = null;
                _right = null;
            }
        }
        base.Dispose(disposing);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = SmoothingMode.HighQuality;
        e.Graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
        e.Graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;

        using var borderPen = new Pen(Color.FromArgb(210, 214, 220), 1f);
        using var titleBrush = new SolidBrush(Color.FromArgb(32, 33, 36));
        using var mutedBrush = new SolidBrush(Color.FromArgb(95, 99, 104));
        using var panelBrush = new SolidBrush(Color.FromArgb(248, 249, 250));
        using var eyeLabelBrush = new SolidBrush(Color.FromArgb(255, 255, 255, 225));
        using var eyeLabelBack = new SolidBrush(Color.FromArgb(110, 0, 0, 0));
        using var titleFont = new Font(Font.FontFamily, 10.5f, FontStyle.Bold);
        using var smallFont = new Font(Font.FontFamily, 8.5f, FontStyle.Regular);

        var titleHeight = 48;
        e.Graphics.FillRectangle(panelBrush, 0, 0, Width, titleHeight);
        e.Graphics.DrawLine(borderPen, 0, titleHeight - 1, Width, titleHeight - 1);
        e.Graphics.DrawString("Stereo Panel (B)", titleFont, titleBrush, new PointF(12, 7));
        e.Graphics.DrawString(_message, smallFont, mutedBrush, new PointF(12, 27));

        Bitmap? left;
        Bitmap? right;
        lock (_imageLock)
        {
            left = _left;
            right = _right;
        }

        var content = new Rectangle(8, titleHeight + 8, Math.Max(1, Width - 16), Math.Max(1, Height - titleHeight - 16));
        e.Graphics.DrawRectangle(borderPen, content);

        if (left is null || right is null)
        {
            var text = "3D grafik açıldığında\nsol ve sağ göz kareleri burada SBS önizlenecek.";
            var size = e.Graphics.MeasureString(text, Font);
            e.Graphics.DrawString(
                text,
                Font,
                mutedBrush,
                content.Left + (content.Width - size.Width) / 2f,
                content.Top + (content.Height - size.Height) / 2f);
            return;
        }

        var gap = 4;
        var halfWidth = Math.Max(1, (content.Width - gap) / 2);
        var leftArea = new Rectangle(content.Left, content.Top, halfWidth, content.Height);
        var rightArea = new Rectangle(content.Left + halfWidth + gap, content.Top, content.Width - halfWidth - gap, content.Height);

        DrawContained(e.Graphics, left, leftArea);
        DrawContained(e.Graphics, right, rightArea);

        DrawEyeLabel(e.Graphics, "L", leftArea, smallFont, eyeLabelBrush, eyeLabelBack);
        DrawEyeLabel(e.Graphics, "R", rightArea, smallFont, eyeLabelBrush, eyeLabelBack);
    }

    private static void DrawContained(Graphics graphics, Image image, Rectangle area)
    {
        var scale = Math.Min(area.Width / (double)image.Width, area.Height / (double)image.Height);
        var width = Math.Max(1, (int)Math.Round(image.Width * scale));
        var height = Math.Max(1, (int)Math.Round(image.Height * scale));
        var target = new Rectangle(
            area.Left + (area.Width - width) / 2,
            area.Top + (area.Height - height) / 2,
            width,
            height);
        graphics.DrawImage(image, target);
    }

    private static void DrawEyeLabel(
        Graphics graphics,
        string text,
        Rectangle area,
        Font font,
        Brush textBrush,
        Brush backgroundBrush)
    {
        var label = new Rectangle(area.Left + 8, area.Top + 8, 24, 20);
        graphics.FillRectangle(backgroundBrush, label);
        graphics.DrawString(text, font, textBrush, label.Left + 7, label.Top + 2);
    }
}
