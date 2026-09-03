namespace GeoGebraForQuest.PC;

internal sealed partial class MainForm
{
    private long _physicalMouseOwnsUntilMs;
    private long _xrOwnsUntilMs;
    private Point _lastPhysicalMousePoint = new(-10000, -10000);
    private bool _hasPhysicalMousePoint;
    private float _lastAcceptedXrU;
    private float _lastAcceptedXrV;
    private bool _lastAcceptedXrTrigger;
    private bool _hasAcceptedXrPoint;

    private void MarkPhysicalMouseActivity(Point p, bool force = false)
    {
        var moved = !_hasPhysicalMousePoint ||
                    Math.Abs(p.X - _lastPhysicalMousePoint.X) >= 2 ||
                    Math.Abs(p.Y - _lastPhysicalMousePoint.Y) >= 2;
        _lastPhysicalMousePoint = p;
        _hasPhysicalMousePoint = true;
        if (!force && !moved) return;
        _physicalMouseOwnsUntilMs = Environment.TickCount64 + 1200;
    }

    private bool ShouldRouteXrPointer(float u, float v, bool triggerDown)
    {
        var now = Environment.TickCount64;
        var triggerChanged = triggerDown != _lastAcceptedXrTrigger;
        var moved = !_hasAcceptedXrPoint ||
                    Math.Abs(u - _lastAcceptedXrU) >= 0.0006f ||
                    Math.Abs(v - _lastAcceptedXrV) >= 0.0006f;

        // Trigger edges always win. Ordinary XR hover waits until a real mouse gesture
        // has finished, so two independent devices cannot drag the same CEF cursor.
        if (!triggerChanged && now < _physicalMouseOwnsUntilMs) return false;
        if (!moved && !triggerChanged) return false;

        _xrOwnsUntilMs = now + 1200;
        _lastAcceptedXrU = u;
        _lastAcceptedXrV = v;
        _lastAcceptedXrTrigger = triggerDown;
        _hasAcceptedXrPoint = true;
        return true;
    }

    private bool PhysicalMouseMayRoute() => Environment.TickCount64 >= _xrOwnsUntilMs;

    private void ResetXrPointerRouting()
    {
        _hasAcceptedXrPoint = false;
        _lastAcceptedXrTrigger = false;
    }
}
