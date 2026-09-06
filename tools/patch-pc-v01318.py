from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.18
# 1) Keep B stereo geometry fixed and restore dynamic GeoGebra UI rectangles
#    (3D stylebar / menus) from A on top of B.
# 2) Replace the hand-drawn XR UI cursor with the actual Windows IDC_ARROW image
#    and its real hotspot (with the previous pointed triangle as fallback).
# 3) Make the native XR stereo splash actually appear when XR first becomes
#    renderable / wakes: initialize COM for WIC and start the timer on visibility,
#    not during early process initialization.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# JS: fixed B geometry + dynamic UI overlay rectangles.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
t = p.read_text(encoding='utf-8')

insert_marker = '  function findVisible3DCanvas() {'
require(t, insert_marker, 'v0.13.18: findVisible3DCanvas marker missing')

ui_helpers = r'''
  // Return up to three visible GeoGebra UI rectangles that sit ABOVE the 3D
  // canvas. These are not used to resize B. XR redraws the corresponding A
  // texture pieces on top of the fixed stereo image instead.
  function collectUiOverlayRects(canvas, panelRect) {
    if (!canvas || !panelRect) return [];

    var panelArea = Math.max(1, rectArea(panelRect));
    var elements = [];

    function remember(element) {
      if (!element || elements.indexOf(element) >= 0) return;
      if (element === canvas ||
          (element.contains && element.contains(canvas)) ||
          (canvas.contains && canvas.contains(element))) return;
      var tag = String(element.tagName || '').toLowerCase();
      if (tag === 'html' || tag === 'body') return;

      var er = rawRectOf(element);
      var clipped = er && intersectRect(er, panelRect);
      if (!clipped || rectArea(clipped) < 20) return;

      var role = String(element.getAttribute && element.getAttribute('role') || '').toLowerCase();
      var label = String(
        (element.getAttribute && (element.getAttribute('aria-label') || element.getAttribute('title'))) || ''
      ).toLowerCase();
      var text = classAndIdText(element) + ' ' + label;
      var style;
      try { style = getComputedStyle(element); } catch (_) { style = null; }
      var z = style ? parseInt(style.zIndex, 10) : NaN;
      var positioned = style &&
        (style.position === 'fixed' || style.position === 'absolute' || style.position === 'sticky');
      var buttonish = tag === 'button' || role === 'button' || role === 'toolbar';
      var namedUi = /(toolbar|stylebar|style-bar|menu|popup|dialog|dropdown|settings|undo|redo|zoom|viewcontrol)/.test(text);

      if (!(isMenuLike(element) || buttonish || namedUi ||
            ((positioned || (isFinite(z) && z > 5)) && hasPaint(element)))) {
        return;
      }

      // Avoid accidentally selecting the whole Euclidian/3D container.
      if (!isMenuLike(element) && rectArea(clipped) > panelArea * 0.72) return;
      elements.push(element);
    }

    function elementAboveCanvasAt(x, y) {
      var stack;
      try { stack = document.elementsFromPoint(x, y); } catch (_) { return; }
      if (!stack || !stack.length) return;
      var canvasIndex = canvasIndexInStack(stack, canvas);
      var limit = canvasIndex >= 0 ? canvasIndex : Math.min(stack.length, 8);
      for (var i = 0; i < limit; i++) {
        var element = stack[i];
        if (!element || element === canvas) continue;
        remember(element);
      }
    }

    // Known menu/dialog/toolbar families. GeoGebra/GWT changes class names across
    // layouts, therefore these are deliberately broad and are filtered by actual
    // visibility + intersection with the 3D canvas.
    var selectors = [
      '[role="dialog"]', '[aria-modal="true"]', '[role="menu"]',
      '[role="listbox"]', '[role="toolbar"]',
      '.gwt-PopupPanel', '.gwt-DialogBox',
      '[class*="Popup"]', '[class*="popup"]',
      '[class*="Dialog"]', '[class*="dialog"]',
      '[class*="Dropdown"]', '[class*="dropdown"]',
      '[class*="Menu"]', '[class*="menu"]',
      '[class*="Toolbar"]', '[class*="toolbar"]',
      '[class*="StyleBar"]', '[class*="stylebar"]'
    ].join(',');
    try {
      var known = document.querySelectorAll(selectors);
      for (var k = 0; k < known.length; k++) remember(known[k]);
    } catch (_) {}

    // The small 3D stylebar is often made of several button DIVs rather than one
    // semantic toolbar. Sample its top/right region and merge the button rectangles.
    var xs = [0.55, 0.65, 0.75, 0.84, 0.92, 0.985];
    var ys = [0.025, 0.075, 0.14];
    for (var yi = 0; yi < ys.length; yi++) {
      for (var xi = 0; xi < xs.length; xi++) {
        elementAboveCanvasAt(
          panelRect.left + panelRect.width * xs[xi],
          panelRect.top + panelRect.height * ys[yi]
        );
      }
    }
    var rightYs = [0.08, 0.24, 0.42, 0.60, 0.78, 0.94];
    for (var ry = 0; ry < rightYs.length; ry++) {
      elementAboveCanvasAt(
        panelRect.left + panelRect.width * 0.985,
        panelRect.top + panelRect.height * rightYs[ry]
      );
    }

    var rects = [];
    function pushRect(element) {
      var er = rawRectOf(element);
      var r = er && intersectRect(er, panelRect);
      if (!r) return;
      var pad = 5;
      r = intersectRect({
        left: r.left - pad,
        top: r.top - pad,
        width: r.width + pad * 2,
        height: r.height + pad * 2
      }, panelRect);
      if (r && rectArea(r) >= 25) rects.push(r);
    }
    for (var e = 0; e < elements.length; e++) pushRect(elements[e]);

    function near(a, b, gap) {
      return !(
        a.left + a.width + gap < b.left ||
        b.left + b.width + gap < a.left ||
        a.top + a.height + gap < b.top ||
        b.top + b.height + gap < a.top
      );
    }
    function unionRect(a, b) {
      var left = Math.min(a.left, b.left);
      var top = Math.min(a.top, b.top);
      var right = Math.max(a.left + a.width, b.left + b.width);
      var bottom = Math.max(a.top + a.height, b.top + b.height);
      return { left: left, top: top, width: right - left, height: bottom - top };
    }

    // Merge neighbouring buttons into one dynamic toolbar patch.
    var changed = true;
    while (changed) {
      changed = false;
      outer:
      for (var a = 0; a < rects.length; a++) {
        for (var b = a + 1; b < rects.length; b++) {
          if (near(rects[a], rects[b], 12)) {
            rects[a] = unionRect(rects[a], rects[b]);
            rects.splice(b, 1);
            changed = true;
            break outer;
          }
        }
      }
    }

    rects = rects.map(function (r) { return intersectRect(r, panelRect); })
      .filter(function (r) { return !!r && rectArea(r) >= 25; });
    rects.sort(function (a, b) { return rectArea(b) - rectArea(a); });
    return rects.slice(0, 3);
  }

'''

