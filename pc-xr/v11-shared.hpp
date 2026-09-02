#pragma once
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <dxgi.h>
#include <wrl/client.h>
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using Microsoft::WRL::ComPtr;


namespace ggqv11 {


constexpr wchar_t kGpuMapName[] = L"Local\\GeoGebraForQuestPC_A_GPU_v1";
constexpr std::int32_t kGpuMagic = 0x47514147;
constexpr std::int32_t kGpuProtocolVersion = 1;
constexpr std::size_t kGpuMappingSize = 64;

constexpr wchar_t kSbsMapName[] = L"Local\\GeoGebraForQuestPC_SBS_v2";
constexpr std::int32_t kSbsMagic = 0x47515342;
constexpr std::int32_t kSbsProtocolVersion = 2;
constexpr std::size_t kSbsHeaderSize = 128;
constexpr int kMaxEyeWidth = 2048;
constexpr int kMaxEyeHeight = 2048;
constexpr int kMaxSbsWidth = kMaxEyeWidth * 2;
constexpr std::size_t kMaxSbsBytes =
    static_cast<std::size_t>(kMaxSbsWidth) * kMaxEyeHeight * 4;
constexpr std::size_t kSbsOffset = kSbsHeaderSize;
constexpr std::size_t kSbsMappingSize = kSbsHeaderSize + kMaxSbsBytes;

constexpr wchar_t kInputMapName[] = L"Local\\GeoGebraForQuestPC_Input_v1";
constexpr std::int32_t kInputMagic = 0x4751494E;
constexpr std::int32_t kInputProtocolVersion = 1;
constexpr std::size_t kInputMappingSize = 64;

constexpr float kScreenWidthMeters = 1.65f;
constexpr float kScreenDistanceMeters = 1.55f;
constexpr float kStereoDistanceMeters = 1.53f;
constexpr float kCursorDistanceMeters = 1.515f;
constexpr float kCursorSizeMeters = 0.018f;
constexpr float kNearDepthMeters = 0.05f;
constexpr float kTriggerThreshold = 0.55f;

std::ofstream gLog;

void Log(const std::string& text) {
    if (!gLog.is_open()) {
        char path[MAX_PATH]{};
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        std::string file(path);
        const auto slash = file.find_last_of("\\/");
        if (slash != std::string::npos) {
            file.resize(slash + 1);
        }
        file += "GeoGebraForQuestPC.XR.log";
        gLog.open(file, std::ios::out | std::ios::app);
    }
    if (gLog.is_open()) {
        gLog << text << std::endl;
        gLog.flush();
    }
}

[[noreturn]] void ThrowXr(XrResult result, const char* where) {
    throw std::runtime_error(
        std::string(where) + " failed, XrResult=" + std::to_string(result));
}

void CheckXr(XrResult result, const char* where) {
    if (XR_FAILED(result)) {
        ThrowXr(result, where);
    }
}

void CheckHr(HRESULT result, const char* where) {
    if (FAILED(result)) {
        throw std::runtime_error(
            std::string(where) + " failed, HRESULT=" +
            std::to_string(static_cast<long long>(result)));
    }
}

bool LuidEqual(const LUID& a, const LUID& b) {
    return a.LowPart == b.LowPart && a.HighPart == b.HighPart;
}

DWORD ParsePid(int argc, wchar_t** argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::wstring(argv[i]) == L"--pid") {
            return static_cast<DWORD>(std::wcstoul(argv[i + 1], nullptr, 10));
        }
    }
    return 0;
}

bool ProcessAlive(DWORD pid) {
    HANDLE process = OpenProcess(SYNCHRONIZE, FALSE, pid);
    if (!process) {
        return false;
    }
    const DWORD state = WaitForSingleObject(process, 0);
    CloseHandle(process);
    return state == WAIT_TIMEOUT;
}

