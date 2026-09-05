from pathlib import Path
import re


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# v0.13.17 cursor apex + sharper isosceles pointer.
#
# v0.13.16 anchored the logical click point to the wrong visible vertex of the
# rotated triangle. Replace that cursor artwork with an explicit upright
# isosceles triangle:
#
#                 A  <- hotspot / click point (north)
#                / \
#               /   \
#              B-----C
#
# A is north, B south-west, C south-east, and AB = AC > BC.  The cursor is
# intentionally narrow/pointed. Mouse coordinates and GeoGebra hit-testing stay
# untouched; only the visual cursor artwork and its hotspot are changed.
# ---------------------------------------------------------------------------

p = Path('pc-xr/v11-render.hpp')
t = p.read_text(encoding='utf-8')

old_shape = '''        // 40x40 cyan triangle, rotated 45 degrees counter-clockwise. Dark
        // outline + transparent background keeps one cursor visible on any UI.
        constexpr int s = 40;
        std::array<std::uint32_t, s * s> pixels{};
        constexpr std::uint32_t transparent = 0x00000000u;
        constexpr std::uint32_t outline = 0xFF101820u;
        constexpr std::uint32_t fill = 0xFFFFFFFFu;
        constexpr float c = 0.70710678f;
        pixels.fill(transparent);
        for (int y = 0; y < s; ++y) {
            for (int x = 0; x < s; ++x) {
                const float px = static_cast<float>(x) - 19.5f;
                const float py = static_cast<float>(y) - 19.5f;
                const float sx = c * px - c * py + 19.5f;
                const float sy = c * px + c * py + 19.5f;
                const float dx = sx - 5.0f;
                const float dy = std::abs(sy - 19.5f);
                const bool inside = dx >= 0.0f && dx <= 30.0f &&
                    dy <= dx * 0.58f + 1.0f;
                if (!inside) continue;
                const bool edge = dx < 3.0f ||
                    std::abs(dy - (dx * 0.58f + 1.0f)) < 2.2f ||
                    sx >= 33.0f;
                pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;
            }
        }'''

new_shape = '''        // 41x41 upright pointed isosceles triangle. A is the NORTH apex and is
        // the actual mouse hotspot. B/C form a short south base, so AB = AC > BC.
        // Dark outline + white fill keeps it visible on both light and dark UI.
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

                // Roughly 1.5-2 px dark border along the two long sides and base.
                const float sideDistance = halfWidth - dx;
                const bool edge = sideDistance < 1.65f || (baseY - fy) < 1.65f;
                pixels[static_cast<std::size_t>(y * s + x)] = edge ? outline : fill;
            }
        }'''

require(t, old_shape, 'v0.13.17: previous rotated cursor artwork block missing')
t = t.replace(old_shape, new_shape, 1)

old_hotspot = '''                // The generated 40x40 triangle is rotated 45 degrees and its
                // visible tip lies at approximately (u=0.25, v=0.75) in texture
                // coordinates. Anchor that tip, not the quad centre, to the real
                // mouse coordinate. This makes what the user points at exactly what
                // GeoGebra receives for hover/click/point placement.
                constexpr float kCursorHotspotU = 0.25f;
                constexpr float kCursorHotspotV = 0.75f;'''

new_hotspot = '''                // The visual pointer's NORTH apex A is at texture pixel (20, 2)
                // in a 41x41 image, i.e. normalized hotspot (0.5, 0.05).
                // Anchor A exactly to the logical Windows/GeoGebra mouse point.
                constexpr float kCursorHotspotU = 0.50f;
                constexpr float kCursorHotspotV = 0.05f;'''

require(t, old_hotspot, 'v0.13.17: v0.13.16 hotspot block missing')
t = t.replace(old_hotspot, new_hotspot, 1)
p.write_text(t, encoding='utf-8')

# Version/package labels.
for file in ('pc/MainFormV11.cs', 'pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    s = s.replace('0.13.16-cursor-hotspot', '0.13.17-cursor-apex')
    s = s.replace(r'0\\.13\\.16-cursor-hotspot', r'0\\.13\\.17-cursor-apex')
    s = s.replace('v0.13.16', 'v0.13.17')

    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.17</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.17.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.17.0</AssemblyVersion>', s, count=1)

    if file.endswith('build.ps1'):
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.16-cursor-hotspot-win-x64',
            'GeoGebraForQuest-PC-v0.13.17-cursor-apex-win-x64')

    p.write_text(s, encoding='utf-8')

print('GeoGebraForQuest PC v0.13.17 cursor apex patch applied')
