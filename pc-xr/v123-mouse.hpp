#pragma once

namespace ggqv11 {

constexpr wchar_t kMouseMapName[] = L"Local\\GeoGebraForQuestPC_Mouse_v1";
constexpr std::int32_t kMouseMagic = 0x47514D53;
constexpr std::int32_t kMouseProtocolVersion = 1;
constexpr std::size_t kMouseMappingSize = 64;

struct MousePointerState {
    bool valid{};
    float u{};
    float v{};
};

class MousePointerSharedReader {
public:
    ~MousePointerSharedReader() {
        Reset();
    }

    MousePointerState ReadLatest() {
        if (!EnsureOpen()) return {};

        for (int attempt = 0; attempt < 3; ++attempt) {
            const std::int64_t sequenceA = ReadI64(view_, 8);
            if (sequenceA <= 0 || (sequenceA & 1) != 0) continue;

            const std::int32_t valid = ReadI32(view_, 16);
            const float u = ReadF32(view_, 20);
            const float v = ReadF32(view_, 24);
            MemoryBarrier();
            const std::int64_t sequenceB = ReadI64(view_, 8);

            if (sequenceA == sequenceB && (sequenceB & 1) == 0) {
                return {
                    valid != 0,
                    std::clamp(u, 0.0f, 1.0f),
                    std::clamp(v, 0.0f, 1.0f)
                };
            }
        }
        return {};
    }

private:
    HANDLE mapping_{};
    const std::uint8_t* view_{};

    bool EnsureOpen() {
        if (view_) return true;

        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kMouseMapName);
        if (!mapping_) return false;

        view_ = static_cast<const std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kMouseMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            return false;
        }

        if (ReadI32(view_, 0) != kMouseMagic ||
            ReadI32(view_, 4) != kMouseProtocolVersion) {
            Reset();
            return false;
        }
        return true;
    }

    void Reset() {
        if (view_) {
            UnmapViewOfFile(view_);
            view_ = nullptr;
        }
        if (mapping_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
        }
    }
};

} // namespace ggqv11
