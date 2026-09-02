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

constexpr wchar_t kMapName[] = L"Local\\GeoGebraForQuestPC_SBS_v2";
constexpr std::int32_t kMagic = 0x47515342;
constexpr std::int32_t kProtocolVersion = 2;
constexpr std::size_t kHeaderSize = 128;
constexpr std::size_t kMapSize = kHeaderSize + static_cast<std::size_t>(4096) * 2048 * 4;
constexpr int kCycleSeconds = 6;

std::ofstream gLog;

void Log(const std::string& text) {
    if (!gLog.is_open()) {
        char path[MAX_PATH]{};
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        std::string file(path);
        const auto slash = file.find_last_of("\\/");
        if (slash != std::string::npos) file.resize(slash + 1);
        file += "GeoGebraForQuestPC.XR.log";
        gLog.open(file, std::ios::out | std::ios::app);
    }
    if (gLog.is_open()) {
        gLog << text << std::endl;
        gLog.flush();
    }
}

[[noreturn]] void ThrowXr(XrResult result, const char* where) {
    throw std::runtime_error(std::string(where) + " failed, XrResult=" + std::to_string(result));
}

void CheckXr(XrResult result, const char* where) {
    if (XR_FAILED(result)) ThrowXr(result, where);
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
    if (!process) return false;
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
    if (pid != data->pid || !IsWindowVisible(hwnd)) return TRUE;

    RECT client{};
    if (!GetClientRect(hwnd, &client)) return TRUE;
    const long w = client.right - client.left;
    const long h = client.bottom - client.top;
    const long long area = static_cast<long long>(w) * h;
    if (w >= 400 && h >= 300 && area > data->bestArea) {
        data->best = hwnd;
        data->bestArea = area;
    }
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
        if (memDc_) DeleteDC(memDc_);
        if (screenDc_) ReleaseDC(nullptr, screenDc_);
    }

    bool Capture(HWND hwnd, std::vector<std::uint8_t>& out, int& width, int& height) {
        RECT client{};
        if (!GetClientRect(hwnd, &client)) return false;
        POINT origin{0, 0};
        if (!ClientToScreen(hwnd, &origin)) return false;

        width = client.right - client.left;
        height = client.bottom - client.top;
        if (width < 2 || height < 2) return false;
        if (!EnsureBitmap(width, height)) return false;

        if (!BitBlt(
                memDc_, 0, 0, width, height,
                screenDc_, origin.x, origin.y,
                SRCCOPY | CAPTUREBLT)) {
            return false;
        }

        const std::size_t bytes = static_cast<std::size_t>(width) * height * 4;
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
        if (bitmap_ && width == width_ && height == height_) return true;
        ResetBitmap();

        if (!screenDc_) screenDc_ = GetDC(nullptr);
        if (!screenDc_) return false;
        if (!memDc_) memDc_ = CreateCompatibleDC(screenDc_);
        if (!memDc_) return false;

        BITMAPINFO info{};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = width;
        info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;

        bitmap_ = CreateDIBSection(
            screenDc_, &info, DIB_RGB_COLORS, &bits_, nullptr, 0);
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

struct GeometrySnapshot {
    bool available{};
    int clientWidth{};
    int clientHeight{};
    int left{};
    int top{};
    int width{};
    int height{};
    std::int64_t sequence{};
};

class SharedGeometryReader {
public:
    ~SharedGeometryReader() {
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    bool Read(GeometrySnapshot& out) {
        if (!view_ && !Open()) return false;

        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadSequence();
            if (first & 1) {
                std::this_thread::yield();
                continue;
            }

            GeometrySnapshot g{};
            g.sequence = first;
            g.available = ReadI32(16) != 0;
            g.clientWidth = ReadI32(20);
            g.clientHeight = ReadI32(24);
            g.left = ReadI32(28);
            g.top = ReadI32(32);
            g.width = ReadI32(36);
            g.height = ReadI32(40);

            MemoryBarrier();
            const auto second = ReadSequence();
            if (first == second && !(second & 1)) {
                g.available =
                    g.available &&
                    g.clientWidth > 1 && g.clientHeight > 1 &&
                    g.width > 1 && g.height > 1;
                out = g;
                return true;
            }
        }
        return false;
    }

private:
    HANDLE mapping_{};
    std::uint8_t* view_{};

    bool Open() {
        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kMapName);
        if (!mapping_) return false;
        view_ = static_cast<std::uint8_t*>(
            MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kMapSize));
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

    std::int32_t ReadI32(std::size_t offset) const {
        std::int32_t value{};
        std::memcpy(&value, view_ + offset, sizeof(value));
        return value;
    }

    std::int64_t ReadSequence() const {
        auto* p = reinterpret_cast<volatile LONG64*>(view_ + 8);
        return static_cast<std::int64_t>(InterlockedCompareExchange64(p, 0, 0));
    }
};

