from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.19 hybrid UI policy
#
# v0.13.18 kept B fixed and repainted GeoGebra UI rectangles from A over B.
# That is correct for the small expandable 3D stylebar, but too aggressive for
# true dialogs / file-open pages / large overlays: B can cover the page and the
# flat XR mouse cursor is hidden merely because the pointer is geometrically
# inside the stereo rectangle.
#
# Policy in this patch:
#   * small/local UI (3D stylebar, compact toolbar/menu) -> keep B fixed and
#     repaint the A UI rectangle over it;
#   * modal dialog or genuinely large overlay -> temporarily disable B so the
#     full A page/dialog is visible and interactive;
#   * while B stays active, if the mouse is over an A overlay rectangle, show
#     the Windows/XR cursor even though the point lies inside the stereo region.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) JS: detect major/modal blockers separately from small overlay rectangles.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
t = p.read_text(encoding='utf-8')

insert_marker = '  function findVisible3DCanvas() {'
require(t, insert_marker, 'v0.13.19: findVisible3DCanvas marker missing')

major_helper = r'''
  // v0.13.19: distinguish a true page/dialog blocker from the compact 3D
  // stylebar. Compact UI is repainted over B; modal or large UI suppresses B.
  function majorUiBlocksStereo(canvas, panelRect) {
    if (!canvas || !panelRect) return false;

    var panelArea = Math.max(1, rectArea(panelRect));

    function blocks(element) {
      if (!element || element === canvas) return false;
      if (element.contains && element.contains(canvas)) return false;
      if (!visibleElement(element)) return false;

      var raw = rawRectOf(element);
      var clipped = raw && intersectRect(raw, panelRect);
      if (!clipped) return false;

      var areaFraction = rectArea(clipped) / panelArea;
      var role = String(element.getAttribute && element.getAttribute('role') || '').toLowerCase();
      var ariaModal = String(element.getAttribute && element.getAttribute('aria-modal') || '').toLowerCase();
      var tag = String(element.tagName || '').toLowerCase();
      var label = String(
        (element.getAttribute &&
          (element.getAttribute('aria-label') || element.getAttribute('title'))) || ''
      ).toLowerCase();
      var semantic = classAndIdText(element) + ' ' + label;

      // True modal/dialog semantics always win, even for a small confirmation
      // such as "save changes?".
      if (tag === 'dialog' || role === 'dialog' || ariaModal === 'true') return true;

      // Explicit file/open/save chooser families are considered blocking once
      // they cover a meaningful part of the 3D canvas.
      var fileLike = /(file|open|save|chooser|browser|document|material)/.test(semantic);
      if (fileLike && areaFraction >= 0.16) return true;

      // A genuinely large painted overlay is a page-level takeover. The
      // threshold deliberately keeps a narrow hamburger side menu and the
      // expandable 3D stylebar in the small-overlay path.
      if (areaFraction >= 0.36 && hasPaint(element)) return true;

      // A menu/listbox can become a page-sized chooser without dialog ARIA.
      // Only treat it as blocking when it is substantially larger than a
      // compact toolbar/dropdown.
      if ((role === 'menu' || role === 'listbox' || isMenuLike(element)) &&
          areaFraction >= 0.28) {
        return true;
      }

      return false;
    }

    var selectors = [
      '[role="dialog"]', '[aria-modal="true"]', 'dialog',
      '[role="menu"]', '[role="listbox"]',
      '.gwt-PopupPanel', '.gwt-DialogBox',
      '[class*="Popup"]', '[class*="popup"]',
      '[class*="Dialog"]', '[class*="dialog"]',
      '[class*="File"]', '[class*="file"]',
      '[class*="Open"]', '[class*="open"]',
      '[class*="Save"]', '[class*="save"]'
    ].join(',');

    try {
      var known = document.querySelectorAll(selectors);
      for (var i = 0; i < known.length; i++) {
        if (blocks(known[i])) return true;
      }
    } catch (_) {}

    // Catch large GWT/page overlays whose class names are opaque. Sampling the
    // middle of the stereo canvas avoids class-name dependence.
    var xs = [0.18, 0.38, 0.50, 0.62, 0.82];
    var ys = [0.18, 0.38, 0.50, 0.62, 0.82];
    for (var yi = 0; yi < ys.length; yi++) {
      for (var xi = 0; xi < xs.length; xi++) {
        var x = panelRect.left + panelRect.width * xs[xi];
        var y = panelRect.top + panelRect.height * ys[yi];
        var stack;
        try { stack = document.elementsFromPoint(x, y); } catch (_) { stack = null; }
        if (!stack || !stack.length) continue;
        var canvasIndex = canvasIndexInStack(stack, canvas);
        var limit = canvasIndex >= 0 ? canvasIndex : Math.min(stack.length, 8);
        for (var si = 0; si < limit; si++) {
          if (blocks(stack[si])) return true;
        }
      }
    }

    return false;
  }

'''

