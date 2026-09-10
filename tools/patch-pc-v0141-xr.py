#!/usr/bin/env python3
from pathlib import Path


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.14.1 — zero-copy GPU B consumer.
#
# The v0.13.35 correctness baseline is preserved as compatibility:
#   pixelFormat 1 = legacy BGRA L|R
#   pixelFormat 2 = older raw-RGBA L|R compatibility
#
# v0.14.1 adds:
#   pixelFormat 5 = CEF accelerated-paint GPU staging texture
#
# The old CPU/MMF SBS transport is no longer used by v0.14.1 at runtime, but
# the compositor keeps format 1/2 support so the known-good rendering contract
# is not destructively rewritten.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) Shared metadata reader for the GPU-resident B texture.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
shared = p.read_text(encoding='utf-8')

const_marker = 'constexpr wchar_t kSbsMapName[] = L"Local\\\\GeoGebraForQuestPC_SBS_v2";\n'
req(shared, const_marker, 'v0.14.1: shared SBS constant marker missing')
shared = shared.replace(
    const_marker,
    '''constexpr wchar_t kStereoGpuMapName[] = L"Local\\\\GeoGebraForQuestPC_B_GPU_v1";
constexpr std::int32_t kStereoGpuMagic = 0x47514247;
constexpr std::int32_t kStereoGpuProtocolVersion = 1;
constexpr std::size_t kStereoGpuMappingSize = 128;

''' + const_marker,
    1)

reader_marker = 'struct SbsSnapshot {\n'
req(shared, reader_marker, 'v0.14.1: SbsSnapshot marker missing')
stereo_reader = r'''struct StereoGpuFrameInfo {
    std::int64_t sequence{};
    bool active{};
    int textureWidth{};
    int textureHeight{};
    DXGI_FORMAT format{DXGI_FORMAT_UNKNOWN};
    HANDLE sharedHandle{};
    int clientWidth{};
    int clientHeight{};
    int panelLeft{};
    int panelTop{};
    int panelWidth{};
    int panelHeight{};
    int stageLeft{};
    int stageTop{};
    int stageWidth{};
    int stageHeight{};
    std::int64_t frameNumber{};
};

class StereoGpuFrameInfoReader {
public:
    ~StereoGpuFrameInfoReader() {
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    bool ReadIfChanged(std::int64_t previousSequence, StereoGpuFrameInfo& out) {
        if (!view_ && !Open()) return false;
        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadI64(view_, 8);
            if ((first & 1) != 0) {
                std::this_thread::yield();
                continue;
            }
            if (first == previousSequence) return false;

            StereoGpuFrameInfo c{};
            c.sequence = first;
            c.active = ReadI32(view_, 16) != 0;
            c.textureWidth = ReadI32(view_, 20);
            c.textureHeight = ReadI32(view_, 24);
            c.format = static_cast<DXGI_FORMAT>(ReadI32(view_, 28));
            c.sharedHandle = reinterpret_cast<HANDLE>(
                static_cast<std::intptr_t>(ReadI64(view_, 32)));
            c.clientWidth = ReadI32(view_, 40);
            c.clientHeight = ReadI32(view_, 44);
            c.panelLeft = ReadI32(view_, 48);
            c.panelTop = ReadI32(view_, 52);
            c.panelWidth = ReadI32(view_, 56);
            c.panelHeight = ReadI32(view_, 60);
            c.stageLeft = ReadI32(view_, 64);
            c.stageTop = ReadI32(view_, 68);
            c.stageWidth = ReadI32(view_, 72);
            c.stageHeight = ReadI32(view_, 76);
            c.frameNumber = ReadI64(view_, 80);

            MemoryBarrier();
            const auto second = ReadI64(view_, 8);
            if (first == second && (second & 1) == 0) {
                out = c;
                return true;
            }
        }
        return false;
    }

private:
    HANDLE mapping_{};
    std::uint8_t* view_{};

    bool Open() {
        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kStereoGpuMapName);
        if (!mapping_) return false;
        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kStereoGpuMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            return false;
        }
        if (ReadI32(view_, 0) != kStereoGpuMagic ||
            ReadI32(view_, 4) != kStereoGpuProtocolVersion) {
            UnmapViewOfFile(view_);
            CloseHandle(mapping_);
            view_ = nullptr;
            mapping_ = nullptr;
            return false;
        }
        Log("B GPU metadata mapping opened");
        return true;
    }
};

'''
shared = shared.replace(reader_marker, stereo_reader + reader_marker, 1)

frame_marker = '    std::int32_t frameNumber{};\n'
req(shared, frame_marker, 'v0.14.1: SbsSnapshot frame marker missing')
shared = shared.replace(
    frame_marker,
    frame_marker +
    '    int stageLeft{};\n'
    '    int stageTop{};\n'
    '    int stageWidth{};\n'
    '    int stageHeight{};\n'
    '    int sourceTextureWidth{};\n'
    '    int sourceTextureHeight{};\n',
    1)
p.write_text(shared, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) main-v11.cpp: replace the CPU SBS source with shared GPU B metadata.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
xr = p.read_text(encoding='utf-8')