class ProjectionSwapchain {
public:
    ~ProjectionSwapchain() { Reset(); }

    void Reset() {
        images_.clear();
        if (handle_ != XR_NULL_HANDLE) {
            xrDestroySwapchain(handle_);
            handle_ = XR_NULL_HANDLE;
        }
        width_ = 0;
        height_ = 0;
    }

    void Create(XrSession session, std::int64_t format, int width, int height) {
        Reset();
        XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
        info.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
        info.format = format;
        info.sampleCount = 1;
        info.width = static_cast<std::uint32_t>(width);
        info.height = static_cast<std::uint32_t>(height);
        info.faceCount = 1;
        info.arraySize = 2;
        info.mipCount = 1;
        CheckXr(xrCreateSwapchain(session, &info, &handle_), "xrCreateSwapchain");

        std::uint32_t count = 0;
        CheckXr(
            xrEnumerateSwapchainImages(handle_, 0, &count, nullptr),
            "xrEnumerateSwapchainImages(count)");
        images_.resize(count);
        for (auto& image : images_) image = {XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR};
        CheckXr(
            xrEnumerateSwapchainImages(
                handle_, count, &count,
                reinterpret_cast<XrSwapchainImageBaseHeader*>(images_.data())),
            "xrEnumerateSwapchainImages(images)");
        width_ = width;
        height_ = height;
    }

    std::uint32_t Acquire() {
        std::uint32_t index = 0;
        XrSwapchainImageAcquireInfo acquire{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
        CheckXr(xrAcquireSwapchainImage(handle_, &acquire, &index), "xrAcquireSwapchainImage");
        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(xrWaitSwapchainImage(handle_, &wait), "xrWaitSwapchainImage");
        return index;
    }

    void Release() {
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(xrReleaseSwapchainImage(handle_, &release), "xrReleaseSwapchainImage");
    }

    ID3D11Texture2D* Texture(std::uint32_t index) const { return images_.at(index).texture; }
    XrSwapchain Handle() const { return handle_; }
    int Width() const { return width_; }
    int Height() const { return height_; }

private:
    XrSwapchain handle_{XR_NULL_HANDLE};
    std::vector<XrSwapchainImageD3D11KHR> images_;
    int width_{};
    int height_{};
};

class SourceTexture {
public:
    void Upload(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        const std::uint8_t* pixels,
        int width,
        int height) {

        if (!pixels || width < 2 || height < 2) return;
        if (!texture_ || width != width_ || height != height_) {
            texture_.Reset();
            srv_.Reset();

            D3D11_TEXTURE2D_DESC desc{};
            desc.Width = static_cast<UINT>(width);
            desc.Height = static_cast<UINT>(height);
            desc.MipLevels = 1;
            desc.ArraySize = 1;
            desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
            desc.SampleDesc.Count = 1;
            desc.Usage = D3D11_USAGE_DEFAULT;
            desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
            CheckHr(device->CreateTexture2D(&desc, nullptr, texture_.ReleaseAndGetAddressOf()), "CreateTexture2D(base)");
            CheckHr(device->CreateShaderResourceView(texture_.Get(), nullptr, srv_.ReleaseAndGetAddressOf()), "CreateShaderResourceView(base)");
            width_ = width;
            height_ = height;
        }
        context->UpdateSubresource(texture_.Get(), 0, nullptr, pixels, static_cast<UINT>(width * 4), 0);
    }

