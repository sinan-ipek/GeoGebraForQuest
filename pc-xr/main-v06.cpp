#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <dxgi1_2.h>
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
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {

constexpr wchar_t kSbsMapName[] = L"Local\\GeoGebraForQuestPC_SBS_v2";
constexpr std::int32_t kMagic = 0x47515342;
constexpr std::int32_t kProtocolVersion = 2;
constexpr std::size_t kHeaderSize = 128;
constexpr int kMaxEyeWidth = 2048;
constexpr int kMaxEyeHeight = 2048;
constexpr int kMaxSbsWidth = kMaxEyeWidth * 2;
constexpr std::size_t kMaxSbsBytes =
    static_cast<std::size_t>(kMaxSbsWidth) * kMaxEyeHeight * 4;
constexpr std::size_t kSbsOffset = kHeaderSize;
constexpr std::size_t kMappingSize = kHeaderSize + kMaxSbsBytes;

constexpr float kPanelWidthMeters = 1.80f;
constexpr float kPanelDistanceMeters = 1.60f;
constexpr float kNearDepthMeters = 0.05f;

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

struct FindWindowData {
    DWORD pid{};
    HWND best{};
    long long bestArea{};
};

BOOL CALLBACK EnumWindowForPid(HWND hwnd, LPARAM param) {
    auto* data = reinterpret_cast<FindWindowData*>(param);

    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (pid != data->pid || !IsWindowVisible(hwnd)) {
        return TRUE;
    }

    RECT client{};
    if (!GetClientRect(hwnd, &client)) {
        return TRUE;
    }

    const long width = client.right - client.left;
    const long height = client.bottom - client.top;
    const long long area = static_cast<long long>(width) * height;

    if (width < 400 || height < 300 || area <= data->bestArea) {
        return TRUE;
    }

    data->best = hwnd;
    data->bestArea = area;
    return TRUE;
}

HWND FindMainWindow(DWORD pid) {
    FindWindowData data{};
    data.pid = pid;
    EnumWindows(EnumWindowForPid, reinterpret_cast<LPARAM>(&data));
    return data.best;
}

class WindowCapture {
public:
    ~WindowCapture() {
        ResetBitmap();
        if (memDc_) {
            DeleteDC(memDc_);
        }
        if (screenDc_) {
            ReleaseDC(nullptr, screenDc_);
        }
    }

    bool Capture(
        HWND hwnd,
        std::vector<std::uint8_t>& out,
        int& width,
        int& height) {

        RECT client{};
        if (!GetClientRect(hwnd, &client)) {
            return false;
        }

        POINT origin{0, 0};
        if (!ClientToScreen(hwnd, &origin)) {
            return false;
        }

        width = client.right - client.left;
        height = client.bottom - client.top;
        if (width < 2 || height < 2) {
            return false;
        }

        if (!EnsureBitmap(width, height)) {
            return false;
        }

        if (!BitBlt(
                memDc_,
                0,
                0,
                width,
                height,
                screenDc_,
                origin.x,
                origin.y,
                SRCCOPY | CAPTUREBLT)) {
            return false;
        }

        const std::size_t bytes =
            static_cast<std::size_t>(width) *
            static_cast<std::size_t>(height) * 4;
        out.resize(bytes);
        std::memcpy(out.data(), bits_, bytes);
        return true;
    }

private:
    HDC screenDc_{};
    HDC memDc_{};
    HBITMAP bitmap_{};
    HGDIOBJ oldObject_{};
    void* bits_{};
    int width_{};
    int height_{};

    bool EnsureBitmap(int width, int height) {
        if (bitmap_ && width == width_ && height == height_) {
            return true;
        }

        ResetBitmap();

        if (!screenDc_) {
            screenDc_ = GetDC(nullptr);
        }
        if (!screenDc_) {
            return false;
        }

        if (!memDc_) {
            memDc_ = CreateCompatibleDC(screenDc_);
        }
        if (!memDc_) {
            return false;
        }

        BITMAPINFO info{};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = width;
        info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;

        bitmap_ = CreateDIBSection(
            screenDc_,
            &info,
            DIB_RGB_COLORS,
            &bits_,
            nullptr,
            0);

        if (!bitmap_ || !bits_) {
            ResetBitmap();
            return false;
        }

        oldObject_ = SelectObject(memDc_, bitmap_);
        width_ = width;
        height_ = height;
        return true;
    }

    void ResetBitmap() {
        if (memDc_ && oldObject_) {
            SelectObject(memDc_, oldObject_);
            oldObject_ = nullptr;
        }

        if (bitmap_) {
            DeleteObject(bitmap_);
            bitmap_ = nullptr;
        }

        bits_ = nullptr;
        width_ = 0;
        height_ = 0;
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
        if (view_) {
            UnmapViewOfFile(view_);
        }
        if (mapping_) {
            CloseHandle(mapping_);
        }
    }

    bool Open() {
        if (view_) {
            return true;
        }

        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kSbsMapName);
        if (!mapping_) {
            return false;
        }

        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kMappingSize));
        if (!view_) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
            return false;
        }

        if (ReadI32(0) != kMagic || ReadI32(4) != kProtocolVersion) {
            UnmapViewOfFile(view_);
            CloseHandle(mapping_);
            view_ = nullptr;
            mapping_ = nullptr;
            return false;
        }

        return true;
    }

    bool Read(SbsSnapshot& snapshot) {
        if (!view_ && !Open()) {
            return false;
        }

        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadSequence();
            if (first & 1) {
                std::this_thread::yield();
                continue;
            }

            SbsSnapshot candidate{};
            candidate.sequence = first;
            candidate.active = ReadI32(16) != 0;
            candidate.clientWidth = ReadI32(20);
            candidate.clientHeight = ReadI32(24);
            candidate.panelLeft = ReadI32(28);
            candidate.panelTop = ReadI32(32);
            candidate.panelWidth = ReadI32(36);
            candidate.panelHeight = ReadI32(40);
            candidate.eyeWidth = ReadI32(44);
            candidate.eyeHeight = ReadI32(48);
            candidate.sbsStride = ReadI32(52);
            candidate.frameNumber = ReadI32(56);

            const bool validSbs =
                candidate.active &&
                candidate.eyeWidth > 1 &&
                candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 &&
                candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4;

            if (validSbs) {
                const std::size_t bytes =
                    static_cast<std::size_t>(candidate.sbsStride) *
                    static_cast<std::size_t>(candidate.eyeHeight);

                if (bytes <= kMaxSbsBytes) {
                    candidate.sbs.resize(bytes);
                    std::memcpy(
                        candidate.sbs.data(),
                        view_ + kSbsOffset,
                        bytes);
                }
            }

            MemoryBarrier();
            const auto second = ReadSequence();
            if (first == second && !(second & 1)) {
                snapshot = std::move(candidate);
                return true;
            }
        }

        return false;
    }

