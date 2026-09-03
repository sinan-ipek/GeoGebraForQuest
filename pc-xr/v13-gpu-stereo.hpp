#pragma once
#include "v11-shared.hpp"

namespace ggqv13 {

using Microsoft::WRL::ComPtr;
using namespace ggqv11;

constexpr wchar_t kStereoGpuMapName[] = L"Local\\GeoGebraForQuestPC_B_GPU_v1";
constexpr std::int32_t kStereoGpuMagic = 0x47514247;
constexpr std::int32_t kStereoGpuProtocolVersion = 1;
constexpr std::size_t kStereoGpuMappingSize = 96;

struct StereoGpuFrameInfo {
    std::int64_t sequence{};
    bool active{};
    int clientWidth{};
    int clientHeight{};
    int panelLeft{};
    int panelTop{};
    int panelWidth{};
    int panelHeight{};
    int eyeWidth{};
    int eyeHeight{};
    DXGI_FORMAT format{DXGI_FORMAT_UNKNOWN};
    HANDLE sharedHandle{};
    std::int32_t frameNumber{};
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

            StereoGpuFrameInfo candidate{};
            candidate.sequence = first;
            candidate.active = ReadI32(view_, 16) != 0;
            candidate.clientWidth = ReadI32(view_, 20);
            candidate.clientHeight = ReadI32(view_, 24);
            candidate.panelLeft = ReadI32(view_, 28);
            candidate.panelTop = ReadI32(view_, 32);
            candidate.panelWidth = ReadI32(view_, 36);
            candidate.panelHeight = ReadI32(view_, 40);
            candidate.eyeWidth = ReadI32(view_, 44);
            candidate.eyeHeight = ReadI32(view_, 48);
            candidate.format = static_cast<DXGI_FORMAT>(ReadI32(view_, 52));
            const auto handle64 = ReadI64(view_, 56);
            candidate.sharedHandle = reinterpret_cast<HANDLE>(
                static_cast<std::intptr_t>(handle64));
            candidate.frameNumber = ReadI32(view_, 64);

