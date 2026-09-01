using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace GeoGebraForQuest.PC;

internal sealed class PopupForm : Form
{
    private readonly CoreWebView2Environment _environment;
    private readonly Action<CoreWebView2> _configure;

    public WebView2 WebView { get; } = new() { Dock = DockStyle.Fill };

    public PopupForm(CoreWebView2Environment environment, Action<CoreWebView2> configure)
    {
        _environment = environment;
        _configure = configure;

        Text = "GeoGebra · Giriş / Online İçerik";
        StartPosition = FormStartPosition.CenterParent;
        Width = 1100;
        Height = 780;
        MinimumSize = new Size(760, 560);
        Controls.Add(WebView);
    }

    public async Task InitializeAsync()
    {
        await WebView.EnsureCoreWebView2Async(_environment);
        _configure(WebView.CoreWebView2);
        WebView.CoreWebView2.WindowCloseRequested += (_, _) => Close();
    }
}
