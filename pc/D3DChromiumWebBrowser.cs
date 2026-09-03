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
                WindowlessFrameRate = 90,
                DefaultEncoding = "UTF-8",
                Javascript = CefState.Enabled,
                WebGl = CefState.Enabled,
                LocalStorage = CefState.Enabled
            });
    }
}