private:
    HANDLE mapping_{};
    std::uint8_t* view_{};

    std::int32_t ReadI32(std::size_t offset) const {
        std::int32_t value{};
        std::memcpy(&value, view_ + offset, sizeof(value));
        return value;
    }

    std::int64_t ReadSequence() const {
        auto* address = reinterpret_cast<volatile LONG64*>(view_ + 8);
        return static_cast<std::int64_t>(
            InterlockedCompareExchange64(address, 0, 0));
    }
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

        if (!pixels || width < 2 || height < 2 || rowPitch < width * 4) {
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

            CheckHr(
                device->CreateTexture2D(
                    &desc,
                    nullptr,
                    texture_.ReleaseAndGetAddressOf()),
                "CreateTexture2D(source)");

            D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
            srvDesc.Format = desc.Format;
            srvDesc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
            srvDesc.Texture2D.MostDetailedMip = 0;
            srvDesc.Texture2D.MipLevels = 1;

            CheckHr(
                device->CreateShaderResourceView(
                    texture_.Get(),
                    &srvDesc,
                    srv_.ReleaseAndGetAddressOf()),
                "CreateShaderResourceView(source)");

            width_ = width;
            height_ = height;
        }

        context->UpdateSubresource(
            texture_.Get(),
            0,
            nullptr,
            pixels,
            static_cast<UINT>(rowPitch),
            0);
    }

    ID3D11ShaderResourceView* Srv() const {
        return srv_.Get();
    }

    bool Valid() const {
        return srv_ != nullptr;
    }

private:
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    int width_{};
    int height_{};
};

class ProjectionSwapchain {
public:
    ~ProjectionSwapchain() {
        Reset();
    }

    void Reset() {
        images_.clear();
        if (handle_ != XR_NULL_HANDLE) {
            xrDestroySwapchain(handle_);
            handle_ = XR_NULL_HANDLE;
        }
        width_ = 0;
        height_ = 0;
    }

    void Create(
        XrSession session,
        std::int64_t format,
        int width,
        int height) {

        Reset();

        XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
        info.createFlags = 0;
        info.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
        info.format = format;
        info.sampleCount = 1;
        info.width = static_cast<std::uint32_t>(width);
        info.height = static_cast<std::uint32_t>(height);
        info.faceCount = 1;
        info.arraySize = 2;
        info.mipCount = 1;

        CheckXr(
            xrCreateSwapchain(session, &info, &handle_),
            "xrCreateSwapchain(projection)");

        std::uint32_t count = 0;
        CheckXr(
            xrEnumerateSwapchainImages(handle_, 0, &count, nullptr),
            "xrEnumerateSwapchainImages(count)");

        images_.resize(count);
        for (auto& image : images_) {
            image = {XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR};
        }

        CheckXr(
            xrEnumerateSwapchainImages(
                handle_,
                count,
                &count,
                reinterpret_cast<XrSwapchainImageBaseHeader*>(images_.data())),
            "xrEnumerateSwapchainImages(images)");

        width_ = width;
        height_ = height;
    }

    std::uint32_t Acquire() {
        std::uint32_t index = 0;
        XrSwapchainImageAcquireInfo acquire{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
        CheckXr(
            xrAcquireSwapchainImage(handle_, &acquire, &index),
            "xrAcquireSwapchainImage(projection)");

        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(
            xrWaitSwapchainImage(handle_, &wait),
            "xrWaitSwapchainImage(projection)");

        return index;
    }

    void Release() {
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(
            xrReleaseSwapchainImage(handle_, &release),
            "xrReleaseSwapchainImage(projection)");
    }

    ID3D11Texture2D* Texture(std::uint32_t index) const {
        return images_.at(index).texture;
    }

    XrSwapchain Handle() const {
        return handle_;
    }

    int Width() const {
        return width_;
    }

    int Height() const {
        return height_;
    }

private:
    XrSwapchain handle_{XR_NULL_HANDLE};
    std::vector<XrSwapchainImageD3D11KHR> images_;
    int width_{};
    int height_{};
};

struct Vec3 {
    float x{};
    float y{};
    float z{};
};

Vec3 Cross(const Vec3& a, const Vec3& b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x};
}

