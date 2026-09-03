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

class SharedGpuTextureView {
public:
    void Reset() {
        locked_ = false;
        srv_.Reset();
        mutex_.Reset();
        texture_.Reset();
        sharedHandle_ = nullptr;
        width_ = 0;
        height_ = 0;
        format_ = DXGI_FORMAT_UNKNOWN;
    }

    bool Update(
        ID3D11Device* device,
        bool active,
        HANDLE sharedHandle,
        int width,
        int height,
        DXGI_FORMAT format) {

        if (!active || !sharedHandle || width < 2 || height < 2) {
            Reset();
            return false;
        }

        if (texture_ && sharedHandle_ == sharedHandle &&
            width_ == width && height_ == height && format_ == format) {
            return true;
        }

        Reset();

        ComPtr<ID3D11Texture2D> texture;
        const HRESULT open = device->OpenSharedResource(
            sharedHandle,
            __uuidof(ID3D11Texture2D),
            reinterpret_cast<void**>(texture.GetAddressOf()));
        if (FAILED(open) || !texture) {
            Log("OpenSharedResource(GPU view) failed HRESULT=" +
                std::to_string(static_cast<long long>(open)));
            return false;
        }

        D3D11_TEXTURE2D_DESC desc{};
        texture->GetDesc(&desc);
        if (static_cast<int>(desc.Width) != width ||
            static_cast<int>(desc.Height) != height ||
            desc.Format != format) {
            Log("Shared GPU texture metadata mismatch");
            return false;
        }

        ComPtr<IDXGIKeyedMutex> mutex;
        const HRESULT mutexHr = texture.As(&mutex);
        if (FAILED(mutexHr) || !mutex) {
            Log("Query IDXGIKeyedMutex failed HRESULT=" +
                std::to_string(static_cast<long long>(mutexHr)));
            return false;
        }

        D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
        srvDesc.Format = desc.Format;
        srvDesc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
        srvDesc.Texture2D.MostDetailedMip = 0;
        srvDesc.Texture2D.MipLevels = 1;

        ComPtr<ID3D11ShaderResourceView> srv;
        const HRESULT srvHr = device->CreateShaderResourceView(
            texture.Get(), &srvDesc, &srv);
        if (FAILED(srvHr) || !srv) {
            Log("CreateShaderResourceView(shared GPU) failed HRESULT=" +
                std::to_string(static_cast<long long>(srvHr)));
            return false;
        }

        texture_ = texture;
        mutex_ = mutex;
        srv_ = srv;
        sharedHandle_ = sharedHandle;
        width_ = width;
        height_ = height;
        format_ = format;
        return true;
    }

    bool Acquire() {
        if (!mutex_ || !srv_ || locked_) return false;
        const HRESULT hr = mutex_->AcquireSync(1, 0);
        if (hr == WAIT_TIMEOUT) return false;
        if (FAILED(hr)) {
            Log("AcquireSync(shared GPU,key=1) failed HRESULT=" +
                std::to_string(static_cast<long long>(hr)));
            return false;
        }
        locked_ = true;
        return true;
    }

    void Release() {
        if (!locked_ || !mutex_) return;
        const HRESULT hr = mutex_->ReleaseSync(0);
        if (FAILED(hr)) {
            Log("ReleaseSync(shared GPU,key=0) failed HRESULT=" +
                std::to_string(static_cast<long long>(hr)));
        }
        locked_ = false;
    }

    bool Valid() const { return srv_ != nullptr; }
    ID3D11ShaderResourceView* Srv() const { return srv_.Get(); }
    int Width() const { return width_; }
    int Height() const { return height_; }

private:
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<IDXGIKeyedMutex> mutex_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    HANDLE sharedHandle_{};
    int width_{};
    int height_{};
    DXGI_FORMAT format_{DXGI_FORMAT_UNKNOWN};
    bool locked_{};
};

} // namespace ggqv13
