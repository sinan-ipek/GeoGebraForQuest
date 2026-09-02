using CefSharp;
using CefSharp.OffScreen;

namespace GeoGebraForQuest.PC;

internal sealed class D3DChromiumWebBrowser : ChromiumWebBrowser
{
    public D3DChromiumWebBrowser(
        IRequestContext requestContext,
        IRenderHandler renderHandler,
        int initialWidth,
        int initialHeight)
        : base("about:blank", null, requestContext, automaticallyCreateBrowser: false)
    {
        RenderHandler = renderHandler;

        var windowInfo = new WindowInfo();
        windowInfo.SetAsWindowless(IntPtr.Zero);
        windowInfo.WindowlessRenderingEnabled = true;
        windowInfo.SharedTextureEnabled = true;
        windowInfo.Width = Math.Max(2, initialWidth);
        windowInfo.Height = Math.Max(2, initialHeight);

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