const char* SessionStateName(XrSessionState state) {
    switch (state) {
        case XR_SESSION_STATE_UNKNOWN: return "UNKNOWN";
        case XR_SESSION_STATE_IDLE: return "IDLE";
        case XR_SESSION_STATE_READY: return "READY";
        case XR_SESSION_STATE_SYNCHRONIZED: return "SYNCHRONIZED";
        case XR_SESSION_STATE_VISIBLE: return "VISIBLE";
        case XR_SESSION_STATE_FOCUSED: return "FOCUSED";
        case XR_SESSION_STATE_STOPPING: return "STOPPING";
        case XR_SESSION_STATE_LOSS_PENDING: return "LOSS_PENDING";
        case XR_SESSION_STATE_EXITING: return "EXITING";
        default: return "OTHER";
    }
}

std::int32_t ReadI32(const std::uint8_t* base, std::size_t offset) {
    std::int32_t value{};
    std::memcpy(&value, base + offset, sizeof(value));
    return value;
}

std::int64_t ReadI64(const std::uint8_t* base, std::size_t offset) {
    std::int64_t value{};
    std::memcpy(&value, base + offset, sizeof(value));
    return value;
}

float ReadF32(const std::uint8_t* base, std::size_t offset) {
    float value{};
    std::memcpy(&value, base + offset, sizeof(value));
    return value;
}

void WriteI32(std::uint8_t* base, std::size_t offset, std::int32_t value) {
    std::memcpy(base + offset, &value, sizeof(value));
}

void WriteI64(std::uint8_t* base, std::size_t offset, std::int64_t value) {
    std::memcpy(base + offset, &value, sizeof(value));
}

void WriteF32(std::uint8_t* base, std::size_t offset, float value) {
    std::memcpy(base + offset, &value, sizeof(value));
}

struct GpuFrameInfo {
    std::int64_t sequence{};
    bool active{};
    int width{};
    int height{};
    DXGI_FORMAT format{DXGI_FORMAT_UNKNOWN};
    HANDLE sharedHandle{};
};

class GpuFrameInfoReader {
public:
    ~GpuFrameInfoReader() {
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    bool ReadIfChanged(std::int64_t previousSequence, GpuFrameInfo& out) {
        if (!view_ && !Open()) {
            return false;
        }

        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadI64(view_, 8);
            if ((first & 1) != 0) {
                std::this_thread::yield();
                continue;
            }
            if (first == previousSequence) {
                return false;
            }

            GpuFrameInfo candidate{};
            candidate.sequence = first;
            candidate.active = ReadI32(view_, 16) != 0;
            candidate.width = ReadI32(view_, 20);
            candidate.height = ReadI32(view_, 24);
            candidate.format = static_cast<DXGI_FORMAT>(ReadI32(view_, 28));
            const auto handle64 = ReadI64(view_, 32);
            candidate.sharedHandle = reinterpret_cast<HANDLE>(
                static_cast<std::intptr_t>(handle64));

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
        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kGpuMapName);
        if (!mapping_) {
            return false;
        }
        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kGpuMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            return false;
        }
        if (ReadI32(view_, 0) != kGpuMagic ||
            ReadI32(view_, 4) != kGpuProtocolVersion) {
            UnmapViewOfFile(view_);
            CloseHandle(mapping_);
            view_ = nullptr;
            mapping_ = nullptr;
            return false;
        }
        Log("A GPU metadata mapping opened");
        return true;
    }
};

struct SbsSnapshot {
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
    int sbsStride{};
    std::int32_t frameNumber{};
    std::vector<std::uint8_t> sbs;
};

class SharedSbsReader {
public:
    ~SharedSbsReader() {
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    bool ReadIfChanged(std::int64_t previousSequence, SbsSnapshot& out) {
        if (!view_ && !Open()) {
            return false;
        }

        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadI64(view_, 8);
            if ((first & 1) != 0) {
                std::this_thread::yield();
                continue;
            }
            if (first == previousSequence) {
                return false;
            }

            SbsSnapshot candidate{};
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
            candidate.sbsStride = ReadI32(view_, 52);
            candidate.frameNumber = ReadI32(view_, 56);

            const bool valid =
                candidate.active &&
                candidate.clientWidth > 1 &&
                candidate.clientHeight > 1 &&
                candidate.panelWidth > 1 &&
                candidate.panelHeight > 1 &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4;

            if (valid) {
                const std::size_t bytes =
                    static_cast<std::size_t>(candidate.sbsStride) *
                    static_cast<std::size_t>(candidate.eyeHeight);
                if (bytes <= kMaxSbsBytes) {
                    candidate.sbs.resize(bytes);
                    std::memcpy(candidate.sbs.data(), view_ + kSbsOffset, bytes);
                }
            }

            MemoryBarrier();
            const auto second = ReadI64(view_, 8);
            if (first == second && (second & 1) == 0) {
                out = std::move(candidate);
                return true;
            }
        }
        return false;
    }

private:
    HANDLE mapping_{};
    std::uint8_t* view_{};