            MemoryBarrier();
            const auto second = ReadI64(view_, 8);
            if (first == second && (second & 1) == 0) {
                out = candidate;
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

// Keeps the last complete shared frame in an XR-owned D3D11 texture.
// v0.13.0 released the keyed mutex immediately after queueing CopyResource. That
// allowed the producer to overwrite the shared surface while the XR GPU could still
// be reading it, which can yield an all-white/corrupt cache. The copy query below is
// intentionally on the XR helper thread only: it never blocks GeoGebra/CEF's UI.
class SharedGpuTextureCache {
public:
    void Reset() {
        srv_.Reset();
        localTexture_.Reset();
        mutex_.Reset();
        sharedTexture_.Reset();
        copyQuery_.Reset();
        sharedHandle_ = nullptr;
        width_ = 0;
        height_ = 0;
        format_ = DXGI_FORMAT_UNKNOWN;
        copiedSequence_ = -1;
    }

    bool Update(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        std::int64_t sequence,
        bool active,
        HANDLE sharedHandle,
        int width,
        int height,
        DXGI_FORMAT format) {

        if (!active || !sharedHandle || width < 2 || height < 2) {
            Reset();
            return false;
        }

        if (!sharedTexture_ ||
            sharedHandle_ != sharedHandle ||
            width_ != width ||
            height_ != height ||
            format_ != format) {
            if (!OpenResource(device, sharedHandle, width, height, format)) {
                return false;
            }
        }

        if (copiedSequence_ == sequence && srv_) {
            return true;
        }

        if (!mutex_ || !sharedTexture_ || !localTexture_ || !copyQuery_) {
            return false;
        }

        const HRESULT acquire = mutex_->AcquireSync(1, 0);
        if (acquire == WAIT_TIMEOUT) return false;
        if (FAILED(acquire)) {
            Log("AcquireSync(GPU cache,key=1) failed HRESULT=" +
                std::to_string(static_cast<long long>(acquire)));
            return false;
        }

        bool releaseNeeded = true;
        try {
            context->CopyResource(localTexture_.Get(), sharedTexture_.Get());
            context->End(copyQuery_.Get());
            context->Flush();

            BOOL copyDone = FALSE;
            for (;;) {
                const HRESULT status = context->GetData(
                    copyQuery_.Get(),
                    &copyDone,
                    sizeof(copyDone),
                    D3D11_ASYNC_GETDATA_DONOTFLUSH);
                if (status == S_OK && copyDone != FALSE) break;
                if (FAILED(status)) {
                    CheckHr(status, "GetData(GPU cache copy)");
                }
                std::this_thread::yield();
            }

            CheckHr(mutex_->ReleaseSync(0), "ReleaseSync(GPU cache,key=0)");
            releaseNeeded = false;
            copiedSequence_ = sequence;
            return true;
        } catch (...) {
            if (releaseNeeded && mutex_) {
                mutex_->ReleaseSync(0);
            }
            throw;
        }
    }

    bool Valid() const { return srv_ != nullptr; }
    ID3D11ShaderResourceView* Srv() const { return srv_.Get(); }
    int Width() const { return width_; }
    int Height() const { return height_; }
    std::int64_t CopiedSequence() const { return copiedSequence_; }

private:
    ComPtr<ID3D11Texture2D> sharedTexture_;
    ComPtr<IDXGIKeyedMutex> mutex_;
    ComPtr<ID3D11Texture2D> localTexture_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    ComPtr<ID3D11Query> copyQuery_;
    HANDLE sharedHandle_{};
    int width_{};
    int height_{};
    DXGI_FORMAT format_{DXGI_FORMAT_UNKNOWN};
    std::int64_t copiedSequence_{-1};

    bool OpenResource(
        ID3D11Device* device,
        HANDLE sharedHandle,
        int width,
        int height,
        DXGI_FORMAT format) {

        Reset();

        ComPtr<ID3D11Texture2D> shared;
        const HRESULT open = device->OpenSharedResource(
            sharedHandle,
            __uuidof(ID3D11Texture2D),
            reinterpret_cast<void**>(shared.GetAddressOf()));
        if (FAILED(open) || !shared) {
            Log("OpenSharedResource(GPU cache) failed HRESULT=" +
                std::to_string(static_cast<long long>(open)));
            return false;
        }

        D3D11_TEXTURE2D_DESC sharedDesc{};
        shared->GetDesc(&sharedDesc);
        if (static_cast<int>(sharedDesc.Width) != width ||
            static_cast<int>(sharedDesc.Height) != height ||
            sharedDesc.Format != format) {
            Log("Shared GPU texture metadata mismatch");
            return false;
        }

        ComPtr<IDXGIKeyedMutex> mutex;
        const HRESULT mutexHr = shared.As(&mutex);
        if (FAILED(mutexHr) || !mutex) {
            Log("Query IDXGIKeyedMutex failed HRESULT=" +
                std::to_string(static_cast<long long>(mutexHr)));
            return false;
        }

        D3D11_TEXTURE2D_DESC localDesc{};
        localDesc.Width = sharedDesc.Width;
        localDesc.Height = sharedDesc.Height;
        localDesc.MipLevels = 1;
        localDesc.ArraySize = 1;
        localDesc.Format = sharedDesc.Format;
        localDesc.SampleDesc.Count = 1;
        localDesc.SampleDesc.Quality = 0;
        localDesc.Usage = D3D11_USAGE_DEFAULT;
        localDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        localDesc.CPUAccessFlags = 0;
        localDesc.MiscFlags = 0;

        ComPtr<ID3D11Texture2D> local;
        const HRESULT localHr = device->CreateTexture2D(
            &localDesc, nullptr, &local);
        if (FAILED(localHr) || !local) {
            Log("CreateTexture2D(GPU cache) failed HRESULT=" +
                std::to_string(static_cast<long long>(localHr)));
            return false;
        }

        D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
        srvDesc.Format = localDesc.Format;
        srvDesc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
        srvDesc.Texture2D.MostDetailedMip = 0;
        srvDesc.Texture2D.MipLevels = 1;

        ComPtr<ID3D11ShaderResourceView> srv;
        const HRESULT srvHr = device->CreateShaderResourceView(
            local.Get(), &srvDesc, &srv);
        if (FAILED(srvHr) || !srv) {
            Log("CreateShaderResourceView(GPU cache) failed HRESULT=" +
                std::to_string(static_cast<long long>(srvHr)));
            return false;
        }

        D3D11_QUERY_DESC queryDesc{};
        queryDesc.Query = D3D11_QUERY_EVENT;
        queryDesc.MiscFlags = 0;
        ComPtr<ID3D11Query> query;
        const HRESULT queryHr = device->CreateQuery(&queryDesc, &query);
        if (FAILED(queryHr) || !query) {
            Log("CreateQuery(GPU cache) failed HRESULT=" +
                std::to_string(static_cast<long long>(queryHr)));
            return false;
        }

        sharedTexture_ = shared;
        mutex_ = mutex;
        localTexture_ = local;
        srv_ = srv;
        copyQuery_ = query;
        sharedHandle_ = sharedHandle;
        width_ = width;
        height_ = height;
        format_ = format;
        copiedSequence_ = -1;
        return true;
    }
};

} // namespace ggqv13
