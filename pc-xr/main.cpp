#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>

#define XR_USE_PLATFORM_WIN32
#define XR_USE_GRAPHICS_API_D3D11
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {

constexpr wchar_t kStereoMapName[] = L"Local\\GeoGebraForQuestPC_Stereo_v1";
constexpr std::int32_t kMagic = 0x47515150;
constexpr std::int32_t kProtocolVersion = 1;
constexpr std::size_t kHeaderSize = 128;
constexpr int kMaxEyeWidth = 2048;
constexpr int kMaxEyeHeight = 2048;
constexpr std::size_t kMaxEyeBytes = static_cast<std::size_t>(kMaxEyeWidth) * kMaxEyeHeight * 4;
constexpr std::size_t kLeftOffset = kHeaderSize;
constexpr std::size_t kRightOffset = kHeaderSize + kMaxEyeBytes;
constexpr std::size_t kMappingSize = kHeaderSize + kMaxEyeBytes * 2;
constexpr float kPanelWidthMeters = 1.80f;
constexpr float kPanelDistanceMeters = 1.60f;

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
    const long width = client.right - client.left;
    const long height = client.bottom - client.top;
    const long long area = static_cast<long long>(width) * height;
    if (width < 400 || height < 300 || area <= data->bestArea) return TRUE;

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
        info.bmiHeader.biHeight = -height; // top-down BGRA
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;

        bitmap_ = CreateDIBSection(screenDc_, &info, DIB_RGB_COLORS, &bits_, nullptr, 0);
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

struct StereoSnapshot {
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
    int stride{};
    std::int32_t frameNumber{};
    std::vector<std::uint8_t> left;
    std::vector<std::uint8_t> right;
};

class SharedStereoReader {
public:
    ~SharedStereoReader() {
        if (view_) UnmapViewOfFile(view_);
        if (mapping_) CloseHandle(mapping_);
    }

    bool Open() {
        if (view_) return true;
        mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kStereoMapName);
        if (!mapping_) return false;
        view_ = static_cast<std::uint8_t*>(MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, kMappingSize));
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

    bool Read(StereoSnapshot& snapshot) {
        if (!view_ && !Open()) return false;

        for (int attempt = 0; attempt < 3; ++attempt) {
            const auto first = ReadSequence();
            if (first & 1) {
                std::this_thread::yield();
                continue;
            }

            StereoSnapshot candidate{};
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
            candidate.stride = ReadI32(52);
            candidate.frameNumber = ReadI32(56);

            const bool validEye = candidate.active &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.stride == candidate.eyeWidth * 4;

            if (validEye) {
                const std::size_t bytes = static_cast<std::size_t>(candidate.stride) * candidate.eyeHeight;
                candidate.left.resize(bytes);
                candidate.right.resize(bytes);
                std::memcpy(candidate.left.data(), view_ + kLeftOffset, bytes);
                std::memcpy(candidate.right.data(), view_ + kRightOffset, bytes);
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
        return static_cast<std::int64_t>(InterlockedCompareExchange64(address, 0, 0));
    }
};

class XrSwapchainTexture {
public:
    XrSwapchainTexture() = default;
    ~XrSwapchainTexture() { Reset(); }

    XrSwapchainTexture(const XrSwapchainTexture&) = delete;
    XrSwapchainTexture& operator=(const XrSwapchainTexture&) = delete;

    void Reset() {
        images_.clear();
        if (handle_ != XR_NULL_HANDLE) {
            xrDestroySwapchain(handle_);
            handle_ = XR_NULL_HANDLE;
        }
        width_ = 0;
        height_ = 0;
    }

    void Ensure(XrSession session, std::int64_t format, int width, int height) {
        if (handle_ != XR_NULL_HANDLE && width == width_ && height == height_) return;
        Reset();

        XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
        info.createFlags = 0;
        info.usageFlags = XR_SWAPCHAIN_USAGE_SAMPLED_BIT | XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
        info.format = format;
        info.sampleCount = 1;
        info.width = static_cast<std::uint32_t>(width);
        info.height = static_cast<std::uint32_t>(height);
        info.faceCount = 1;
        info.arraySize = 1;
        info.mipCount = 1;
        CheckXr(xrCreateSwapchain(session, &info, &handle_), "xrCreateSwapchain");

        std::uint32_t count = 0;
        CheckXr(xrEnumerateSwapchainImages(handle_, 0, &count, nullptr), "xrEnumerateSwapchainImages(count)");
        images_.resize(count, {XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR});
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

    bool Upload(ID3D11DeviceContext* context, const std::uint8_t* pixels, int rowPitch) {
        if (handle_ == XR_NULL_HANDLE || images_.empty() || !pixels) return false;

        std::uint32_t index = 0;
        XrSwapchainImageAcquireInfo acquire{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
        CheckXr(xrAcquireSwapchainImage(handle_, &acquire, &index), "xrAcquireSwapchainImage");

        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(xrWaitSwapchainImage(handle_, &wait), "xrWaitSwapchainImage");

        context->UpdateSubresource(images_.at(index).texture, 0, nullptr, pixels, rowPitch, 0);

        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(xrReleaseSwapchainImage(handle_, &release), "xrReleaseSwapchainImage");
        return true;
    }

    XrSwapchain Handle() const { return handle_; }
    int Width() const { return width_; }
    int Height() const { return height_; }

private:
    XrSwapchain handle_{XR_NULL_HANDLE};
    std::vector<XrSwapchainImageD3D11KHR> images_;
    int width_{};
    int height_{};
};

class XrMirrorApp {
public:
    explicit XrMirrorApp(DWORD hostPid) : hostPid_(hostPid) {}

    ~XrMirrorApp() {
        baseSwapchain_.Reset();
        leftSwapchain_.Reset();
        rightSwapchain_.Reset();
        if (localSpace_ != XR_NULL_HANDLE) xrDestroySpace(localSpace_);
        if (session_ != XR_NULL_HANDLE) xrDestroySession(session_);
        if (instance_ != XR_NULL_HANDLE) xrDestroyInstance(instance_);
    }

    int Run() {
        InitializeOpenXr();
        InitializeD3D11();
        CreateSession();

        Log("OpenXR initialized; waiting for session READY");

        auto lastCapture = std::chrono::steady_clock::time_point{};
        std::vector<std::uint8_t> basePixels;
        int baseWidth = 0;
        int baseHeight = 0;
        std::int64_t lastStereoSequence = -1;
        StereoSnapshot stereo{};

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

            std::vector<const XrCompositionLayerBaseHeader*> layers;
            XrCompositionLayerQuad baseLayer{XR_TYPE_COMPOSITION_LAYER_QUAD};
            XrCompositionLayerQuad leftLayer{XR_TYPE_COMPOSITION_LAYER_QUAD};
            XrCompositionLayerQuad rightLayer{XR_TYPE_COMPOSITION_LAYER_QUAD};

            if (frameState.shouldRender) {
                HWND hostWindow = FindMainWindow(hostPid_);
                if (hostWindow) {
                    const auto now = std::chrono::steady_clock::now();
                    const bool captureDue = lastCapture.time_since_epoch().count() == 0 ||
                        now - lastCapture >= std::chrono::milliseconds(33);

                    if (captureDue && capture_.Capture(hostWindow, basePixels, baseWidth, baseHeight)) {
                        baseSwapchain_.Ensure(session_, swapchainFormat_, baseWidth, baseHeight);
                        baseSwapchain_.Upload(context_.Get(), basePixels.data(), baseWidth * 4);
                        lastCapture = now;
                    }

                    StereoSnapshot newest{};
                    if (sharedStereo_.Read(newest)) {
                        stereo = std::move(newest);
                        if (stereo.active && stereo.sequence != lastStereoSequence &&
                            !stereo.left.empty() && !stereo.right.empty()) {
                            leftSwapchain_.Ensure(session_, swapchainFormat_, stereo.eyeWidth, stereo.eyeHeight);
                            rightSwapchain_.Ensure(session_, swapchainFormat_, stereo.eyeWidth, stereo.eyeHeight);
                            leftSwapchain_.Upload(context_.Get(), stereo.left.data(), stereo.stride);
                            rightSwapchain_.Upload(context_.Get(), stereo.right.data(), stereo.stride);
                            lastStereoSequence = stereo.sequence;
                        }
                    }
                }

                if (baseSwapchain_.Handle() != XR_NULL_HANDLE && baseWidth > 1 && baseHeight > 1) {
                    const float panelHeight = kPanelWidthMeters * static_cast<float>(baseHeight) /
                        static_cast<float>(baseWidth);

                    baseLayer.layerFlags = 0;
                    baseLayer.space = localSpace_;
                    baseLayer.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
                    baseLayer.subImage.swapchain = baseSwapchain_.Handle();
                    baseLayer.subImage.imageRect.offset = {0, 0};
                    baseLayer.subImage.imageRect.extent = {baseWidth, baseHeight};
                    baseLayer.subImage.imageArrayIndex = 0;
                    baseLayer.pose.orientation = {0.0f, 0.0f, 0.0f, 1.0f};
                    baseLayer.pose.position = {0.0f, 0.0f, -kPanelDistanceMeters};
                    baseLayer.size = {kPanelWidthMeters, panelHeight};
                    layers.push_back(reinterpret_cast<const XrCompositionLayerBaseHeader*>(&baseLayer));

                    const bool canOverlayStereo = stereo.active &&
                        leftSwapchain_.Handle() != XR_NULL_HANDLE &&
                        rightSwapchain_.Handle() != XR_NULL_HANDLE &&
                        stereo.clientWidth > 0 && stereo.clientHeight > 0 &&
                        stereo.panelWidth > 1 && stereo.panelHeight > 1;

                    if (canOverlayStereo) {
                        const float normCenterX =
                            (stereo.panelLeft + stereo.panelWidth * 0.5f) /
                            static_cast<float>(stereo.clientWidth);
                        const float normCenterY =
                            (stereo.panelTop + stereo.panelHeight * 0.5f) /
                            static_cast<float>(stereo.clientHeight);
                        const float x = (normCenterX - 0.5f) * kPanelWidthMeters;
                        const float y = (0.5f - normCenterY) * panelHeight;
                        const float w = stereo.panelWidth /
                            static_cast<float>(stereo.clientWidth) * kPanelWidthMeters;
                        const float h = stereo.panelHeight /
                            static_cast<float>(stereo.clientHeight) * panelHeight;

                        FillEyeLayer(
                            leftLayer,
                            leftSwapchain_,
                            XR_EYE_VISIBILITY_LEFT,
                            x,
                            y,
                            w,
                            h);
                        FillEyeLayer(
                            rightLayer,
                            rightSwapchain_,
                            XR_EYE_VISIBILITY_RIGHT,
                            x,
                            y,
                            w,
                            h);

                        layers.push_back(reinterpret_cast<const XrCompositionLayerBaseHeader*>(&leftLayer));
                        layers.push_back(reinterpret_cast<const XrCompositionLayerBaseHeader*>(&rightLayer));
                    }
                }
            }

            XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
            endInfo.displayTime = frameState.predictedDisplayTime;
            endInfo.environmentBlendMode = blendMode_;
            endInfo.layerCount = static_cast<std::uint32_t>(layers.size());
            endInfo.layers = layers.empty() ? nullptr : layers.data();
            CheckXr(xrEndFrame(session_, &endInfo), "xrEndFrame");
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
    SharedStereoReader sharedStereo_;
    XrSwapchainTexture baseSwapchain_;
    XrSwapchainTexture leftSwapchain_;
    XrSwapchainTexture rightSwapchain_;

    void InitializeOpenXr() {
        std::uint32_t extensionCount = 0;
        CheckXr(xrEnumerateInstanceExtensionProperties(nullptr, 0, &extensionCount, nullptr),
            "xrEnumerateInstanceExtensionProperties(count)");
        std::vector<XrExtensionProperties> extensions(
            extensionCount,
            {XR_TYPE_EXTENSION_PROPERTIES});
        CheckXr(
            xrEnumerateInstanceExtensionProperties(nullptr, extensionCount, &extensionCount, extensions.data()),
            "xrEnumerateInstanceExtensionProperties");

        const auto hasD3D11 = std::any_of(
            extensions.begin(),
            extensions.end(),
            [](const XrExtensionProperties& e) {
                return std::strcmp(e.extensionName, XR_KHR_D3D11_ENABLE_EXTENSION_NAME) == 0;
            });
        if (!hasD3D11) {
            throw std::runtime_error("Active OpenXR runtime does not expose XR_KHR_D3D11_enable");
        }

        const char* enabledExtensions[] = {XR_KHR_D3D11_ENABLE_EXTENSION_NAME};
        XrInstanceCreateInfo create{XR_TYPE_INSTANCE_CREATE_INFO};
        std::strncpy(create.applicationInfo.applicationName, "GeoGebraForQuest PC", XR_MAX_APPLICATION_NAME_SIZE - 1);
        create.applicationInfo.applicationVersion = 1;
        std::strncpy(create.applicationInfo.engineName, "GeoGebraForQuestPC", XR_MAX_ENGINE_NAME_SIZE - 1);
        create.applicationInfo.engineVersion = 1;
        create.applicationInfo.apiVersion = XR_CURRENT_API_VERSION;
        create.enabledExtensionCount = 1;
        create.enabledExtensionNames = enabledExtensions;
        CheckXr(xrCreateInstance(&create, &instance_), "xrCreateInstance");

        XrInstanceProperties properties{XR_TYPE_INSTANCE_PROPERTIES};
        CheckXr(xrGetInstanceProperties(instance_, &properties), "xrGetInstanceProperties");
        Log(std::string("OpenXR runtime: ") + properties.runtimeName);

        XrSystemGetInfo systemInfo{XR_TYPE_SYSTEM_GET_INFO};
        systemInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
        CheckXr(xrGetSystem(instance_, &systemInfo, &systemId_), "xrGetSystem");

        std::uint32_t blendCount = 0;
        CheckXr(
            xrEnumerateEnvironmentBlendModes(
                instance_, systemId_, XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO, 0, &blendCount, nullptr),
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
            blendMode_ = std::find(modes.begin(), modes.end(), XR_ENVIRONMENT_BLEND_MODE_OPAQUE) != modes.end()
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
        if (!getRequirements) throw std::runtime_error("D3D11 graphics requirements function missing");

        XrGraphicsRequirementsD3D11KHR requirements{XR_TYPE_GRAPHICS_REQUIREMENTS_D3D11_KHR};
        CheckXr(getRequirements(instance_, systemId_, &requirements), "xrGetD3D11GraphicsRequirementsKHR");

        ComPtr<IDXGIFactory1> factory;
        if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(factory.ReleaseAndGetAddressOf())))) {
            throw std::runtime_error("CreateDXGIFactory1 failed");
        }

        ComPtr<IDXGIAdapter1> selected;
        for (UINT i = 0;; ++i) {
            ComPtr<IDXGIAdapter1> adapter;
            if (factory->EnumAdapters1(i, adapter.ReleaseAndGetAddressOf()) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_ADAPTER_DESC1 desc{};
            adapter->GetDesc1(&desc);
            if (LuidEqual(desc.AdapterLuid, requirements.adapterLuid)) {
                selected = adapter;
                break;
            }
        }
        if (!selected) throw std::runtime_error("OpenXR-required DXGI adapter not found");

        const D3D_FEATURE_LEVEL levels[] = {
            D3D_FEATURE_LEVEL_12_1,
            D3D_FEATURE_LEVEL_12_0,
            D3D_FEATURE_LEVEL_11_1,
            D3D_FEATURE_LEVEL_11_0,
        };
        D3D_FEATURE_LEVEL obtained{};
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
#ifndef NDEBUG
        flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif
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
#ifndef NDEBUG
        if (FAILED(hr)) {
            flags &= ~D3D11_CREATE_DEVICE_DEBUG;
            hr = D3D11CreateDevice(
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
        }
#endif
        if (FAILED(hr)) throw std::runtime_error("D3D11CreateDevice failed");
        if (obtained < requirements.minFeatureLevel) {
            throw std::runtime_error("D3D feature level is below OpenXR runtime minimum");
        }
    }

    void CreateSession() {
        XrGraphicsBindingD3D11KHR binding{XR_TYPE_GRAPHICS_BINDING_D3D11_KHR};
        binding.device = device_.Get();

        XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
        sessionInfo.next = &binding;
        sessionInfo.systemId = systemId_;
        CheckXr(xrCreateSession(instance_, &sessionInfo, &session_), "xrCreateSession");

        XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        spaceInfo.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
        spaceInfo.poseInReferenceSpace.orientation = {0.0f, 0.0f, 0.0f, 1.0f};
        spaceInfo.poseInReferenceSpace.position = {0.0f, 0.0f, 0.0f};
        CheckXr(xrCreateReferenceSpace(session_, &spaceInfo, &localSpace_), "xrCreateReferenceSpace");

        std::uint32_t formatCount = 0;
        CheckXr(xrEnumerateSwapchainFormats(session_, 0, &formatCount, nullptr),
            "xrEnumerateSwapchainFormats(count)");
        std::vector<std::int64_t> formats(formatCount);
        CheckXr(xrEnumerateSwapchainFormats(session_, formatCount, &formatCount, formats.data()),
            "xrEnumerateSwapchainFormats");

        const std::int64_t preferred[] = {
            DXGI_FORMAT_B8G8R8A8_UNORM,
            DXGI_FORMAT_B8G8R8A8_UNORM_SRGB,
        };
        bool found = false;
        for (const auto wanted : preferred) {
            if (std::find(formats.begin(), formats.end(), wanted) != formats.end()) {
                swapchainFormat_ = wanted;
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::runtime_error("OpenXR runtime does not expose BGRA8 swapchain format");
        }
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance_, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto* changed = reinterpret_cast<const XrEventDataSessionStateChanged*>(&event);
                sessionState_ = changed->state;

                switch (sessionState_) {
                    case XR_SESSION_STATE_READY: {
                        XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
                        begin.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                        CheckXr(xrBeginSession(session_, &begin), "xrBeginSession");
                        sessionRunning_ = true;
                        Log("OpenXR session READY -> running");
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

    void FillEyeLayer(
        XrCompositionLayerQuad& layer,
        const XrSwapchainTexture& swapchain,
        XrEyeVisibility eye,
        float x,
        float y,
        float width,
        float height) const {
        layer.layerFlags = 0;
        layer.space = localSpace_;
        layer.eyeVisibility = eye;
        layer.subImage.swapchain = swapchain.Handle();
        layer.subImage.imageRect.offset = {0, 0};
        layer.subImage.imageRect.extent = {swapchain.Width(), swapchain.Height()};
        layer.subImage.imageArrayIndex = 0;
        layer.pose.orientation = {0.0f, 0.0f, 0.0f, 1.0f};
        layer.pose.position = {x, y, -(kPanelDistanceMeters - 0.001f)};
        layer.size = {std::max(0.01f, width), std::max(0.01f, height)};
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
        Log("GeoGebraForQuest PC XR companion starting, host pid=" + std::to_string(pid));
        XrMirrorApp app(pid);
        return app.Run();
    } catch (const std::exception& e) {
        Log(std::string("Fatal: ") + e.what());
        return 20;
    } catch (...) {
        Log("Fatal: unknown exception");
        return 21;
    }
}
