using CefSharp;
using CefSharp.OffScreen;

namespace GeoGebraForQuest.PC;

internal sealed class D3DChromiumWebBrowser : ChromiumWebBrowser
{
    private readonly int _initialWidth;
    private readonly int _initialHeight;
    private bool _created;

    public D3DChromiumWebBrowser(
        string initialAddress,
        IRequestContext requestContext,
        IRenderHandler renderHandler,
        int initialWidth,
        int initialHeight)
        : base(initialAddress, null, requestContext, automaticallyCreateBrowser: false)
    {
        RenderHandler = renderHandler;
        _initialWidth = Math.Max(2, initialWidth);
        _initialHeight = Math.Max(2, initialHeight);
    }

    public void CreateGpuBrowser()
    {
        if (_created) return;
        _created = true;

        var windowInfo = new WindowInfo();
        windowInfo.SetAsWindowless(IntPtr.Zero);
        windowInfo.WindowlessRenderingEnabled = true;
        windowInfo.SharedTextureEnabled = true;
        windowInfo.Width = _initialWidth;
        windowInfo.Height = _initialHeight;

        CreateBrowser(
            windowInfo,
            new BrowserSettings
            {
                // 90 fps forced CEF to spend GPU time repainting A even while the
                // stereo transport was also producing eye pairs. 60 fps keeps normal
                // GeoGebra interaction fluid and leaves headroom for OpenXR + B.
                WindowlessFrameRate = 60,
                DefaultEncoding = "UTF-8",
                Javascript = CefState.Enabled,
                WebGl = CefState.Enabled,
                LocalStorage = CefState.Enabled
            });
    }
}
