namespace GeoGebraForQuest.PC;

// MainForm configures large minimum widths in its field initializer. The stock
// WinForms SplitContainer starts with a very small design-time size, so setting
// Panel1MinSize=640 and Panel2MinSize=320 can throw before the form is ever
// shown. Give the control a valid pre-layout size first; once it is parented,
// DockStyle.Fill and the form's normal layout take over exactly as before.
internal sealed class SplitContainer : System.Windows.Forms.SplitContainer
{
    public SplitContainer()
    {
        Width = 1200;
        Height = 720;
        SplitterWidth = 6;
        SplitterDistance = 840;
    }
}
