using System.Drawing.Drawing2D;

namespace GeoGebraForQuest.PC;

internal sealed class StereoPanelControl : Control
{
    private readonly object _imageLock = new();
    private Bitmap? _left;
    private Bitmap? _right;
    private string _message = "3D grafik bekleniyor";

    public bool ShowSbsPreview { get; set; }

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

        _message = $"frame {frameNumber} · {left.Width}×{left.Height} / göz";
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
        using var badgeBrush = new SolidBrush(Color.FromArgb(205, 0, 0, 0));
        using var badgeTextBrush = new SolidBrush(Color.White);
        using var titleFont = new Font(Font.FontFamily, 10.5f, FontStyle.Bold);
        using var smallFont = new Font(Font.FontFamily, 8.5f, FontStyle.Regular);

        const int titleHeight = 50;
        e.Graphics.FillRectangle(panelBrush, 0, 0, Width, titleHeight);
        e.Graphics.DrawLine(borderPen, 0, titleHeight - 1, Width, titleHeight - 1);
        e.Graphics.DrawString("Stereo Panel (B)", titleFont, titleBrush, new PointF(12, 7));
        e.Graphics.DrawString(
            ShowSbsPreview ? _message + " · PC SBS önizleme" : _message + " · PC mono / Quest stereo",
            smallFont,
            mutedBrush,
            new PointF(12, 28));

        Bitmap? left;
        Bitmap? right;
        lock (_imageLock)
        {
            left = _left;
            right = _right;
        }

        var content = new Rectangle(
            8,
            titleHeight + 8,
            Math.Max(1, Width - 16),
            Math.Max(1, Height - titleHeight - 16));

        e.Graphics.DrawRectangle(borderPen, content);

        if (left is null || right is null)
        {
            const string waiting = "3D grafik açıldığında Stereo Panel burada görünecek.\n" +
                                   "Quest bağlıysa L/R kareler gözlere ayrı gönderilecek.";
            var size = e.Graphics.MeasureString(waiting, Font);
            e.Graphics.DrawString(
                waiting,
                Font,
                mutedBrush,
                content.Left + (content.Width - size.Width) / 2f,
                content.Top + (content.Height - size.Height) / 2f);
            return;
        }

        if (!ShowSbsPreview)
        {
            DrawContained(e.Graphics, left, content);
            DrawBadge(e.Graphics, "PC mono", content, smallFont, badgeBrush, badgeTextBrush);
            return;
        }

        const int gap = 4;
        var halfWidth = Math.Max(1, (content.Width - gap) / 2);
        var leftArea = new Rectangle(content.Left, content.Top, halfWidth, content.Height);
        var rightArea = new Rectangle(
            content.Left + halfWidth + gap,
            content.Top,
            content.Width - halfWidth - gap,
            content.Height);

        DrawContained(e.Graphics, left, leftArea);
        DrawContained(e.Graphics, right, rightArea);
        DrawBadge(e.Graphics, "L", leftArea, smallFont, badgeBrush, badgeTextBrush);
        DrawBadge(e.Graphics, "R", rightArea, smallFont, badgeBrush, badgeTextBrush);
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

    private static void DrawBadge(
        Graphics graphics,
        string text,
        Rectangle area,
        Font font,
        Brush background,
        Brush foreground)
    {
        var measured = graphics.MeasureString(text, font);
        var badge = new RectangleF(
            area.Left + 8,
            area.Top + 8,
            measured.Width + 12,
            measured.Height + 5);
        graphics.FillRectangle(background, badge);
        graphics.DrawString(text, font, foreground, badge.Left + 6, badge.Top + 2);
    }
}
