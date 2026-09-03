namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private long _physicalMouseOwnsUntilMs;
    private float _lastAcceptedXrU;
    private float _lastAcceptedXrV;
    private bool _lastAcceptedXrTrigger;
    private bool _hasAcceptedXrPoint;

    private void MarkPhysicalMouseActivity()
    {
        // A real mouse movement/click temporarily owns the CEF pointer. This prevents
        // the continuously-valid XR ray from immediately moving the browser cursor
        // back underneath the physical mouse.
        _physicalMouseOwnsUntilMs = Environment.TickCount64 + 240;
    }

    private bool ShouldRouteXrPointer(float u, float v, bool triggerDown)
    {
        var now = Environment.TickCount64;
        var triggerChanged = triggerDown != _lastAcceptedXrTrigger;
        var moved = !_hasAcceptedXrPoint ||
                    Math.Abs(u - _lastAcceptedXrU) >= 0.0008f ||
                    Math.Abs(v - _lastAcceptedXrV) >= 0.0008f;

        // Trigger edges must never be swallowed. Otherwise let the physical mouse
        // finish its current interaction before XR takes ownership again.
        if (!triggerChanged && now < _physicalMouseOwnsUntilMs)
            return false;
        if (!moved && !triggerChanged)
            return false;

        _lastAcceptedXrU = u;
        _lastAcceptedXrV = v;
        _lastAcceptedXrTrigger = triggerDown;
        _hasAcceptedXrPoint = true;
        return true;
    }

    private void ResetXrPointerRouting()
    {
        _hasAcceptedXrPoint = false;
        _lastAcceptedXrTrigger = false;
    }
}