t = t.replace(insert_marker, major_helper + insert_marker, 1)

refresh_pattern = re.compile(
    r'  function refreshGeometry\(\) \{.*?\n  \}\n\n  function scheduleGeometry\(\) \{',
    re.S)
m = refresh_pattern.search(t)
if not m:
    raise SystemExit('v0.13.19: refreshGeometry block missing')

new_refresh = r'''  function refreshGeometry() {
    geometryScheduled = false;

    var canvas = find3DCanvas();
    var rect = clippedRectOf(canvas);
    if (!canvas || !rect) {
      reportInactive('no-3d');
      return;
    }

    // B keeps the true 3D canvas geometry for compact local UI.
    var visibleRect = rect;
    if (visibleRect.width < 20 || visibleRect.height < 20) {
      reportInactive('3d-too-small');
      return;
    }

    // v0.13.19 hybrid rule: modal dialogs, file/open/save pages and genuinely
    // large overlays temporarily suppress B. A therefore becomes fully opaque
    // and both the page and mouse interaction are available in Quest.
    if (majorUiBlocksStereo(canvas, visibleRect)) {
      reportInactive('major-ui');
      return;
    }

    // Small/local UI stays on the fixed stereo panel and is repainted from A.
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
# 2) XR renderer: do not hide the system cursor over A overlay rectangles.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

old_cursor_gate = '''            if (!mouseInsideStereo3D) {
                const float scale =
                    kCursorDistanceMeters / kScreenDistanceMeters;'''
require(t, old_cursor_gate, 'v0.13.19: cursor stereo gate missing')

new_cursor_gate = '''            bool mouseOverUiOverlay = false;
            if (mouseInsideStereo3D && uiOverlayRects != nullptr && uiOverlayCount > 0) {
                const int count = std::clamp(uiOverlayCount, 0, kMaxUiOverlayRects);
                for (int i = 0; i < count; ++i) {
                    const PanelRect& overlay = uiOverlayRects[i];
                    if (hitX >= overlay.left && hitX <= overlay.right &&
                        hitY <= overlay.top && hitY >= overlay.bottom) {
                        mouseOverUiOverlay = true;
                        break;
                    }
                }
            }

            // Inside bare B we keep the flat XR cursor hidden so GeoGebra's
            // depth-aware cursor remains natural. Over an A toolbar/menu patch,
            // however, show the Windows cursor so the overlay is actually usable.
            if (!mouseInsideStereo3D || mouseOverUiOverlay) {
                const float scale =
                    kCursorDistanceMeters / kScreenDistanceMeters;'''

t = t.replace(old_cursor_gate, new_cursor_gate, 1)
p.write_text(t, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Version / cache-buster / package labels.
# ---------------------------------------------------------------------------
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.18-ui-overlay-splash', '0.13.19-hybrid-overlay-modal')
    s = s.replace(r'0\.13\.18-ui-overlay-splash', r'0\.13\.19-hybrid-overlay-modal')
    s = s.replace('v0.13.18', 'v0.13.19')

    if file.endswith('MainFormV11.cs'):
        s = re.sub(
            r'(pc-stereo-layout\.js\?v=)[^"\']+',
            r'\g<1>0.13.19-hybrid-overlay-modal',
            s,
            count=1)

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.19</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.19.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.19.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.18-ui-overlay-splash-win-x64',
            'GeoGebraForQuest-PC-v0.13.19-hybrid-overlay-modal-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.19 hybrid overlay/modal patch applied')