    bool Open() {
        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kSbsMapName);
        if (!mapping_) {
            return false;
        }
        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kSbsMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            return false;
        }
        if (ReadI32(view_, 0) != kSbsMagic ||
            ReadI32(view_, 4) != kSbsProtocolVersion) {
            UnmapViewOfFile(view_);
            CloseHandle(mapping_);
            view_ = nullptr;
            mapping_ = nullptr;
            return false;
        }
        Log("B SBS mapping opened read-only safely");
        return true;
    }
};

class XrInputWriter {
public:
    ~XrInputWriter() {
        Publish(false, 0.0f, 0.0f, false);
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    void Initialize() {
        if (view_) {
            return;
        }
        mapping_ = CreateFileMappingW(
            INVALID_HANDLE_VALUE,
            nullptr,
            PAGE_READWRITE,
            0,
            static_cast<DWORD>(kInputMappingSize),
            kInputMapName);
        if (!mapping_) {
            throw std::runtime_error("CreateFileMapping(input) failed");
        }
        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_ALL_ACCESS, 0, 0, kInputMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            throw std::runtime_error("MapViewOfFile(input) failed");
        }
        WriteI32(view_, 0, kInputMagic);
        WriteI32(view_, 4, kInputProtocolVersion);
        WriteI64(view_, 8, 0);
        WriteI32(view_, 16, 0);
        WriteF32(view_, 20, 0.0f);
        WriteF32(view_, 24, 0.0f);
        WriteI32(view_, 28, 0);
        FlushViewOfFile(view_, kInputMappingSize);
    }

    void Publish(bool valid, float u, float v, bool triggerDown) {
        if (!view_) {
            return;
        }
        sequence_ += 2;
        WriteI64(view_, 8, sequence_ - 1);
        WriteI32(view_, 16, valid ? 1 : 0);
        WriteF32(view_, 20, u);
        WriteF32(view_, 24, v);
        WriteI32(view_, 28, triggerDown ? 1 : 0);
        MemoryBarrier();
        WriteI64(view_, 8, sequence_);
    }

private:
    HANDLE mapping_{};
    std::uint8_t* view_{};
    std::int64_t sequence_{};
};

class SourceTexture {
public:
    void Reset() {
        srv_.Reset();
        texture_.Reset();
        width_ = 0;
        height_ = 0;
    }

    void Upload(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        const std::uint8_t* pixels,
        int width,
        int height,
        int rowPitch) {

        if (!pixels || width < 1 || height < 1 || rowPitch < width * 4) {
            return;
        }
        if (!texture_ || width != width_ || height != height_) {
            Reset();
            D3D11_TEXTURE2D_DESC desc{};
            desc.Width = static_cast<UINT>(width);
            desc.Height = static_cast<UINT>(height);
            desc.MipLevels = 1;
            desc.ArraySize = 1;
            desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
            desc.SampleDesc.Count = 1;
            desc.Usage = D3D11_USAGE_DEFAULT;
            desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
            CheckHr(device->CreateTexture2D(&desc, nullptr, &texture_), "CreateTexture2D(source)");
            CheckHr(device->CreateShaderResourceView(texture_.Get(), nullptr, &srv_),
                "CreateShaderResourceView(source)");
            width_ = width;
            height_ = height;
        }
        context->UpdateSubresource(
            texture_.Get(), 0, nullptr, pixels, static_cast<UINT>(rowPitch), 0);
    }

    ID3D11ShaderResourceView* Srv() const { return srv_.Get(); }
    bool Valid() const { return srv_ != nullptr; }

private:
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    int width_{};
    int height_{};
};