    ID3D11ShaderResourceView* Srv() const { return srv_.Get(); }
    bool Valid() const { return srv_ != nullptr; }

private:
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    int width_{};
    int height_{};
};

struct Vertex {
    float x, y, z, w;
    float u, v;
};

struct ClipRect {
    float left;
    float right;
    float top;
    float bottom;
};

class DiagnosticRenderer {
public:
    void Initialize(ID3D11Device* device) {
        static const char* source = R"(
Texture2D tex0 : register(t0);
SamplerState samp0 : register(s0);
cbuffer SolidBuffer : register(b0) { float4 solidColor; };
struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD0; };
struct VSOut { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
VSOut VSMain(VSIn i) { VSOut o; o.pos=i.pos; o.uv=i.uv; return o; }
float4 PSTexture(VSOut i) : SV_TARGET { return tex0.Sample(samp0, i.uv); }
float4 PSSolid(VSOut i) : SV_TARGET { return solidColor; }
)";

        ComPtr<ID3DBlob> vsBlob, psTexBlob, psSolidBlob, errors;
        CheckCompile(source, "VSMain", "vs_5_0", vsBlob, errors);
        errors.Reset();
        CheckCompile(source, "PSTexture", "ps_5_0", psTexBlob, errors);
        errors.Reset();
        CheckCompile(source, "PSSolid", "ps_5_0", psSolidBlob, errors);

        CheckHr(device->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, vs_.ReleaseAndGetAddressOf()), "CreateVertexShader");
        CheckHr(device->CreatePixelShader(psTexBlob->GetBufferPointer(), psTexBlob->GetBufferSize(), nullptr, psTexture_.ReleaseAndGetAddressOf()), "CreatePixelShader(texture)");
        CheckHr(device->CreatePixelShader(psSolidBlob->GetBufferPointer(), psSolidBlob->GetBufferSize(), nullptr, psSolid_.ReleaseAndGetAddressOf()), "CreatePixelShader(solid)");

        const D3D11_INPUT_ELEMENT_DESC layout[] = {
            {"POSITION",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,16,D3D11_INPUT_PER_VERTEX_DATA,0},
        };
        CheckHr(device->CreateInputLayout(layout, 2, vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), input_.ReleaseAndGetAddressOf()), "CreateInputLayout");

        D3D11_BUFFER_DESC vb{};
        vb.ByteWidth = sizeof(Vertex) * 6;
        vb.Usage = D3D11_USAGE_DYNAMIC;
        vb.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        CheckHr(device->CreateBuffer(&vb, nullptr, vertexBuffer_.ReleaseAndGetAddressOf()), "CreateBuffer(vertex)");

        D3D11_BUFFER_DESC cb{};
        cb.ByteWidth = 16;
        cb.Usage = D3D11_USAGE_DYNAMIC;
        cb.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        cb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        CheckHr(device->CreateBuffer(&cb, nullptr, solidBuffer_.ReleaseAndGetAddressOf()), "CreateBuffer(solid)");

        D3D11_SAMPLER_DESC samp{};
        samp.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        samp.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        samp.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        samp.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        samp.MinLOD = 0.0f;
        samp.MaxLOD = D3D11_FLOAT32_MAX;
        CheckHr(device->CreateSamplerState(&samp, sampler_.ReleaseAndGetAddressOf()), "CreateSamplerState");

        D3D11_RASTERIZER_DESC rast{};
        rast.FillMode = D3D11_FILL_SOLID;
        rast.CullMode = D3D11_CULL_NONE;
        rast.DepthClipEnable = TRUE;
        CheckHr(device->CreateRasterizerState(&rast, rasterizer_.ReleaseAndGetAddressOf()), "CreateRasterizerState");
    }

    void RenderEye(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        ID3D11Texture2D* target,
        DXGI_FORMAT format,
        UINT slice,
        int width,
        int height,
        ID3D11ShaderResourceView* baseSrv,
        const ClipRect& bRect,
        const std::array<float,4>& bColor,
        bool geometryAvailable) {

        D3D11_RENDER_TARGET_VIEW_DESC rtvDesc{};
        rtvDesc.Format = format;
        rtvDesc.ViewDimension = D3D11_RTV_DIMENSION_TEXTURE2DARRAY;
        rtvDesc.Texture2DArray.MipSlice = 0;
        rtvDesc.Texture2DArray.FirstArraySlice = slice;
        rtvDesc.Texture2DArray.ArraySize = 1;

        ComPtr<ID3D11RenderTargetView> rtv;
        CheckHr(device->CreateRenderTargetView(target, &rtvDesc, rtv.ReleaseAndGetAddressOf()), "CreateRenderTargetView");
        ID3D11RenderTargetView* rtvs[] = {rtv.Get()};
        context->OMSetRenderTargets(1, rtvs, nullptr);

        const float clear[4] = {0.015f,0.015f,0.02f,1.0f};
        context->ClearRenderTargetView(rtv.Get(), clear);

        D3D11_VIEWPORT vp{};
        vp.Width = static_cast<float>(width);
        vp.Height = static_cast<float>(height);
        vp.MinDepth = 0.0f;
        vp.MaxDepth = 1.0f;
        context->RSSetViewports(1, &vp);
        context->RSSetState(rasterizer_.Get());
        context->IASetInputLayout(input_.Get());
        context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        const UINT stride = sizeof(Vertex);
        const UINT offset = 0;
        ID3D11Buffer* vb[] = {vertexBuffer_.Get()};
        context->IASetVertexBuffers(0,1,vb,&stride,&offset);
        context->VSSetShader(vs_.Get(), nullptr, 0);

        if (baseSrv) {
            DrawTextured(context, {-1.0f,1.0f,1.0f,-1.0f}, baseSrv);
        }

        DrawSolid(context, bRect, bColor);

        const std::array<float,4> indicator = geometryAvailable
            ? std::array<float,4>{0.0f,1.0f,0.15f,1.0f}
            : std::array<float,4>{1.0f,0.45f,0.0f,1.0f};
        DrawSolid(context, {-0.96f,-0.78f,0.94f,0.76f}, indicator);

        ID3D11ShaderResourceView* nullSrv[] = {nullptr};
        context->PSSetShaderResources(0,1,nullSrv);
        context->OMSetRenderTargets(0,nullptr,nullptr);
    }