member_marker = '''    SharedSbsReader sbsReader_;
    SourceTexture sbsTexture_;
    std::int64_t sbsSequence_{};
    SbsSnapshot sbsFrame_{};
'''
req(xr, member_marker, 'v0.14.1: old SBS members missing')
xr = xr.replace(
    member_marker,
    '''    // v0.14.1 B stays GPU-resident; old pixel SBS reader is intentionally unused.
    StereoGpuFrameInfoReader stereoGpuReader_;
    SharedGpuTextureConsumer stereoGpuTexture_;
    std::int64_t stereoGpuSequence_{};
    StereoGpuFrameInfo stereoGpuFrame_{};
    SbsSnapshot sbsFrame_{};
''',
    1)

init_marker = '        baseTexture_.Initialize(device_.Get());\n'
req(xr, init_marker, 'v0.14.1: base texture init marker missing')
xr = xr.replace(
    init_marker,
    init_marker + '        stereoGpuTexture_.Initialize(device_.Get());\n',
    1)

start = xr.find('        SbsSnapshot sbsUpdate{};')
end = xr.find('\n    }\n\n    void RenderFrame()', start)
if start < 0 or end < 0:
    raise SystemExit('v0.14.1: RefreshSources old SBS block missing')

new_refresh = r'''        StereoGpuFrameInfo bUpdate{};
        if (stereoGpuReader_.ReadIfChanged(stereoGpuSequence_, bUpdate)) {
            stereoGpuSequence_ = bUpdate.sequence;
            stereoGpuFrame_ = bUpdate;

            if (!bUpdate.active) {
                sbsFrame_.active = false;
            } else if (
                bUpdate.sharedHandle &&
                bUpdate.textureWidth > 1 && bUpdate.textureHeight > 1 &&
                bUpdate.clientWidth > 1 && bUpdate.clientHeight > 1 &&
                bUpdate.panelWidth > 1 && bUpdate.panelHeight > 1 &&
                bUpdate.stageWidth > 3 && bUpdate.stageHeight > 1) {

                GpuFrameInfo gpu{};
                gpu.sequence = bUpdate.sequence;
                gpu.active = true;
                gpu.width = bUpdate.textureWidth;
                gpu.height = bUpdate.textureHeight;
                gpu.format = bUpdate.format;
                gpu.sharedHandle = bUpdate.sharedHandle;

                try {
                    if (stereoGpuTexture_.Update(device_.Get(), context_.Get(), gpu)) {
                        sbsFrame_.sequence = bUpdate.sequence;
                        sbsFrame_.active = true;
                        sbsFrame_.clientWidth = bUpdate.clientWidth;
                        sbsFrame_.clientHeight = bUpdate.clientHeight;
                        sbsFrame_.panelLeft = bUpdate.panelLeft;
                        sbsFrame_.panelTop = bUpdate.panelTop;
                        sbsFrame_.panelWidth = bUpdate.panelWidth;
                        sbsFrame_.panelHeight = bUpdate.panelHeight;
                        sbsFrame_.eyeWidth = std::max(2, bUpdate.stageWidth / 2);
                        sbsFrame_.eyeHeight = bUpdate.stageHeight;
                        sbsFrame_.sbsStride = 0;
                        sbsFrame_.frameNumber = static_cast<std::int32_t>(bUpdate.frameNumber);
                        sbsFrame_.pixelFormat = 5;
                        sbsFrame_.stageLeft = bUpdate.stageLeft;
                        sbsFrame_.stageTop = bUpdate.stageTop;
                        sbsFrame_.stageWidth = bUpdate.stageWidth;
                        sbsFrame_.stageHeight = bUpdate.stageHeight;
                        sbsFrame_.sourceTextureWidth = bUpdate.textureWidth;
                        sbsFrame_.sourceTextureHeight = bUpdate.textureHeight;
                    }
                } catch (const std::exception& ex) {
                    Log(std::string("B GPU update error: ") + ex.what());
                }
            }
        }
'''
xr = xr[:start] + new_refresh + xr[end:]

# v0.13.28 originally used format 2; v0.13.29 broadened the gate to (1 || 2),
# and v0.13.31/35 deliberately left the compositor unchanged. Accept either
# generated spelling so the patch is stable across the correctness lineage.
compose_candidates = [
    '''                    const bool pairReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        (sbsFrame_.pixelFormat == 1 || sbsFrame_.pixelFormat == 2) && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        pairReady ? sbsTexture_.Srv() : nullptr,
                        pairReady ? &sbsFrame_ : nullptr);''',
    '''                    const bool pairReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 1 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        pairReady ? sbsTexture_.Srv() : nullptr,
                        pairReady ? &sbsFrame_ : nullptr);''',
    '''                    const bool pairReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 2 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        pairReady ? sbsTexture_.Srv() : nullptr,
                        pairReady ? &sbsFrame_ : nullptr);''',
]

compose_old = next((candidate for candidate in compose_candidates if candidate in xr), None)
if compose_old is None:
    raise SystemExit('v0.14.1: v0.13.35 FullSbs compose block missing')

