using CefSharp;
using CefSharp.OffScreen;

namespace GeoGebraForQuest.PC;

internal sealed class D3DChromiumWebBrowser : ChromiumWebBrowser
{
    public D3DChromiumWebBrowser(IRequestContext requestContext)
        : base("about:blank", null, requestContext, automaticallyCreateBrowser: false)
    {
        var windowInfo = new WindowInfo();
        windowInfo.SetAsWindowless(IntPtr.Zero);
        windowInfo.WindowlessRenderingEnabled = true;
        windowInfo.ExternalBeginFrameEnabled = true;
        windowInfo.SharedTextureEnabled = true;

        CreateBrowser(
            windowInfo,
            new BrowserSettings
            {
                WindowlessFrameRate = 90,
                Javascript = CefState.Enabled,
                WebGl = CefState.Enabled,
                LocalStorage = CefState.Enabled
            });
    }
}