private:
    ComPtr<ID3D11VertexShader> vs_;
    ComPtr<ID3D11PixelShader> psTexture_;
    ComPtr<ID3D11PixelShader> psSolid_;
    ComPtr<ID3D11InputLayout> input_;
    ComPtr<ID3D11Buffer> vertexBuffer_;
    ComPtr<ID3D11Buffer> solidBuffer_;
    ComPtr<ID3D11SamplerState> sampler_;
    ComPtr<ID3D11RasterizerState> rasterizer_;

    static void CheckCompile(
        const char* source,
        const char* entry,
        const char* target,
        ComPtr<ID3DBlob>& blob,
        ComPtr<ID3DBlob>& errors) {

        HRESULT hr = D3DCompile(
            source, std::strlen(source), "GGQ-v0.8", nullptr, nullptr,
            entry, target, D3DCOMPILE_ENABLE_STRICTNESS, 0,
            blob.ReleaseAndGetAddressOf(), errors.ReleaseAndGetAddressOf());
        if (FAILED(hr)) {
            std::string detail = "shader compile failed";
            if (errors && errors->GetBufferPointer()) {
                detail.assign(
                    static_cast<const char*>(errors->GetBufferPointer()),
                    errors->GetBufferSize());
            }
            throw std::runtime_error(detail);
        }
    }

    void UploadVertices(ID3D11DeviceContext* context, const ClipRect& r) {
        const std::array<Vertex,6> v = {
            Vertex{r.left,r.top,0.5f,1.0f,0.0f,0.0f},
            Vertex{r.left,r.bottom,0.5f,1.0f,0.0f,1.0f},
            Vertex{r.right,r.top,0.5f,1.0f,1.0f,0.0f},
            Vertex{r.right,r.top,0.5f,1.0f,1.0f,0.0f},
            Vertex{r.left,r.bottom,0.5f,1.0f,0.0f,1.0f},
            Vertex{r.right,r.bottom,0.5f,1.0f,1.0f,1.0f},
        };
        D3D11_MAPPED_SUBRESOURCE mapped{};
        CheckHr(context->Map(vertexBuffer_.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped), "Map(vertices)");
        std::memcpy(mapped.pData, v.data(), sizeof(v));
        context->Unmap(vertexBuffer_.Get(),0);
    }

    void DrawTextured(ID3D11DeviceContext* context, const ClipRect& r, ID3D11ShaderResourceView* srv) {
        UploadVertices(context, r);
        context->PSSetShader(psTexture_.Get(), nullptr, 0);
        ID3D11ShaderResourceView* srvs[] = {srv};
        context->PSSetShaderResources(0,1,srvs);
        ID3D11SamplerState* samplers[] = {sampler_.Get()};
        context->PSSetSamplers(0,1,samplers);
        context->Draw(6,0);
    }

    void DrawSolid(ID3D11DeviceContext* context, const ClipRect& r, const std::array<float,4>& color) {
        UploadVertices(context, r);
        D3D11_MAPPED_SUBRESOURCE mapped{};
        CheckHr(context->Map(solidBuffer_.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped), "Map(solid)");
        std::memcpy(mapped.pData, color.data(), 16);
        context->Unmap(solidBuffer_.Get(),0);
        ID3D11Buffer* buffers[] = {solidBuffer_.Get()};
        context->PSSetConstantBuffers(0,1,buffers);
        context->PSSetShader(psSolid_.Get(), nullptr, 0);
        context->Draw(6,0);
    }
};