class SharedGpuTextureConsumer {
public:
    void Initialize(ID3D11Device* device) {
        D3D11_QUERY_DESC queryDesc{};
        queryDesc.Query = D3D11_QUERY_EVENT;
        CheckHr(device->CreateQuery(&queryDesc, &copyQuery_), "CreateQuery(A GPU copy)");
    }

    bool Update(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        const GpuFrameInfo& info) {

        if (!info.active || !info.sharedHandle || info.width < 2 || info.height < 2) {
            return false;
        }

        if (info.sharedHandle != currentHandle_) {
            sharedMutex_.Reset();
            sharedTexture_.Reset();
            currentHandle_ = nullptr;

            ComPtr<ID3D11Resource> resource;
            HRESULT hr = device->OpenSharedResource(
                info.sharedHandle,
                __uuidof(ID3D11Resource),
                reinterpret_cast<void**>(resource.GetAddressOf()));
            if (FAILED(hr)) {
                Log("OpenSharedResource(A) failed HRESULT=" +
                    std::to_string(static_cast<long long>(hr)));
                return false;
            }
            CheckHr(resource.As(&sharedTexture_), "Query ID3D11Texture2D(A shared)");
            CheckHr(sharedTexture_.As(&sharedMutex_), "Query IDXGIKeyedMutex(A shared)");
            currentHandle_ = info.sharedHandle;
            Log("Opened new A GPU shared texture handle");
        }

        D3D11_TEXTURE2D_DESC sharedDesc{};
        sharedTexture_->GetDesc(&sharedDesc);
        if (static_cast<int>(sharedDesc.Width) != info.width ||
            static_cast<int>(sharedDesc.Height) != info.height) {
            return false;
        }

        if (!localTexture_ ||
            localWidth_ != info.width ||
            localHeight_ != info.height ||
            localFormat_ != sharedDesc.Format) {

            localSrv_.Reset();
            localTexture_.Reset();
            D3D11_TEXTURE2D_DESC localDesc = sharedDesc;
            localDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
            localDesc.MiscFlags = 0;
            localDesc.CPUAccessFlags = 0;
            localDesc.Usage = D3D11_USAGE_DEFAULT;
            CheckHr(device->CreateTexture2D(&localDesc, nullptr, &localTexture_),
                "CreateTexture2D(A local)");
            CheckHr(device->CreateShaderResourceView(localTexture_.Get(), nullptr, &localSrv_),
                "CreateShaderResourceView(A local)");
            localWidth_ = info.width;
            localHeight_ = info.height;
            localFormat_ = sharedDesc.Format;
        }

        const HRESULT acquire = sharedMutex_->AcquireSync(1, 0);
        if (acquire == WAIT_TIMEOUT) {
            return false;
        }
        if (FAILED(acquire)) {
            Log("AcquireSync(A,key=1) failed HRESULT=" +
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
                const HRESULT copyStatus = context->GetData(
                    copyQuery_.Get(), &copyDone, sizeof(copyDone), 0);
                if (copyStatus == S_OK && copyDone != FALSE) {
                    break;
                }
                if (FAILED(copyStatus)) {
                    CheckHr(copyStatus, "GetData(A GPU copy)");
                }
                std::this_thread::yield();
            }
            CheckHr(sharedMutex_->ReleaseSync(0), "ReleaseSync(A,key=0)");
            releaseNeeded = false;
        } catch (...) {
            if (releaseNeeded) {
                sharedMutex_->ReleaseSync(0);
            }
            throw;
        }
        return true;
    }

    ID3D11ShaderResourceView* Srv() const { return localSrv_.Get(); }
    bool Valid() const { return localSrv_ != nullptr; }
    int Width() const { return localWidth_; }
    int Height() const { return localHeight_; }

private:
    HANDLE currentHandle_{};
    ComPtr<ID3D11Texture2D> sharedTexture_;
    ComPtr<IDXGIKeyedMutex> sharedMutex_;
    ComPtr<ID3D11Texture2D> localTexture_;
    ComPtr<ID3D11ShaderResourceView> localSrv_;
    ComPtr<ID3D11Query> copyQuery_;
    int localWidth_{};
    int localHeight_{};
    DXGI_FORMAT localFormat_{DXGI_FORMAT_UNKNOWN};
};


} // namespace ggqv11