compose_new = '''                    const bool pairReady =
                        stereoGpuTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 5;
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        pairReady ? stereoGpuTexture_.Srv() : nullptr,
                        pairReady ? &sbsFrame_ : nullptr);'''
xr = xr.replace(compose_old, compose_new, 1)

xr = xr.replace(
    'initialized: A CEF GPU + proven JPEG L/R -> GPU A_L|A_R full-SBS single panel',
    'initialized: A CEF GPU + zero-copy B GPU staging -> A_L|A_R single panel',
    1)
xr = xr.replace(
    'initialized: A CEF GPU + raw TRUE L/R -> GPU A_L|A_R full-SBS single panel',
    'initialized: A CEF GPU + zero-copy B GPU staging -> A_L|A_R single panel',
    1)
p.write_text(xr, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) FullSbs compositor: keep proven format 1/2 and add GPU-stage format 5.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
render = p.read_text(encoding='utf-8')

render_gate_candidates = [
    '            (pairFrame->pixelFormat == 1 || pairFrame->pixelFormat == 2) &&\n',
    '            pairFrame->pixelFormat == 1 &&\n',
    '            pairFrame->pixelFormat == 2 &&\n',
]
render_gate_old = next((candidate for candidate in render_gate_candidates if candidate in render), None)
if render_gate_old is None:
    raise SystemExit('v0.14.1: FullSbs pixel-format gate missing')
render = render.replace(
    render_gate_old,
    '            (pairFrame->pixelFormat == 1 || pairFrame->pixelFormat == 2 || pairFrame->pixelFormat == 5) &&\n',
    1)

left_old = '''                DrawRect(context, stereoPair,
                    panelL, panelT, panelR, panelB,
                    0.0f, 0.0f, 0.5f, 1.0f, fullWidth, fullHeight);

                // A_R: replace 3D with the exact TRUE RIGHT half of the proven pair.
                DrawRect(context, stereoPair,
                    static_cast<float>(fullWidth) + panelL,
                    panelT,
                    static_cast<float>(fullWidth) + panelR,
                    panelB,
                    0.5f, 0.0f, 1.0f, 1.0f, fullWidth, fullHeight);'''
req(render, left_old, 'v0.14.1: FullSbs fixed UV pair block missing')

left_new = '''                float srcU0 = 0.0f;
                float srcUM = 0.5f;
                float srcU1 = 1.0f;
                float srcV0 = 0.0f;
                float srcV1 = 1.0f;
                if (pairFrame->pixelFormat == 5 &&
                    pairFrame->sourceTextureWidth > 1 &&
                    pairFrame->sourceTextureHeight > 1 &&
                    pairFrame->stageWidth > 3 && pairFrame->stageHeight > 1) {
                    const float tw = static_cast<float>(pairFrame->sourceTextureWidth);
                    const float th = static_cast<float>(pairFrame->sourceTextureHeight);
                    srcU0 = std::clamp(pairFrame->stageLeft / tw, 0.0f, 1.0f);
                    srcU1 = std::clamp(
                        (pairFrame->stageLeft + pairFrame->stageWidth) / tw,
                        0.0f, 1.0f);
                    srcUM = (srcU0 + srcU1) * 0.5f;
                    srcV0 = std::clamp(pairFrame->stageTop / th, 0.0f, 1.0f);
                    srcV1 = std::clamp(
                        (pairFrame->stageTop + pairFrame->stageHeight) / th,
                        0.0f, 1.0f);
                }

                DrawRect(context, stereoPair,
                    panelL, panelT, panelR, panelB,
                    srcU0, srcV0, srcUM, srcV1, fullWidth, fullHeight);

                DrawRect(context, stereoPair,
                    static_cast<float>(fullWidth) + panelL,
                    panelT,
                    static_cast<float>(fullWidth) + panelR,
                    panelB,
                    srcUM, srcV0, srcU1, srcV1, fullWidth, fullHeight);'''
render = render.replace(left_old, left_new, 1)
p.write_text(render, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Hard invariants.
# ---------------------------------------------------------------------------
shared = Path('pc-xr/v11-shared.hpp').read_text(encoding='utf-8')
xr = Path('pc-xr/main-v11.cpp').read_text(encoding='utf-8')
render = Path('pc-xr/v11-render.hpp').read_text(encoding='utf-8')

for needed, text in (
    ('GeoGebraForQuestPC_B_GPU_v1', shared),
    ('StereoGpuFrameInfoReader', shared),
    ('stereoGpuTexture_.Update', xr),
    ('sbsFrame_.pixelFormat = 5', xr),
    ('stereoGpuTexture_.Srv()', xr),
    ('pairFrame->pixelFormat == 5', render),
    ('pairFrame->pixelFormat == 1', render),
    ('pairFrame->pixelFormat == 2', render),
    ('rightEye ? 0.5f : 0.0f', render),
):
    req(text, needed, 'v0.14.1 XR invariant missing: ' + needed)

print('GeoGebraForQuest PC v0.14.1 XR GPU-B patch applied')