t = t.replace(insert_marker, ui_helpers + insert_marker, 1)

refresh_pattern = re.compile(
    r'  function refreshGeometry\(\) \{.*?\n  \}\n\n  function scheduleGeometry\(\) \{',
    re.S)
m = refresh_pattern.search(t)
if not m:
    raise SystemExit('v0.13.18: refreshGeometry block missing')

new_refresh = r'''  function refreshGeometry() {
    geometryScheduled = false;

    var canvas = find3DCanvas();
    var rect = clippedRectOf(canvas);
    if (!canvas || !rect) {
      reportInactive('no-3d');
      return;
    }

    // v0.13.18: B geometry is ALWAYS the actual 3D canvas rectangle. Menus,
    // stylebars and side panels no longer shrink/disable B; they are sent as A
    // overlay rectangles and redrawn by XR on top of B.
    var visibleRect = rect;
    if (visibleRect.width < 20 || visibleRect.height < 20) {
      reportInactive('3d-too-small');
      return;
    }

    var uiOverlays = collectUiOverlayRects(canvas, visibleRect);
    geometryState = {
      canvas: canvas,
      rect: visibleRect,
      uiOverlays: uiOverlays
    };
    reportActive();

    var payload = JSON.stringify({
      active: true,
      stereo: visibleRect,
      uiOverlays: uiOverlays,
      viewWidth: innerWidth,
      viewHeight: innerHeight
    });

    if (payload !== lastPayload) {
      lastPayload = payload;
      bridge('updateStereoLayout', payload);
    }
  }

  function scheduleGeometry() {'''

t = t[:m.start()] + new_refresh + t[m.end():]
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# C# MainForm: keep scaled UI overlay rectangles with the stereo geometry.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
t = p.read_text(encoding='utf-8')
field_marker = '    private Rectangle _stereo3DRenderBounds = Rectangle.Empty;\n'
require(t, field_marker, 'v0.13.18: stereo bounds field missing')
t = t.replace(
    field_marker,
    field_marker + '    private Rectangle[] _stereoUiOverlayBounds = Array.Empty<Rectangle>();\n',
    1)

method_pattern = re.compile(
    r'    private void HandleStereoLayout\(string\? payload\)\n    \{.*?\n    \}\n\n    private void XrStatusChanged',
    re.S)
mm = method_pattern.search(t)
if not mm:
    raise SystemExit('v0.13.18: HandleStereoLayout method missing')