class BPanelDiagnosticApp {
public:
    explicit BPanelDiagnosticApp(DWORD hostPid) : hostPid_(hostPid) {}

    ~BPanelDiagnosticApp() {
        swapchain_.Reset();
        if (localSpace_ != XR_NULL_HANDLE) xrDestroySpace(localSpace_);
        if (session_ != XR_NULL_HANDLE) xrDestroySession(session_);
        if (instance_ != XR_NULL_HANDLE) xrDestroyInstance(instance_);
    }

    int Run() {
        InitializeOpenXr();
        InitializeD3D11();
        CreateSessionAndSwapchain();
        renderer_.Initialize(device_.Get());

        Log("v0.8 B diagnostic initialized: A=window capture; B=magenta then L red/R blue; top-left indicator green=shared geometry, orange=fallback.");

        std::vector<std::uint8_t> basePixels;
        int baseWidth = 0;
        int baseHeight = 0;
        auto lastCapture = std::chrono::steady_clock::time_point{};
        const auto start = std::chrono::steady_clock::now();
        int lastMode = -1;
        bool lastGeometryAvailable = false;

        while (!exitRequested_ && ProcessAlive(hostPid_)) {
            PollEvents();
            if (!sessionRunning_) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
            XrFrameState frameState{XR_TYPE_FRAME_STATE};
            CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");
            XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
            CheckXr(xrBeginFrame(session_, &beginInfo), "xrBeginFrame");

            const XrCompositionLayerBaseHeader* submitted = nullptr;
            XrCompositionLayerProjection layer{XR_TYPE_COMPOSITION_LAYER_PROJECTION};
            std::array<XrCompositionLayerProjectionView,2> projViews{
                XrCompositionLayerProjectionView{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
                XrCompositionLayerProjectionView{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            };

            if (frameState.shouldRender) {
                HWND host = FindMainWindow(hostPid_);
                const auto now = std::chrono::steady_clock::now();
                if (host && (lastCapture.time_since_epoch().count() == 0 || now - lastCapture >= std::chrono::milliseconds(33))) {
                    if (capture_.Capture(host, basePixels, baseWidth, baseHeight)) {
                        baseTexture_.Upload(device_.Get(), context_.Get(), basePixels.data(), baseWidth, baseHeight);
                        lastCapture = now;
                    }
                }

                GeometrySnapshot geometry{};
                geometryReader_.Read(geometry);

                ClipRect bRect{-0.15f,0.92f,0.62f,-0.56f};
                if (geometry.available) {
                    const float l = geometry.left / static_cast<float>(geometry.clientWidth);
                    const float r = (geometry.left + geometry.width) / static_cast<float>(geometry.clientWidth);
                    const float t = geometry.top / static_cast<float>(geometry.clientHeight);
                    const float b = (geometry.top + geometry.height) / static_cast<float>(geometry.clientHeight);
                    bRect.left = -1.0f + 2.0f * std::clamp(l,0.0f,1.0f);
                    bRect.right = -1.0f + 2.0f * std::clamp(r,0.0f,1.0f);
                    bRect.top = 1.0f - 2.0f * std::clamp(t,0.0f,1.0f);
                    bRect.bottom = 1.0f - 2.0f * std::clamp(b,0.0f,1.0f);
                }

                if (geometry.available != lastGeometryAvailable) {
                    lastGeometryAvailable = geometry.available;
                    Log(std::string("shared geometry=") + (geometry.available ? "AVAILABLE" : "MISSING/FALLBACK"));
                }

                const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - start).count();
                const int mode = static_cast<int>((elapsed / kCycleSeconds) % 2);
                if (mode != lastMode) {
                    lastMode = mode;
                    Log(mode == 0
                        ? "diagnostic mode 0: MAGENTA B BOTH EYES"
                        : "diagnostic mode 1: LEFT RED / RIGHT BLUE");
                }

                std::array<XrView,2> views{XrView{XR_TYPE_VIEW}, XrView{XR_TYPE_VIEW}};
                XrViewLocateInfo locate{XR_TYPE_VIEW_LOCATE_INFO};
                locate.viewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                locate.displayTime = frameState.predictedDisplayTime;
                locate.space = localSpace_;
                XrViewState viewState{XR_TYPE_VIEW_STATE};
                std::uint32_t viewCount = 0;
                CheckXr(xrLocateViews(session_, &locate, &viewState, 2, &viewCount, views.data()), "xrLocateViews");

                if (viewCount == 2 && baseTexture_.Valid()) {
                    const std::uint32_t imageIndex = swapchain_.Acquire();
                    for (std::uint32_t eye = 0; eye < 2; ++eye) {
                        std::array<float,4> color{};
                        if (mode == 0) {
                            color = {0.95f,0.0f,0.95f,1.0f};
                        } else {
                            color = eye == 0
                                ? std::array<float,4>{1.0f,0.0f,0.0f,1.0f}
                                : std::array<float,4>{0.0f,0.25f,1.0f,1.0f};
                        }

                        renderer_.RenderEye(
                            device_.Get(), context_.Get(),
                            swapchain_.Texture(imageIndex),
                            static_cast<DXGI_FORMAT>(swapchainFormat_),
                            eye, swapchain_.Width(), swapchain_.Height(),
                            baseTexture_.Srv(), bRect, color, geometry.available);

                        projViews[eye].pose = views[eye].pose;
                        projViews[eye].fov = views[eye].fov;
                        projViews[eye].subImage.swapchain = swapchain_.Handle();
                        projViews[eye].subImage.imageRect.offset = {0,0};
                        projViews[eye].subImage.imageRect.extent = {swapchain_.Width(), swapchain_.Height()};
                        projViews[eye].subImage.imageArrayIndex = eye;
                    }
                    swapchain_.Release();

                    layer.space = localSpace_;
                    layer.viewCount = 2;
                    layer.views = projViews.data();
                    submitted = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&layer);
                }
            }

            XrFrameEndInfo end{XR_TYPE_FRAME_END_INFO};
            end.displayTime = frameState.predictedDisplayTime;
            end.environmentBlendMode = blendMode_;
            end.layerCount = submitted ? 1u : 0u;
            end.layers = submitted ? &submitted : nullptr;
            CheckXr(xrEndFrame(session_, &end), "xrEndFrame");
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
    ProjectionSwapchain swapchain_;
    WindowCapture capture_;
    SourceTexture baseTexture_;
    SharedGeometryReader geometryReader_;
    DiagnosticRenderer renderer_;

    void InitializeOpenXr() {
        std::uint32_t extensionCount = 0;
        CheckXr(xrEnumerateInstanceExtensionProperties(nullptr,0,&extensionCount,nullptr), "xrEnumerateInstanceExtensionProperties(count)");
        std::vector<XrExtensionProperties> extensions(extensionCount);
        for (auto& e : extensions) e = {XR_TYPE_EXTENSION_PROPERTIES};
        CheckXr(xrEnumerateInstanceExtensionProperties(nullptr,extensionCount,&extensionCount,extensions.data()), "xrEnumerateInstanceExtensionProperties");
        const bool hasD3D11 = std::any_of(extensions.begin(),extensions.end(),[](const XrExtensionProperties& e){
            return std::strcmp(e.extensionName, XR_KHR_D3D11_ENABLE_EXTENSION_NAME) == 0;
        });
        if (!hasD3D11) throw std::runtime_error("XR_KHR_D3D11_enable missing");

        const char* enabled[] = {XR_KHR_D3D11_ENABLE_EXTENSION_NAME};
        XrInstanceCreateInfo create{XR_TYPE_INSTANCE_CREATE_INFO};
        std::strncpy(create.applicationInfo.applicationName, "GeoGebraForQuest PC B Diagnostic", XR_MAX_APPLICATION_NAME_SIZE-1);
        create.applicationInfo.applicationVersion = 8;
        std::strncpy(create.applicationInfo.engineName, "GGQ-PC-v0.8-BDiagnostic", XR_MAX_ENGINE_NAME_SIZE-1);
        create.applicationInfo.engineVersion = 8;
        create.applicationInfo.apiVersion = XR_CURRENT_API_VERSION;
        create.enabledExtensionCount = 1;
        create.enabledExtensionNames = enabled;
        CheckXr(xrCreateInstance(&create,&instance_), "xrCreateInstance");

        XrInstanceProperties props{XR_TYPE_INSTANCE_PROPERTIES};
        CheckXr(xrGetInstanceProperties(instance_,&props), "xrGetInstanceProperties");
        Log(std::string("OpenXR runtime=") + props.runtimeName);

        XrSystemGetInfo info{XR_TYPE_SYSTEM_GET_INFO};
        info.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
        CheckXr(xrGetSystem(instance_,&info,&systemId_), "xrGetSystem");

        std::uint32_t blendCount = 0;
        CheckXr(xrEnumerateEnvironmentBlendModes(instance_,systemId_,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,0,&blendCount,nullptr), "xrEnumerateEnvironmentBlendModes(count)");
        std::vector<XrEnvironmentBlendMode> modes(blendCount);
        CheckXr(xrEnumerateEnvironmentBlendModes(instance_,systemId_,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,blendCount,&blendCount,modes.data()), "xrEnumerateEnvironmentBlendModes");
        if (!modes.empty()) {
            blendMode_ = std::find(modes.begin(),modes.end(),XR_ENVIRONMENT_BLEND_MODE_OPAQUE) != modes.end()
                ? XR_ENVIRONMENT_BLEND_MODE_OPAQUE : modes.front();
        }
    }

    void InitializeD3D11() {
        PFN_xrGetD3D11GraphicsRequirementsKHR getReq = nullptr;
        CheckXr(xrGetInstanceProcAddr(instance_,"xrGetD3D11GraphicsRequirementsKHR",reinterpret_cast<PFN_xrVoidFunction*>(&getReq)), "xrGetInstanceProcAddr");
        if (!getReq) throw std::runtime_error("xrGetD3D11GraphicsRequirementsKHR missing");

        XrGraphicsRequirementsD3D11KHR req{XR_TYPE_GRAPHICS_REQUIREMENTS_D3D11_KHR};
        CheckXr(getReq(instance_,systemId_,&req), "xrGetD3D11GraphicsRequirementsKHR");

        ComPtr<IDXGIFactory1> factory;
        CheckHr(CreateDXGIFactory1(IID_PPV_ARGS(factory.ReleaseAndGetAddressOf())), "CreateDXGIFactory1");
        ComPtr<IDXGIAdapter1> selected;
        for (UINT i=0;;++i) {
            ComPtr<IDXGIAdapter1> adapter;
            if (factory->EnumAdapters1(i,adapter.ReleaseAndGetAddressOf()) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_ADAPTER_DESC1 desc{};
            adapter->GetDesc1(&desc);
            if (LuidEqual(desc.AdapterLuid,req.adapterLuid)) { selected = adapter; break; }
        }
        if (!selected) throw std::runtime_error("OpenXR DXGI adapter not found");

        const D3D_FEATURE_LEVEL levels[] = {
            D3D_FEATURE_LEVEL_12_1,D3D_FEATURE_LEVEL_12_0,
            D3D_FEATURE_LEVEL_11_1,D3D_FEATURE_LEVEL_11_0};
        D3D_FEATURE_LEVEL obtained{};
        CheckHr(D3D11CreateDevice(
            selected.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            levels,static_cast<UINT>(std::size(levels)),D3D11_SDK_VERSION,
            device_.ReleaseAndGetAddressOf(),&obtained,context_.ReleaseAndGetAddressOf()),
            "D3D11CreateDevice");
        if (obtained < req.minFeatureLevel) throw std::runtime_error("D3D feature level below OpenXR minimum");
    }

    void CreateSessionAndSwapchain() {
        XrGraphicsBindingD3D11KHR binding{XR_TYPE_GRAPHICS_BINDING_D3D11_KHR};
        binding.device = device_.Get();
        XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
        sessionInfo.next = &binding;
        sessionInfo.systemId = systemId_;
        CheckXr(xrCreateSession(instance_,&sessionInfo,&session_), "xrCreateSession");

        XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        spaceInfo.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
        spaceInfo.poseInReferenceSpace.orientation = {0,0,0,1};
        CheckXr(xrCreateReferenceSpace(session_,&spaceInfo,&localSpace_), "xrCreateReferenceSpace");

        std::uint32_t formatCount = 0;
        CheckXr(xrEnumerateSwapchainFormats(session_,0,&formatCount,nullptr), "xrEnumerateSwapchainFormats(count)");
        std::vector<std::int64_t> formats(formatCount);
        CheckXr(xrEnumerateSwapchainFormats(session_,formatCount,&formatCount,formats.data()), "xrEnumerateSwapchainFormats");
        const std::int64_t preferred[] = {
            DXGI_FORMAT_B8G8R8A8_UNORM,DXGI_FORMAT_B8G8R8A8_UNORM_SRGB,
            DXGI_FORMAT_R8G8B8A8_UNORM,DXGI_FORMAT_R8G8B8A8_UNORM_SRGB};
        bool found = false;
        for (auto f : preferred) {
            if (std::find(formats.begin(),formats.end(),f) != formats.end()) {
                swapchainFormat_ = f; found = true; break;
            }
        }
        if (!found) throw std::runtime_error("No supported 32-bit swapchain format");

        std::uint32_t count = 0;
        CheckXr(xrEnumerateViewConfigurationViews(instance_,systemId_,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,0,&count,nullptr), "xrEnumerateViewConfigurationViews(count)");
        if (count != 2) throw std::runtime_error("PRIMARY_STEREO view count != 2");
        std::array<XrViewConfigurationView,2> configs{
            XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW},
            XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW}};
        CheckXr(xrEnumerateViewConfigurationViews(instance_,systemId_,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,2,&count,configs.data()), "xrEnumerateViewConfigurationViews");
        const int w = static_cast<int>(std::max(configs[0].recommendedImageRectWidth,configs[1].recommendedImageRectWidth));
        const int h = static_cast<int>(std::max(configs[0].recommendedImageRectHeight,configs[1].recommendedImageRectHeight));
        swapchain_.Create(session_,swapchainFormat_,w,h);
        Log("Projection swapchain=" + std::to_string(w) + "x" + std::to_string(h));
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance_,&event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto* changed = reinterpret_cast<const XrEventDataSessionStateChanged*>(&event);
                sessionState_ = changed->state;
                Log("sessionState=" + std::to_string(static_cast<int>(sessionState_)));
                switch (sessionState_) {
                    case XR_SESSION_STATE_READY: {
                        XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
                        begin.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                        CheckXr(xrBeginSession(session_,&begin), "xrBeginSession");
                        sessionRunning_ = true;
                        break;
                    }
                    case XR_SESSION_STATE_STOPPING:
                        if (sessionRunning_) {
                            CheckXr(xrEndSession(session_), "xrEndSession");
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
            } else if (event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING) {
                exitRequested_ = true;
            }
            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
    }
};

} // namespace

int wmain(int argc, wchar_t** argv) {
    const DWORD pid = ParsePid(argc,argv);
    if (!pid) {
        Log("Missing --pid argument");
        return 2;
    }
    try {
        Log("GeoGebraForQuest PC v0.8 B-panel diagnostic starting, host pid=" + std::to_string(pid));
        BPanelDiagnosticApp app(pid);
        return app.Run();
    } catch (const std::exception& ex) {
        Log(std::string("Fatal: ") + ex.what());
        return 20;
    } catch (...) {
        Log("Fatal: unknown exception");
        return 21;
    }
}