Vec3 Add(const Vec3& a, const Vec3& b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

Vec3 Scale(const Vec3& v, float s) {
    return {v.x * s, v.y * s, v.z * s};
}

Vec3 RotateByQuaternion(const XrQuaternionf& q, const Vec3& v) {
    const Vec3 qv{q.x, q.y, q.z};
    const Vec3 t = Scale(Cross(qv, v), 2.0f);
    return Add(v, Add(Scale(t, q.w), Cross(qv, t)));
}

Vec3 WorldToView(const XrPosef& eyePose, const Vec3& world) {
    const Vec3 translated{
        world.x - eyePose.position.x,
        world.y - eyePose.position.y,
        world.z - eyePose.position.z};

    const XrQuaternionf inverse{
        -eyePose.orientation.x,
        -eyePose.orientation.y,
        -eyePose.orientation.z,
        eyePose.orientation.w};

    return RotateByQuaternion(inverse, translated);
}

struct Vertex {
    float x{};
    float y{};
    float z{};
    float w{};
    float u{};
    float v{};
};

Vertex ProjectVertex(
    const XrView& view,
    const Vec3& world,
    float u,
    float v) {

    const Vec3 p = WorldToView(view.pose, world);
    const float depth = std::max(kNearDepthMeters, -p.z);

    const float tanLeft = std::tan(view.fov.angleLeft);
    const float tanRight = std::tan(view.fov.angleRight);
    const float tanDown = std::tan(view.fov.angleDown);
    const float tanUp = std::tan(view.fov.angleUp);

    const float horizontal = std::max(0.001f, tanRight - tanLeft);
    const float vertical = std::max(0.001f, tanUp - tanDown);

    const float clipX =
        (2.0f * p.x / horizontal) -
        (depth * (tanRight + tanLeft) / horizontal);

    const float clipY =
        (2.0f * p.y / vertical) -
        (depth * (tanUp + tanDown) / vertical);

    return {
        clipX,
        clipY,
        depth * 0.5f,
        depth,
        u,
        v};
}

struct PanelRect {
    float left{};
    float right{};
    float top{};
    float bottom{};
};

class ProjectionRenderer {
public:
    void Initialize(ID3D11Device* device) {
        static const char* shaderSource = R"(
            Texture2D panelTexture : register(t0);
            SamplerState panelSampler : register(s0);

            struct VSInput {
                float4 position : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct PSInput {
                float4 position : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            PSInput VSMain(VSInput input) {
                PSInput output;
                output.position = input.position;
                output.uv = input.uv;
                return output;
            }

            float4 PSMain(PSInput input) : SV_TARGET {
                return panelTexture.Sample(panelSampler, input.uv);
            }
        )";

        ComPtr<ID3DBlob> vertexBlob;
        ComPtr<ID3DBlob> pixelBlob;
        ComPtr<ID3DBlob> errors;

        HRESULT hr = D3DCompile(
            shaderSource,
            std::strlen(shaderSource),
            "GeoGebraForQuestPC-v0.6",
            nullptr,
            nullptr,
            "VSMain",
            "vs_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS,
            0,
            vertexBlob.ReleaseAndGetAddressOf(),
            errors.ReleaseAndGetAddressOf());

        if (FAILED(hr)) {
            const std::string detail =
                errors && errors->GetBufferPointer()
                    ? std::string(
                          static_cast<const char*>(errors->GetBufferPointer()),
                          errors->GetBufferSize())
                    : "unknown vertex shader error";
            throw std::runtime_error("D3DCompile VS failed: " + detail);
        }

        errors.Reset();
        hr = D3DCompile(
            shaderSource,
            std::strlen(shaderSource),
            "GeoGebraForQuestPC-v0.6",
            nullptr,
            nullptr,
            "PSMain",
            "ps_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS,
            0,
            pixelBlob.ReleaseAndGetAddressOf(),
            errors.ReleaseAndGetAddressOf());

        if (FAILED(hr)) {
            const std::string detail =
                errors && errors->GetBufferPointer()
                    ? std::string(
                          static_cast<const char*>(errors->GetBufferPointer()),
                          errors->GetBufferSize())
                    : "unknown pixel shader error";
            throw std::runtime_error("D3DCompile PS failed: " + detail);
        }

        CheckHr(
            device->CreateVertexShader(
                vertexBlob->GetBufferPointer(),
                vertexBlob->GetBufferSize(),
                nullptr,
                vertexShader_.ReleaseAndGetAddressOf()),
            "CreateVertexShader");

        CheckHr(
            device->CreatePixelShader(
                pixelBlob->GetBufferPointer(),
                pixelBlob->GetBufferSize(),
                nullptr,
                pixelShader_.ReleaseAndGetAddressOf()),
            "CreatePixelShader");

        const D3D11_INPUT_ELEMENT_DESC layout[] = {
            {
                "POSITION",
                0,
                DXGI_FORMAT_R32G32B32A32_FLOAT,
                0,
                0,
                D3D11_INPUT_PER_VERTEX_DATA,
                0,
            },
            {
                "TEXCOORD",
                0,
                DXGI_FORMAT_R32G32_FLOAT,
                0,
                16,
                D3D11_INPUT_PER_VERTEX_DATA,
                0,
            },
        };

        CheckHr(
            device->CreateInputLayout(
                layout,
                static_cast<UINT>(std::size(layout)),
                vertexBlob->GetBufferPointer(),
                vertexBlob->GetBufferSize(),
                inputLayout_.ReleaseAndGetAddressOf()),
            "CreateInputLayout");

        D3D11_BUFFER_DESC vertexBufferDesc{};
        vertexBufferDesc.ByteWidth = sizeof(Vertex) * 6;
        vertexBufferDesc.Usage = D3D11_USAGE_DYNAMIC;
        vertexBufferDesc.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vertexBufferDesc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

        CheckHr(
            device->CreateBuffer(
                &vertexBufferDesc,
                nullptr,
                vertexBuffer_.ReleaseAndGetAddressOf()),
            "CreateBuffer(vertices)");

        D3D11_SAMPLER_DESC samplerDesc{};
        samplerDesc.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        samplerDesc.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        samplerDesc.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        samplerDesc.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        samplerDesc.MinLOD = 0.0f;
        samplerDesc.MaxLOD = D3D11_FLOAT32_MAX;

        CheckHr(
            device->CreateSamplerState(
                &samplerDesc,
                sampler_.ReleaseAndGetAddressOf()),
            "CreateSamplerState");

        D3D11_RASTERIZER_DESC rasterDesc{};
        rasterDesc.FillMode = D3D11_FILL_SOLID;
        rasterDesc.CullMode = D3D11_CULL_NONE;
        rasterDesc.DepthClipEnable = TRUE;

        CheckHr(
            device->CreateRasterizerState(
                &rasterDesc,
                rasterizer_.ReleaseAndGetAddressOf()),
            "CreateRasterizerState");

        D3D11_BLEND_DESC blendDesc{};
        blendDesc.RenderTarget[0].BlendEnable = FALSE;
        blendDesc.RenderTarget[0].RenderTargetWriteMask =
            D3D11_COLOR_WRITE_ENABLE_ALL;

        CheckHr(
            device->CreateBlendState(
                &blendDesc,
                blendState_.ReleaseAndGetAddressOf()),
            "CreateBlendState");
    }

    void RenderEye(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        ID3D11Texture2D* target,
        DXGI_FORMAT targetFormat,
        UINT arraySlice,
        int targetWidth,
        int targetHeight,
        const XrView& view,
        ID3D11ShaderResourceView* baseSrv,
        const PanelRect& baseRect,
        ID3D11ShaderResourceView* sbsSrv,
        const PanelRect* stereoRect,
        bool rightEye) {

        D3D11_RENDER_TARGET_VIEW_DESC rtvDesc{};
        rtvDesc.Format = targetFormat;
        rtvDesc.ViewDimension = D3D11_RTV_DIMENSION_TEXTURE2DARRAY;
        rtvDesc.Texture2DArray.MipSlice = 0;
        rtvDesc.Texture2DArray.FirstArraySlice = arraySlice;
        rtvDesc.Texture2DArray.ArraySize = 1;

        ComPtr<ID3D11RenderTargetView> rtv;
        CheckHr(
            device->CreateRenderTargetView(
                target,
                &rtvDesc,
                rtv.ReleaseAndGetAddressOf()),
            "CreateRenderTargetView(projection eye)");

        ID3D11RenderTargetView* targets[] = {rtv.Get()};
        context->OMSetRenderTargets(1, targets, nullptr);

        const float clearColor[4] = {0.015f, 0.015f, 0.020f, 1.0f};
        context->ClearRenderTargetView(rtv.Get(), clearColor);

        D3D11_VIEWPORT viewport{};
        viewport.Width = static_cast<float>(targetWidth);
        viewport.Height = static_cast<float>(targetHeight);
        viewport.MinDepth = 0.0f;
        viewport.MaxDepth = 1.0f;
        context->RSSetViewports(1, &viewport);
        context->RSSetState(rasterizer_.Get());

        const float blendFactor[4] = {0, 0, 0, 0};
        context->OMSetBlendState(
            blendState_.Get(),
            blendFactor,
            0xFFFFFFFFu);

        context->IASetInputLayout(inputLayout_.Get());
        context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);

        const UINT stride = sizeof(Vertex);
        const UINT offset = 0;
        ID3D11Buffer* buffers[] = {vertexBuffer_.Get()};
        context->IASetVertexBuffers(0, 1, buffers, &stride, &offset);

        context->VSSetShader(vertexShader_.Get(), nullptr, 0);
        context->PSSetShader(pixelShader_.Get(), nullptr, 0);

        ID3D11SamplerState* samplers[] = {sampler_.Get()};
        context->PSSetSamplers(0, 1, samplers);

        if (baseSrv) {
            DrawQuad(
                context,
                view,
                baseRect,
                -kPanelDistanceMeters,
                baseSrv,
                0.0f,
                0.0f,
                1.0f,
                1.0f);
        }

        if (sbsSrv && stereoRect) {
            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;

            // B is rendered on the exact same geometric plane as A, just as the
            // successful standalone Quest embedded-stereo build does. Draw order
            // makes B visually replace only the measured 3D Graphics rectangle.
            DrawQuad(
                context,
                view,
                *stereoRect,
                -kPanelDistanceMeters,
                sbsSrv,
                u0,
                0.0f,
                u1,
                1.0f);
        }

        ID3D11ShaderResourceView* nullSrv[] = {nullptr};
        context->PSSetShaderResources(0, 1, nullSrv);
        context->OMSetRenderTargets(0, nullptr, nullptr);
    }

private:
    ComPtr<ID3D11VertexShader> vertexShader_;
    ComPtr<ID3D11PixelShader> pixelShader_;
    ComPtr<ID3D11InputLayout> inputLayout_;
    ComPtr<ID3D11Buffer> vertexBuffer_;
    ComPtr<ID3D11SamplerState> sampler_;
    ComPtr<ID3D11RasterizerState> rasterizer_;
    ComPtr<ID3D11BlendState> blendState_;

    void DrawQuad(
        ID3D11DeviceContext* context,
        const XrView& view,
        const PanelRect& rect,
        float z,
        ID3D11ShaderResourceView* texture,
        float u0,
        float v0,
        float u1,
        float v1) {

        const Vec3 topLeft{rect.left, rect.top, z};
        const Vec3 topRight{rect.right, rect.top, z};
        const Vec3 bottomLeft{rect.left, rect.bottom, z};
        const Vec3 bottomRight{rect.right, rect.bottom, z};

        const std::array<Vertex, 6> vertices = {
            ProjectVertex(view, topLeft, u0, v0),
            ProjectVertex(view, bottomLeft, u0, v1),
            ProjectVertex(view, topRight, u1, v0),
            ProjectVertex(view, topRight, u1, v0),
            ProjectVertex(view, bottomLeft, u0, v1),
            ProjectVertex(view, bottomRight, u1, v1),
        };

        D3D11_MAPPED_SUBRESOURCE mapped{};
        CheckHr(
            context->Map(
                vertexBuffer_.Get(),
                0,
                D3D11_MAP_WRITE_DISCARD,
                0,
                &mapped),
            "Map(vertex buffer)");

        std::memcpy(
            mapped.pData,
            vertices.data(),
            sizeof(vertices));
        context->Unmap(vertexBuffer_.Get(), 0);

        ID3D11ShaderResourceView* srvs[] = {texture};
        context->PSSetShaderResources(0, 1, srvs);
        context->Draw(6, 0);
    }
};

class XrProjectionStereoApp {
public:
    explicit XrProjectionStereoApp(DWORD hostPid)
        : hostPid_(hostPid) {
    }

    ~XrProjectionStereoApp() {
        projectionSwapchain_.Reset();

        if (localSpace_ != XR_NULL_HANDLE) {
            xrDestroySpace(localSpace_);
        }
        if (session_ != XR_NULL_HANDLE) {
            xrDestroySession(session_);
        }
        if (instance_ != XR_NULL_HANDLE) {
            xrDestroyInstance(instance_);
        }
    }

    int Run() {
        InitializeOpenXr();
        InitializeD3D11();
        CreateSessionAndSwapchain();
        renderer_.Initialize(device_.Get());

        Log(
            "PC v0.6 Projection Stereo: OpenXR initialized; "
            "no XrCompositionLayerQuad is used");

        std::vector<std::uint8_t> basePixels;
        int baseWidth = 0;
        int baseHeight = 0;
        auto lastCapture = std::chrono::steady_clock::time_point{};

        SbsSnapshot stereo{};
        std::int64_t lastUploadedSbsSequence = -1;
        std::int64_t lastLoggedSbsSequence = -1;

        while (!exitRequested_ && ProcessAlive(hostPid_)) {
            PollEvents();

            if (!sessionRunning_) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
            XrFrameState frameState{XR_TYPE_FRAME_STATE};
            CheckXr(
                xrWaitFrame(session_, &waitInfo, &frameState),
                "xrWaitFrame");

            XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
            CheckXr(
                xrBeginFrame(session_, &beginInfo),
                "xrBeginFrame");

            XrCompositionLayerProjection projectionLayer{
                XR_TYPE_COMPOSITION_LAYER_PROJECTION};
            std::array<XrCompositionLayerProjectionView, 2> projectionViews{
                XrCompositionLayerProjectionView{
                    XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
                XrCompositionLayerProjectionView{
                    XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            };

            const XrCompositionLayerBaseHeader* submittedLayer = nullptr;

            if (frameState.shouldRender) {
                HWND hostWindow = FindMainWindow(hostPid_);
                if (hostWindow) {
                    const auto now = std::chrono::steady_clock::now();
                    const bool captureDue =
                        lastCapture.time_since_epoch().count() == 0 ||
                        now - lastCapture >= std::chrono::milliseconds(33);

                    if (captureDue &&
                        capture_.Capture(
                            hostWindow,
                            basePixels,
                            baseWidth,
                            baseHeight)) {

                        baseTexture_.Upload(
                            device_.Get(),
                            context_.Get(),
                            basePixels.data(),
                            baseWidth,
                            baseHeight,
                            baseWidth * 4);
                        lastCapture = now;
                    }

                    SbsSnapshot newest{};
                    if (sharedSbs_.Read(newest)) {
                        stereo = std::move(newest);
                    }
                }

                const bool validSbs =
                    stereo.active &&
                    stereo.clientWidth > 1 &&
                    stereo.clientHeight > 1 &&
                    stereo.panelWidth > 1 &&
                    stereo.panelHeight > 1 &&
                    stereo.eyeWidth > 1 &&
                    stereo.eyeWidth <= kMaxEyeWidth &&
                    stereo.eyeHeight > 1 &&
                    stereo.eyeHeight <= kMaxEyeHeight &&
                    stereo.sbsStride == stereo.eyeWidth * 2 * 4 &&
                    !stereo.sbs.empty();

                if (validSbs &&
                    stereo.sequence != lastUploadedSbsSequence) {

                    sbsTexture_.Upload(
                        device_.Get(),
                        context_.Get(),
                        stereo.sbs.data(),
                        stereo.eyeWidth * 2,
                        stereo.eyeHeight,
                        stereo.sbsStride);
                    lastUploadedSbsSequence = stereo.sequence;
                }

                std::array<XrView, 2> views{
                    XrView{XR_TYPE_VIEW},
                    XrView{XR_TYPE_VIEW},
                };

                XrViewLocateInfo locateInfo{XR_TYPE_VIEW_LOCATE_INFO};
                locateInfo.viewConfigurationType =
                    XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                locateInfo.displayTime = frameState.predictedDisplayTime;
                locateInfo.space = localSpace_;

                XrViewState viewState{XR_TYPE_VIEW_STATE};
                std::uint32_t viewCount = 0;

                CheckXr(
                    xrLocateViews(
                        session_,
                        &locateInfo,
                        &viewState,
                        static_cast<std::uint32_t>(views.size()),
                        &viewCount,
                        views.data()),
                    "xrLocateViews");

                const bool viewsUsable =
                    viewCount == 2 &&
                    (viewState.viewStateFlags &
                     XR_VIEW_STATE_ORIENTATION_VALID_BIT) != 0 &&
                    (viewState.viewStateFlags &
                     XR_VIEW_STATE_POSITION_VALID_BIT) != 0;

                if (viewsUsable && baseTexture_.Valid()) {
                    const std::uint32_t imageIndex =
                        projectionSwapchain_.Acquire();

                    const float panelHeightMeters =
                        kPanelWidthMeters *
                        static_cast<float>(baseHeight) /
                        static_cast<float>(std::max(1, baseWidth));

                    const PanelRect baseRect{
                        -kPanelWidthMeters * 0.5f,
                        kPanelWidthMeters * 0.5f,
                        panelHeightMeters * 0.5f,
                        -panelHeightMeters * 0.5f};

                    PanelRect stereoRectMeters{};
                    const PanelRect* stereoRectPtr = nullptr;

                    if (validSbs && sbsTexture_.Valid()) {
                        const float leftNorm =
                            stereo.panelLeft /
                            static_cast<float>(stereo.clientWidth);
                        const float rightNorm =
                            (stereo.panelLeft + stereo.panelWidth) /
                            static_cast<float>(stereo.clientWidth);
                        const float topNorm =
                            stereo.panelTop /
                            static_cast<float>(stereo.clientHeight);
                        const float bottomNorm =
                            (stereo.panelTop + stereo.panelHeight) /
                            static_cast<float>(stereo.clientHeight);

                        stereoRectMeters.left =
                            -kPanelWidthMeters * 0.5f +
                            leftNorm * kPanelWidthMeters;
                        stereoRectMeters.right =
                            -kPanelWidthMeters * 0.5f +
                            rightNorm * kPanelWidthMeters;
                        stereoRectMeters.top =
                            panelHeightMeters * 0.5f -
                            topNorm * panelHeightMeters;
                        stereoRectMeters.bottom =
                            panelHeightMeters * 0.5f -
                            bottomNorm * panelHeightMeters;
                        stereoRectPtr = &stereoRectMeters;
                    }

                    for (std::uint32_t eye = 0; eye < 2; ++eye) {
                        renderer_.RenderEye(
                            device_.Get(),
                            context_.Get(),
                            projectionSwapchain_.Texture(imageIndex),
                            static_cast<DXGI_FORMAT>(swapchainFormat_),
                            eye,
                            projectionSwapchain_.Width(),
                            projectionSwapchain_.Height(),
                            views[eye],
                            baseTexture_.Srv(),
                            baseRect,
                            stereoRectPtr ? sbsTexture_.Srv() : nullptr,
                            stereoRectPtr,
                            eye == 1);

                        projectionViews[eye].pose = views[eye].pose;
                        projectionViews[eye].fov = views[eye].fov;
                        projectionViews[eye].subImage.swapchain =
                            projectionSwapchain_.Handle();
                        projectionViews[eye].subImage.imageRect.offset = {0, 0};
                        projectionViews[eye].subImage.imageRect.extent = {
                            projectionSwapchain_.Width(),
                            projectionSwapchain_.Height()};
                        projectionViews[eye].subImage.imageArrayIndex = eye;
                    }

                    projectionSwapchain_.Release();

                    projectionLayer.layerFlags = 0;
                    projectionLayer.space = localSpace_;
                    projectionLayer.viewCount =
                        static_cast<std::uint32_t>(projectionViews.size());
                    projectionLayer.views = projectionViews.data();

                    submittedLayer =
                        reinterpret_cast<const XrCompositionLayerBaseHeader*>(
                            &projectionLayer);

                    if (validSbs &&
                        stereo.sequence != lastLoggedSbsSequence) {

                        lastLoggedSbsSequence = stereo.sequence;
                        Log(
                            "PROJECTION SBS ACTIVE seq=" +
                            std::to_string(stereo.sequence) +
                            " frame=" +
                            std::to_string(stereo.frameNumber) +
                            " panel=" +
                            std::to_string(stereo.panelLeft) + "," +
                            std::to_string(stereo.panelTop) + " " +
                            std::to_string(stereo.panelWidth) + "x" +
                            std::to_string(stereo.panelHeight) +
                            " eye=" +
                            std::to_string(stereo.eyeWidth) + "x" +
                            std::to_string(stereo.eyeHeight));
                    }
                }
            }

            XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
            endInfo.displayTime = frameState.predictedDisplayTime;
            endInfo.environmentBlendMode = blendMode_;
            endInfo.layerCount = submittedLayer ? 1u : 0u;
            endInfo.layers = submittedLayer ? &submittedLayer : nullptr;

            CheckXr(
                xrEndFrame(session_, &endInfo),
                "xrEndFrame");
        }

        return 0;
    }

private:
    DWORD hostPid_{};
    XrInstance instance_{XR_NULL_HANDLE};
    XrSystemId systemId_{XR_NULL_SYSTEM_ID};
    XrSession session_{XR_NULL_HANDLE};
    XrSpace localSpace_{XR_NULL_HANDLE};
    XrSessionState sessionState_{XR_SESSION_STATE_UNKNOWN};
    bool sessionRunning_{};
    bool exitRequested_{};
    XrEnvironmentBlendMode blendMode_{XR_ENVIRONMENT_BLEND_MODE_OPAQUE};
    std::int64_t swapchainFormat_{DXGI_FORMAT_B8G8R8A8_UNORM};

    ComPtr<ID3D11Device> device_;
    ComPtr<ID3D11DeviceContext> context_;

    WindowCapture capture_;
    SharedSbsReader sharedSbs_;
    SourceTexture baseTexture_;
    SourceTexture sbsTexture_;
    ProjectionSwapchain projectionSwapchain_;
    ProjectionRenderer renderer_;

    void InitializeOpenXr() {
        std::uint32_t extensionCount = 0;
        CheckXr(
            xrEnumerateInstanceExtensionProperties(
                nullptr,
                0,
                &extensionCount,
                nullptr),
            "xrEnumerateInstanceExtensionProperties(count)");

        std::vector<XrExtensionProperties> extensions(extensionCount);
        for (auto& extension : extensions) {
            extension = {XR_TYPE_EXTENSION_PROPERTIES};
        }

        CheckXr(
            xrEnumerateInstanceExtensionProperties(
                nullptr,
                extensionCount,
                &extensionCount,
                extensions.data()),
            "xrEnumerateInstanceExtensionProperties");

        const bool hasD3D11 = std::any_of(
            extensions.begin(),
            extensions.end(),
            [](const XrExtensionProperties& extension) {
                return std::strcmp(
                    extension.extensionName,
                    XR_KHR_D3D11_ENABLE_EXTENSION_NAME) == 0;
            });

        if (!hasD3D11) {
            throw std::runtime_error(
                "Active OpenXR runtime does not expose XR_KHR_D3D11_enable");
        }

        const char* enabledExtensions[] = {
            XR_KHR_D3D11_ENABLE_EXTENSION_NAME};

        XrInstanceCreateInfo create{XR_TYPE_INSTANCE_CREATE_INFO};
        std::strncpy(
            create.applicationInfo.applicationName,
            "GeoGebraForQuest PC",
            XR_MAX_APPLICATION_NAME_SIZE - 1);
        create.applicationInfo.applicationVersion = 6;
        std::strncpy(
            create.applicationInfo.engineName,
            "GeoGebraForQuestPC-v0.6-Projection",
            XR_MAX_ENGINE_NAME_SIZE - 1);
        create.applicationInfo.engineVersion = 6;
        create.applicationInfo.apiVersion = XR_CURRENT_API_VERSION;
        create.enabledExtensionCount = 1;
        create.enabledExtensionNames = enabledExtensions;

        CheckXr(
            xrCreateInstance(&create, &instance_),
            "xrCreateInstance");

        XrInstanceProperties properties{XR_TYPE_INSTANCE_PROPERTIES};
        CheckXr(
            xrGetInstanceProperties(instance_, &properties),
            "xrGetInstanceProperties");
        Log(std::string("OpenXR runtime: ") + properties.runtimeName);

        XrSystemGetInfo systemInfo{XR_TYPE_SYSTEM_GET_INFO};
        systemInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
        CheckXr(
            xrGetSystem(instance_, &systemInfo, &systemId_),
            "xrGetSystem");

        std::uint32_t blendCount = 0;
        CheckXr(
            xrEnumerateEnvironmentBlendModes(
                instance_,
                systemId_,
                XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
                0,
                &blendCount,
                nullptr),
            "xrEnumerateEnvironmentBlendModes(count)");

        std::vector<XrEnvironmentBlendMode> modes(blendCount);
        CheckXr(
            xrEnumerateEnvironmentBlendModes(
                instance_,
                systemId_,
                XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
                blendCount,
                &blendCount,
                modes.data()),
            "xrEnumerateEnvironmentBlendModes");

        if (!modes.empty()) {
            blendMode_ =
                std::find(
                    modes.begin(),
                    modes.end(),
                    XR_ENVIRONMENT_BLEND_MODE_OPAQUE) != modes.end()
                ? XR_ENVIRONMENT_BLEND_MODE_OPAQUE
                : modes.front();
        }
    }

    void InitializeD3D11() {
        PFN_xrGetD3D11GraphicsRequirementsKHR getRequirements = nullptr;
        CheckXr(
            xrGetInstanceProcAddr(
                instance_,
                "xrGetD3D11GraphicsRequirementsKHR",
                reinterpret_cast<PFN_xrVoidFunction*>(&getRequirements)),
            "xrGetInstanceProcAddr(xrGetD3D11GraphicsRequirementsKHR)");

        if (!getRequirements) {
            throw std::runtime_error(
                "D3D11 graphics requirements function missing");
        }

        XrGraphicsRequirementsD3D11KHR requirements{
            XR_TYPE_GRAPHICS_REQUIREMENTS_D3D11_KHR};
        CheckXr(
            getRequirements(instance_, systemId_, &requirements),
            "xrGetD3D11GraphicsRequirementsKHR");

        ComPtr<IDXGIFactory1> factory;
        CheckHr(
            CreateDXGIFactory1(
                IID_PPV_ARGS(factory.ReleaseAndGetAddressOf())),
            "CreateDXGIFactory1");

        ComPtr<IDXGIAdapter1> selected;
        for (UINT i = 0;; ++i) {
            ComPtr<IDXGIAdapter1> adapter;
            if (factory->EnumAdapters1(
                    i,
                    adapter.ReleaseAndGetAddressOf()) ==
                DXGI_ERROR_NOT_FOUND) {
                break;
            }

            DXGI_ADAPTER_DESC1 desc{};
            adapter->GetDesc1(&desc);
            if (LuidEqual(desc.AdapterLuid, requirements.adapterLuid)) {
                selected = adapter;
                break;
            }
        }

        if (!selected) {
            throw std::runtime_error(
                "OpenXR-required DXGI adapter not found");
        }

        const D3D_FEATURE_LEVEL levels[] = {
            D3D_FEATURE_LEVEL_12_1,
            D3D_FEATURE_LEVEL_12_0,
            D3D_FEATURE_LEVEL_11_1,
            D3D_FEATURE_LEVEL_11_0,
        };

        D3D_FEATURE_LEVEL obtained{};
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;

        HRESULT hr = D3D11CreateDevice(
            selected.Get(),
            D3D_DRIVER_TYPE_UNKNOWN,
            nullptr,
            flags,
            levels,
            static_cast<UINT>(std::size(levels)),
            D3D11_SDK_VERSION,
            device_.ReleaseAndGetAddressOf(),
            &obtained,
            context_.ReleaseAndGetAddressOf());

        CheckHr(hr, "D3D11CreateDevice");

        if (obtained < requirements.minFeatureLevel) {
            throw std::runtime_error(
                "D3D feature level is below OpenXR runtime minimum");
        }
    }

    void CreateSessionAndSwapchain() {
        XrGraphicsBindingD3D11KHR binding{
            XR_TYPE_GRAPHICS_BINDING_D3D11_KHR};
        binding.device = device_.Get();

        XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
        sessionInfo.next = &binding;
        sessionInfo.systemId = systemId_;
        CheckXr(
            xrCreateSession(instance_, &sessionInfo, &session_),
            "xrCreateSession");

        XrReferenceSpaceCreateInfo spaceInfo{
            XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        spaceInfo.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
        spaceInfo.poseInReferenceSpace.orientation = {
            0.0f, 0.0f, 0.0f, 1.0f};
        spaceInfo.poseInReferenceSpace.position = {
            0.0f, 0.0f, 0.0f};

        CheckXr(
            xrCreateReferenceSpace(session_, &spaceInfo, &localSpace_),
            "xrCreateReferenceSpace");

        std::uint32_t formatCount = 0;
        CheckXr(
            xrEnumerateSwapchainFormats(
                session_,
                0,
                &formatCount,
                nullptr),
            "xrEnumerateSwapchainFormats(count)");

        std::vector<std::int64_t> formats(formatCount);
        CheckXr(
            xrEnumerateSwapchainFormats(
                session_,
                formatCount,
                &formatCount,
                formats.data()),
            "xrEnumerateSwapchainFormats");

        const std::int64_t preferred[] = {
            DXGI_FORMAT_B8G8R8A8_UNORM,
            DXGI_FORMAT_B8G8R8A8_UNORM_SRGB,
            DXGI_FORMAT_R8G8B8A8_UNORM,
            DXGI_FORMAT_R8G8B8A8_UNORM_SRGB,
        };

        bool found = false;
        for (const auto wanted : preferred) {
            if (std::find(formats.begin(), formats.end(), wanted) !=
                formats.end()) {
                swapchainFormat_ = wanted;
                found = true;
                break;
            }
        }

        if (!found) {
            throw std::runtime_error(
                "OpenXR runtime exposes no supported 32-bit color swapchain format");
        }

        std::uint32_t viewConfigCount = 0;
        CheckXr(
            xrEnumerateViewConfigurationViews(
                instance_,
                systemId_,
                XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
                0,
                &viewConfigCount,
                nullptr),
            "xrEnumerateViewConfigurationViews(count)");

        if (viewConfigCount != 2) {
            throw std::runtime_error(
                "PRIMARY_STEREO did not report exactly two views");
        }

        std::array<XrViewConfigurationView, 2> viewConfigs{
            XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW},
            XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW},
        };

        CheckXr(
            xrEnumerateViewConfigurationViews(
                instance_,
                systemId_,
                XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
                static_cast<std::uint32_t>(viewConfigs.size()),
                &viewConfigCount,
                viewConfigs.data()),
            "xrEnumerateViewConfigurationViews");

        const int width = static_cast<int>(
            std::max(
                viewConfigs[0].recommendedImageRectWidth,
                viewConfigs[1].recommendedImageRectWidth));
        const int height = static_cast<int>(
            std::max(
                viewConfigs[0].recommendedImageRectHeight,
                viewConfigs[1].recommendedImageRectHeight));

        projectionSwapchain_.Create(
            session_,
            swapchainFormat_,
            width,
            height);

        Log(
            "Projection swapchain " +
            std::to_string(width) + "x" +
            std::to_string(height) +
            " arraySize=2");
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};

        while (xrPollEvent(instance_, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto* changed =
                    reinterpret_cast<const XrEventDataSessionStateChanged*>(
                        &event);
                sessionState_ = changed->state;

                switch (sessionState_) {
                    case XR_SESSION_STATE_READY: {
                        XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
                        begin.primaryViewConfigurationType =
                            XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                        CheckXr(
                            xrBeginSession(session_, &begin),
                            "xrBeginSession");
                        sessionRunning_ = true;
                        Log("OpenXR session READY -> Projection Stereo running");
                        break;
                    }

                    case XR_SESSION_STATE_STOPPING:
                        if (sessionRunning_) {
                            CheckXr(
                                xrEndSession(session_),
                                "xrEndSession");
                            sessionRunning_ = false;
                        }
                        break;

                    case XR_SESSION_STATE_EXITING:
                    case XR_SESSION_STATE_LOSS_PENDING:
                        exitRequested_ = true;
                        break;

                    default:
                        break;
                }
            } else if (
                event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING) {
                exitRequested_ = true;
            }

            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
    }
};

} // namespace

int wmain(int argc, wchar_t** argv) {
    const DWORD pid = ParsePid(argc, argv);
    if (!pid) {
        Log("Missing --pid argument");
        return 2;
    }

    try {
        Log(
            "GeoGebraForQuest PC v0.6 Projection Stereo XR companion "
            "starting, host pid=" +
            std::to_string(pid));
        XrProjectionStereoApp app(pid);
        return app.Run();
    } catch (const std::exception& exception) {
        Log(std::string("Fatal: ") + exception.what());
        return 20;
    } catch (...) {
        Log("Fatal: unknown exception");
        return 21;
    }
}