new_method = r'''    private void HandleStereoLayout(string? payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            var active = root.TryGetProperty("active", out var activeNode) &&
                         activeNode.GetBoolean();
            if (!active || !root.TryGetProperty("stereo", out var stereo))
            {
                SetStereoInactive();
                return;
            }

            var viewWidth = root.TryGetProperty("viewWidth", out var vw) ? vw.GetDouble() : 0;
            var viewHeight = root.TryGetProperty("viewHeight", out var vh) ? vh.GetDouble() : 0;
            if (viewWidth < 2 || viewHeight < 2) return;

            var left = stereo.GetProperty("left").GetDouble();
            var top = stereo.GetProperty("top").GetDouble();
            var width = stereo.GetProperty("width").GetDouble();
            var height = stereo.GetProperty("height").GetDouble();
            if (width < 2 || height < 2) return;

            Size renderSize;
            lock (_geometryLock) renderSize = _browserSize;
            var sx = renderSize.Width / viewWidth;
            var sy = renderSize.Height / viewHeight;

            var rect = new Rectangle(
                (int)Math.Round(left * sx),
                (int)Math.Round(top * sy),
                Math.Max(2, (int)Math.Round(width * sx)),
                Math.Max(2, (int)Math.Round(height * sy)));
            rect = Rectangle.Intersect(
                rect,
                new Rectangle(0, 0, renderSize.Width, renderSize.Height));
            if (rect.Width < 2 || rect.Height < 2) return;

            var overlays = new List<Rectangle>(3);
            if (root.TryGetProperty("uiOverlays", out var overlayArray) &&
                overlayArray.ValueKind == JsonValueKind.Array)
            {
                foreach (var overlay in overlayArray.EnumerateArray())
                {
                    if (overlays.Count >= 3 || overlay.ValueKind != JsonValueKind.Object) break;
                    if (!overlay.TryGetProperty("left", out var ol) ||
                        !overlay.TryGetProperty("top", out var ot) ||
                        !overlay.TryGetProperty("width", out var ow) ||
                        !overlay.TryGetProperty("height", out var oh)) continue;

                    var candidate = new Rectangle(
                        (int)Math.Round(ol.GetDouble() * sx),
                        (int)Math.Round(ot.GetDouble() * sy),
                        Math.Max(1, (int)Math.Round(ow.GetDouble() * sx)),
                        Math.Max(1, (int)Math.Round(oh.GetDouble() * sy)));
                    candidate = Rectangle.Intersect(candidate, rect);
                    if (candidate.Width >= 2 && candidate.Height >= 2)
                        overlays.Add(candidate);
                }
            }

            lock (_geometryLock)
            {
                _stereo3DRenderBounds = rect;
                _stereoUiOverlayBounds = overlays.ToArray();
                _stereo3DActive = true;
            }
        }
        catch (Exception ex)
        {
            _cefPageText = "CEF 3D rect: " + ex.Message;
            BeginInvokeSafe(UpdateWindowTitle);
        }
    }

    private void XrStatusChanged'''

t = t[:mm.start()] + new_method + t[mm.end():]
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# C# stereo pipeline: carry immutable overlay rectangles into SBS shared header.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.InputStereo.cs')
t = p.read_text(encoding='utf-8')

old_geom = '''                    bool active;
                    Rectangle rect;
                    Size size;
                    lock (_geometryLock)
                    {
                        active = _stereo3DActive;
                        rect = _stereo3DRenderBounds;
                        size = _browserSize;
                    }'''
new_geom = '''                    bool active;
                    Rectangle rect;
                    Rectangle[] overlays;
                    Size size;
                    lock (_geometryLock)
                    {
                        active = _stereo3DActive;
                        rect = _stereo3DRenderBounds;
                        overlays = _stereoUiOverlayBounds;
                        size = _browserSize;
                    }'''
require(t, old_geom, 'v0.13.18: DecodeStereoLoop geometry snapshot missing')
t = t.replace(old_geom, new_geom, 1)

old_write = '_sharedStereoFrames.WriteFrames(left, right, rect, size, frame);'
new_write = '_sharedStereoFrames.WriteFrames(left, right, rect, size, overlays, frame);'
require(t, old_write, 'v0.13.18: WriteFrames call missing')
t = t.replace(old_write, new_write, 1)

inactive_marker = '''            size = _browserSize;
            _stereo3DActive = false;'''
require(t, inactive_marker, 'v0.13.18: SetStereoInactive marker missing')
t = t.replace(
    inactive_marker,
    '''            size = _browserSize;
            _stereo3DActive = false;
            _stereoUiOverlayBounds = Array.Empty<Rectangle>();''',
    1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# SBS shared-memory header: bytes 64..127 were reserved. Use them for up to 3
# UI rectangles without enlarging the mapping or moving the pixel payload.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
t = p.read_text(encoding='utf-8')
require(t, '    private const long HeaderSize = 128;\n', 'v0.13.18: SBS header marker missing')
t = t.replace(
    '    private const long HeaderSize = 128;\n',
    '    private const long HeaderSize = 128;\n    private const int MaxUiOverlayRects = 3;\n',
    1)

constructor_marker = '        _view.Write(60, Environment.ProcessId);\n        _view.Flush();'
require(t, constructor_marker, 'v0.13.18: SBS constructor pid marker missing')
t = t.replace(
    constructor_marker,
    '        _view.Write(60, Environment.ProcessId);\n        _view.Write(64, 0);\n        _view.Flush();',
    1)

old_sig = '''        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        long frameNumber)'''
new_sig = '''        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        IReadOnlyList<Rectangle>? uiOverlayClientBounds,
        long frameNumber)'''
require(t, old_sig, 'v0.13.18: WriteFrames signature missing')
t = t.replace(old_sig, new_sig, 1)

header_marker = '''                _view.Write(56, unchecked((int)frameNumber));
                _view.Write(60, Environment.ProcessId);

                WriteSbsBitmap'''
require(t, header_marker, 'v0.13.18: SBS frame header marker missing')
header_new = '''                _view.Write(56, unchecked((int)frameNumber));
                _view.Write(60, Environment.ProcessId);

                var overlayCount = Math.Min(
                    MaxUiOverlayRects,
                    uiOverlayClientBounds?.Count ?? 0);
                _view.Write(64, overlayCount);
                for (var i = 0; i < MaxUiOverlayRects; i++)
                {
                    var offset = 68 + i * 16;
                    var r = i < overlayCount
                        ? uiOverlayClientBounds![i]
                        : Rectangle.Empty;
                    _view.Write(offset + 0, r.Left);
                    _view.Write(offset + 4, r.Top);
                    _view.Write(offset + 8, r.Width);
                    _view.Write(offset + 12, r.Height);
                }

                WriteSbsBitmap'''
t = t.replace(header_marker, header_new, 1)

inactive_header = '            _view.Write(60, Environment.ProcessId);\n\n            Thread.MemoryBarrier();'
require(t, inactive_header, 'v0.13.18: SBS inactive header marker missing')
t = t.replace(
    inactive_header,
    '            _view.Write(60, Environment.ProcessId);\n            _view.Write(64, 0);\n\n            Thread.MemoryBarrier();',
    1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# C++ SBS reader: decode overlay rectangles from reserved header bytes.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
t = p.read_text(encoding='utf-8')
const_marker = 'constexpr std::size_t kSbsMappingSize = kSbsHeaderSize + kMaxSbsBytes;\n'
require(t, const_marker, 'v0.13.18: SBS constants marker missing')
t = t.replace(
    const_marker,
    const_marker + 'constexpr int kMaxUiOverlayRects = 3;\n',
    1)

snapshot_marker = '''struct SbsSnapshot {
    std::int64_t sequence{};'''
require(t, snapshot_marker, 'v0.13.18: SbsSnapshot marker missing')
t = t.replace(
    snapshot_marker,
    '''struct UiOverlayRectPx {
    int left{};
    int top{};
    int width{};
    int height{};
};

struct SbsSnapshot {
    std::int64_t sequence{};''',
    1)

frame_field = '    std::int32_t frameNumber{};\n    std::vector<std::uint8_t> sbs;'
require(t, frame_field, 'v0.13.18: SbsSnapshot frame field missing')
t = t.replace(
    frame_field,
    '''    std::int32_t frameNumber{};
    int uiOverlayCount{};
    std::array<UiOverlayRectPx, kMaxUiOverlayRects> uiOverlays{};
    std::vector<std::uint8_t> sbs;''',
    1)

read_marker = '''            candidate.sbsStride = ReadI32(view_, 52);
            candidate.frameNumber = ReadI32(view_, 56);

            const bool valid ='''
require(t, read_marker, 'v0.13.18: SBS read marker missing')
read_new = '''            candidate.sbsStride = ReadI32(view_, 52);
            candidate.frameNumber = ReadI32(view_, 56);
            candidate.uiOverlayCount = std::clamp(
                ReadI32(view_, 64), 0, kMaxUiOverlayRects);
            for (int i = 0; i < candidate.uiOverlayCount; ++i) {
                const std::size_t o = 68 + static_cast<std::size_t>(i) * 16;
                candidate.uiOverlays[i] = {
                    ReadI32(view_, o + 0),
                    ReadI32(view_, o + 4),
                    ReadI32(view_, o + 8),
                    ReadI32(view_, o + 12)
                };
            }

            const bool valid ='''
t = t.replace(read_marker, read_new, 1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# C++ main: convert pixel UI rectangles to A-plane rectangles and pass to renderer.
# Also fix XR splash timing/COM initialization.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')

# Splash state members.
splash_member = '    std::chrono::steady_clock::time_point splashUntil_{};\n'
require(t, splash_member, 'v0.13.18: splashUntil member missing')
t = t.replace(
    splash_member,
    '''    std::chrono::steady_clock::time_point splashUntil_{};
    bool splashStarted_{};
    bool comInitializedByUs_{};
''',
    1)

# COM must be initialized before WIC CoCreateInstance. The old timer was started
# here far too early and could expire before the headset produced its first frame.
load_try = '''        try {
            const auto dir = ggqv1312::ExeDir1312();'''
require(t, load_try, 'v0.13.18: splash load try marker missing')
t = t.replace(
    load_try,
    '''        const HRESULT coInitResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (SUCCEEDED(coInitResult)) {
            comInitializedByUs_ = true;
        } else if (coInitResult != RPC_E_CHANGED_MODE) {
            Log("v0.13.18 COM init for XR splash failed hr=" +
                std::to_string(static_cast<long long>(coInitResult)));
        }

        try {
            const auto dir = ggqv1312::ExeDir1312();''',
    1)

old_timer = '            splashUntil_ = std::chrono::steady_clock::now() + std::chrono::milliseconds(2800);\n'
require(t, old_timer, 'v0.13.18: old early splash timer missing')
t = t.replace(
    old_timer,
    '            splashStarted_ = false; // timer starts on first renderable XR frame\n',
    1)

# Restart splash when XR becomes visible again (first launch or headset wake).
state_marker = '''                    const auto& changed =
                        *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                    sessionState_ = changed.state;'''
require(t, state_marker, 'v0.13.18: XR session state marker missing')
t = t.replace(
    state_marker,
    '''                    const auto& changed =
                        *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                    const XrSessionState previousState = sessionState_;
                    sessionState_ = changed.state;
                    const bool wasVisible =
                        previousState == XR_SESSION_STATE_VISIBLE ||
                        previousState == XR_SESSION_STATE_FOCUSED;
                    const bool isVisibleNow =
                        sessionState_ == XR_SESSION_STATE_VISIBLE ||
                        sessionState_ == XR_SESSION_STATE_FOCUSED;
                    if (isVisibleNow && !wasVisible) {
                        splashStarted_ = false;
                    }''',
    1)

# Insert UI-rect conversion helper before UpdatePointer.
pointer_marker = '    bool UpdatePointer(\n'
require(t, pointer_marker, 'v0.13.18: UpdatePointer marker missing')
ui_rect_helper = r'''    int MakeUiOverlayRects(
        const PanelRect& base,
        std::array<PanelRect, kMaxUiOverlayRects>& out) const {

        if (!sbsFrame_.active ||
            sbsFrame_.clientWidth < 2 || sbsFrame_.clientHeight < 2) {
            return 0;
        }

        const float clientWidth = static_cast<float>(sbsFrame_.clientWidth);
        const float clientHeight = static_cast<float>(sbsFrame_.clientHeight);
        const float baseWidth = base.right - base.left;
        const float baseHeight = base.top - base.bottom;
        int count = 0;

        for (int i = 0;
             i < sbsFrame_.uiOverlayCount && i < kMaxUiOverlayRects;
             ++i) {
            const auto& r = sbsFrame_.uiOverlays[i];
            if (r.width < 2 || r.height < 2) continue;

            const float leftN = std::clamp(r.left / clientWidth, 0.0f, 1.0f);
            const float rightN = std::clamp(
                (r.left + r.width) / clientWidth, 0.0f, 1.0f);
            const float topN = std::clamp(r.top / clientHeight, 0.0f, 1.0f);
            const float bottomN = std::clamp(
                (r.top + r.height) / clientHeight, 0.0f, 1.0f);
            if (rightN <= leftN || bottomN <= topN) continue;

            PanelRect patch{
                base.left + baseWidth * leftN,
                base.left + baseWidth * rightN,
                base.top - baseHeight * topN,
                base.top - baseHeight * bottomN
            };
            patch.left = std::max(patch.left, base.left);
            patch.right = std::min(patch.right, base.right);
            patch.top = std::min(patch.top, base.top);
            patch.bottom = std::max(patch.bottom, base.bottom);
            if (patch.right <= patch.left || patch.top <= patch.bottom) continue;
            out[count++] = patch;
        }
        return count;
    }

'''
t = t.replace(pointer_marker, ui_rect_helper + pointer_marker, 1)

# Start splash timer only when shouldRender is true. Keep splash visible if A is
# temporarily unavailable, which removes the black wake-up interval.
old_show = '''        const bool splashReady = splashLeft_.Valid() && splashRight_.Valid();
        const bool showSplash = splashReady &&
            (!baseTexture_.Valid() || std::chrono::steady_clock::now() < splashUntil_);
        if (frameState.shouldRender && (baseTexture_.Valid() || showSplash)) {'''
require(t, old_show, 'v0.13.18: old showSplash block missing')
new_show = '''        const bool splashReady = splashLeft_.Valid() && splashRight_.Valid();
        const auto splashNow = std::chrono::steady_clock::now();
        if (frameState.shouldRender && splashReady && !splashStarted_) {
            splashStarted_ = true;
            splashUntil_ = splashNow + std::chrono::milliseconds(2200);
            Log("v0.13.18 XR splash started on first visible/renderable frame");
        }
        const bool showSplash = splashReady && splashStarted_ &&
            (!baseTexture_.Valid() || splashNow < splashUntil_);
        if (frameState.shouldRender && (baseTexture_.Valid() || showSplash)) {'''
t = t.replace(old_show, new_show, 1)

# UI overlay rectangles for this frame.
stereo_marker = '''                const bool stereoValid =
                    !showSplash && sbsTexture_.Valid() && MakeStereoRect(baseRect, stereoRect);

                float cursorX = 0.0f;'''
require(t, stereo_marker, 'v0.13.18: stereoValid render block missing')
t = t.replace(
    stereo_marker,
    '''                const bool stereoValid =
                    !showSplash && sbsTexture_.Valid() && MakeStereoRect(baseRect, stereoRect);
                std::array<PanelRect, kMaxUiOverlayRects> uiOverlayRects{};
                const int uiOverlayCount = stereoValid
                    ? MakeUiOverlayRects(baseRect, uiOverlayRects)
                    : 0;

                float cursorX = 0.0f;''',
    1)

call_marker = '''                        stereoValid ? &stereoRect : nullptr,
                        eye == 1,'''
require(t, call_marker, 'v0.13.18: RenderEye stereo args marker missing')
t = t.replace(
    call_marker,
    '''                        stereoValid ? &stereoRect : nullptr,
                        stereoValid ? uiOverlayRects.data() : nullptr,
                        uiOverlayCount,
                        eye == 1,''',
    1)

shutdown_marker = '''        splashLeft_.Reset();
        splashRight_.Reset();
        context_.Reset();'''
require(t, shutdown_marker, 'v0.13.18: splash shutdown marker missing')
t = t.replace(
    shutdown_marker,
    '''        splashLeft_.Reset();
        splashRight_.Reset();
        if (comInitializedByUs_) {
            CoUninitialize();
            comInitializedByUs_ = false;
        }
        context_.Reset();''',
    1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# Renderer: draw A UI patches after fixed B; use real Windows IDC_ARROW cursor.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

# RenderEye signature receives UI rectangles.
sig_marker = '''        ID3D11ShaderResourceView* sbsSrv,
        const PanelRect* stereoRect,
        bool rightEye,'''
require(t, sig_marker, 'v0.13.18: RenderEye signature marker missing')
t = t.replace(
    sig_marker,
    '''        ID3D11ShaderResourceView* sbsSrv,
        const PanelRect* stereoRect,
        const PanelRect* uiOverlayRects,
        int uiOverlayCount,
        bool rightEye,''',
    1)

hole_marker = '''                DrawBaseWithHole(
                    context, view, baseRect, baseHole, baseSrv);
            }'''
require(t, hole_marker, 'v0.13.18: DrawBaseWithHole call missing')
t = t.replace(
    hole_marker,
    '''                DrawBaseWithHole(
                    context, view, baseRect, baseHole, baseSrv);
                DrawBaseOverlayPatches(
                    context, view, baseRect, baseSrv,
                    uiOverlayRects, uiOverlayCount);
            }''',
    1)

# Replace v0.13.17 hand-drawn triangle with the real Windows system arrow.
shape_pattern = re.compile(
    r'        // 41x41 upright pointed isosceles triangle\..*?'
    r'        cursorTexture_\.Upload\(\n'
    r'            device, context,\n'
    r'            reinterpret_cast<const std::uint8_t\*>\(pixels\.data\(\)\),\n'
    r'            s, s, s \* 4\);',
    re.S)
sm = shape_pattern.search(t)
if not sm:
    raise SystemExit('v0.13.18: v0.13.17 cursor artwork block missing')

windows_cursor = r'''        // Use the real Windows IDC_ARROW bitmap and hotspot. DrawIconEx paints the
        // system cursor into a transparent 32-bit DIB; a sentinel background lets us
        // recover transparency even for legacy cursors whose GDI alpha is zero.
        bool windowsArrowLoaded = false;
        HCURSOR arrow = LoadCursorW(nullptr, IDC_ARROW);
        if (arrow) {
            ICONINFO iconInfo{};
            if (GetIconInfo(arrow, &iconInfo)) {
                const int w = std::clamp(GetSystemMetrics(SM_CXCURSOR), 16, 128);
                const int h = std::clamp(GetSystemMetrics(SM_CYCURSOR), 16, 128);
                BITMAPINFO bmi{};
                bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
                bmi.bmiHeader.biWidth = w;
                bmi.bmiHeader.biHeight = -h; // top-down
                bmi.bmiHeader.biPlanes = 1;
                bmi.bmiHeader.biBitCount = 32;
                bmi.bmiHeader.biCompression = BI_RGB;

                HDC screenDc = GetDC(nullptr);
                HDC memDc = screenDc ? CreateCompatibleDC(screenDc) : nullptr;
                void* bits = nullptr;
                HBITMAP dib = memDc
                    ? CreateDIBSection(memDc, &bmi, DIB_RGB_COLORS, &bits, nullptr, 0)
                    : nullptr;
                HGDIOBJ oldObject = nullptr;
                if (dib && bits) {
                    oldObject = SelectObject(memDc, dib);
                    auto* px = static_cast<std::uint32_t*>(bits);
                    constexpr std::uint32_t sentinel = 0x00010203u;
                    std::fill_n(px, static_cast<std::size_t>(w * h), sentinel);
                    if (DrawIconEx(
                            memDc, 0, 0, arrow, w, h, 0, nullptr, DI_NORMAL)) {
                        for (int i = 0; i < w * h; ++i) {
                            const std::uint32_t rgb = px[i] & 0x00FFFFFFu;
                            if (rgb == (sentinel & 0x00FFFFFFu)) {
                                px[i] = 0x00000000u;
                            } else if ((px[i] & 0xFF000000u) == 0) {
                                px[i] |= 0xFF000000u;
                            }
                        }
                        cursorTexture_.Upload(
                            device, context,
                            reinterpret_cast<const std::uint8_t*>(px),
                            w, h, w * 4);
                        cursorHotspotU_ = std::clamp(
                            static_cast<float>(iconInfo.xHotspot) /
                                static_cast<float>(std::max(1, w)),
                            0.0f, 1.0f);
                        cursorHotspotV_ = std::clamp(
                            static_cast<float>(iconInfo.yHotspot) /
                                static_cast<float>(std::max(1, h)),
                            0.0f, 1.0f);
                        cursorAspect_ = static_cast<float>(w) /
                            static_cast<float>(std::max(1, h));
                        windowsArrowLoaded = cursorTexture_.Valid();
                    }
                }
                if (oldObject) SelectObject(memDc, oldObject);
                if (dib) DeleteObject(dib);
                if (memDc) DeleteDC(memDc);
                if (screenDc) ReleaseDC(nullptr, screenDc);
                if (iconInfo.hbmColor) DeleteObject(iconInfo.hbmColor);
                if (iconInfo.hbmMask) DeleteObject(iconInfo.hbmMask);
            }
        }

        if (!windowsArrowLoaded) {
            // Safe fallback: retain the v0.13.17 pointed north-apex triangle.
            constexpr int s = 41;
            std::array<std::uint32_t, s * s> pixels{};
            constexpr std::uint32_t transparent = 0x00000000u;
            constexpr std::uint32_t outline = 0xFF101820u;
            constexpr std::uint32_t fill = 0xFFFFFFFFu;
            constexpr float centerX = 20.0f;
            constexpr float apexY = 2.0f;
            constexpr float baseY = 38.0f;
            constexpr float baseHalfWidth = 8.0f;
            pixels.fill(transparent);
            for (int y = 0; y < s; ++y) {
                for (int x = 0; x < s; ++x) {
                    const float fy = static_cast<float>(y);
                    if (fy < apexY || fy > baseY) continue;
                    const float progress = (fy - apexY) / (baseY - apexY);
                    const float halfWidth = baseHalfWidth * progress;
                    const float dx = std::abs(static_cast<float>(x) - centerX);
                    if (dx > halfWidth + 0.55f) continue;
                    const float sideDistance = halfWidth - dx;
                    const bool edge = sideDistance < 1.65f || (baseY - fy) < 1.65f;
                    pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;
                }
            }
            cursorTexture_.Upload(
                device, context,
                reinterpret_cast<const std::uint8_t*>(pixels.data()),
                s, s, s * 4);
            cursorHotspotU_ = 0.50f;
            cursorHotspotV_ = 0.05f;
            cursorAspect_ = 1.0f;
        }'''
t = t[:sm.start()] + windows_cursor + t[sm.end():]

# Dynamic system hotspot/aspect in the UI cursor quad.
hotspot_old = '''                // The visual pointer's NORTH apex A is at texture pixel (20, 2)
                // in a 41x41 image, i.e. normalized hotspot (0.5, 0.05).
                // Anchor A exactly to the logical Windows/GeoGebra mouse point.
                constexpr float kCursorHotspotU = 0.50f;
                constexpr float kCursorHotspotV = 0.05f;
                const float cursorLeft =
                    mouseX - kCursorSizeMeters * kCursorHotspotU;
                const float cursorTop =
                    mouseY + kCursorSizeMeters * kCursorHotspotV;
                PanelRect cursor{
                    cursorLeft,
                    cursorLeft + kCursorSizeMeters,
                    cursorTop,
                    cursorTop - kCursorSizeMeters};'''
require(t, hotspot_old, 'v0.13.18: v0.13.17 cursor hotspot render block missing')
hotspot_new = '''                // System cursor hotspot is expressed in texture coordinates.
                // Anchor that exact hotspot to the logical Windows/GeoGebra mouse.
                const float cursorHeight = kCursorSizeMeters;
                const float cursorWidth = cursorHeight * cursorAspect_;
                const float cursorLeft =
                    mouseX - cursorWidth * cursorHotspotU_;
                const float cursorTop =
                    mouseY + cursorHeight * cursorHotspotV_;
                PanelRect cursor{
                    cursorLeft,
                    cursorLeft + cursorWidth,
                    cursorTop,
                    cursorTop - cursorHeight};'''
t = t.replace(hotspot_old, hotspot_new, 1)

member_marker = '''    SourceTexture cursorTexture_;
    SourceTexture mouseCursorTexture_;'''
require(t, member_marker, 'v0.13.18: cursor texture members missing')
t = t.replace(
    member_marker,
    '''    SourceTexture cursorTexture_;
    SourceTexture mouseCursorTexture_;
    float cursorHotspotU_{0.0f};
    float cursorHotspotV_{0.0f};
    float cursorAspect_{1.0f};''',
    1)

# Draw A fragments over B for dynamic toolbar/menu rectangles.
draw_quad_marker = '    void DrawQuad(\n'
require(t, draw_quad_marker, 'v0.13.18: DrawQuad marker missing')
overlay_helper = r'''    void DrawBaseOverlayPatches(
        ID3D11DeviceContext* context,
        const XrView& view,
        const PanelRect& base,
        ID3D11ShaderResourceView* texture,
        const PanelRect* patches,
        int patchCount) {

        if (!texture || !patches || patchCount <= 0) return;
        const float width = std::max(0.0001f, base.right - base.left);
        const float height = std::max(0.0001f, base.top - base.bottom);
        const int count = std::clamp(patchCount, 0, kMaxUiOverlayRects);

        for (int i = 0; i < count; ++i) {
            PanelRect p = ClampPanelRect(patches[i], base);
            if (p.right <= p.left || p.top <= p.bottom) continue;
            const float u0 = std::clamp((p.left - base.left) / width, 0.0f, 1.0f);
            const float u1 = std::clamp((p.right - base.left) / width, 0.0f, 1.0f);
            const float v0 = std::clamp((base.top - p.top) / height, 0.0f, 1.0f);
            const float v1 = std::clamp((base.top - p.bottom) / height, 0.0f, 1.0f);
            DrawQuad(
                context, view, p, -kScreenDistanceMeters,
                texture, u0, v0, u1, v1, true);
        }
    }

'''
t = t.replace(draw_quad_marker, overlay_helper + draw_quad_marker, 1)
p.write_text(t, encoding='utf-8')


# CMake: Windows system cursor rasterization needs GDI32.
p = Path('pc-xr/CMakeLists.txt')
t = p.read_text(encoding='utf-8')
if '  gdi32\n' not in t:
    require(t, '  user32\n', 'v0.13.18: CMake user32 marker missing')
    t = t.replace('  user32\n', '  user32\n  gdi32\n', 1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# Version / cache-buster / package labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.17-cursor-apex', '0.13.18-ui-overlay-splash')
    s = s.replace(r'0\.13\.17-cursor-apex', r'0\.13\.18-ui-overlay-splash')
    s = s.replace('v0.13.17', 'v0.13.18')

    if file.endswith('MainFormV11.cs'):
        s = re.sub(
            r'(pc-stereo-layout\.js\?v=)[^"\']+',
            r'\g<1>0.13.18-ui-overlay-splash',
            s,
            count=1)

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.18</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.18.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.18.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = re.sub(
            r'GeoGebraForQuest-PC-v0\.13\.17-cursor-apex-win-x64',
            'GeoGebraForQuest-PC-v0.13.18-ui-overlay-splash-win-x64',
            s,
            count=1)

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.18 dynamic UI overlay + Windows cursor + XR splash fix applied')
