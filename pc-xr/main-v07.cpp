#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#include <algorithm>
#include <array>
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
            "xrCreateSwapchain");

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
            "xrAcquireSwapchainImage");

        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(
            xrWaitSwapchainImage(handle_, &wait),
            "xrWaitSwapchainImage");

        return index;
    }

    void Release() {
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(
            xrReleaseSwapchainImage(handle_, &release),
            "xrReleaseSwapchainImage");
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

class OpenXrVisibilityTest {
public:
    explicit OpenXrVisibilityTest(DWORD hostPid)
        : hostPid_(hostPid) {
    }

    ~OpenXrVisibilityTest() {
        swapchain_.Reset();

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

        Log("v0.7 visibility test initialized. Expected headset result: BRIGHT GREEN immersive view.");

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

            if (frameState.shouldRender != lastShouldRender_) {
                lastShouldRender_ = frameState.shouldRender;
                Log(std::string("shouldRender=") +
                    (frameState.shouldRender ? "true" : "false") +
                    " state=" + SessionStateName(sessionState_));
            }

            XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
            CheckXr(
                xrBeginFrame(session_, &beginInfo),
                "xrBeginFrame");

            const XrCompositionLayerBaseHeader* submittedLayer = nullptr;
            XrCompositionLayerProjection projectionLayer{
                XR_TYPE_COMPOSITION_LAYER_PROJECTION};
            std::array<XrCompositionLayerProjectionView, 2> projectionViews{
                XrCompositionLayerProjectionView{
                    XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
                XrCompositionLayerProjectionView{
                    XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            };

            if (frameState.shouldRender) {
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

                if (viewsUsable) {
                    const std::uint32_t imageIndex = swapchain_.Acquire();
                    ID3D11Texture2D* target = swapchain_.Texture(imageIndex);

                    for (std::uint32_t eye = 0; eye < 2; ++eye) {
                        D3D11_RENDER_TARGET_VIEW_DESC rtvDesc{};
                        rtvDesc.Format =
                            static_cast<DXGI_FORMAT>(swapchainFormat_);
                        rtvDesc.ViewDimension =
                            D3D11_RTV_DIMENSION_TEXTURE2DARRAY;
                        rtvDesc.Texture2DArray.MipSlice = 0;
                        rtvDesc.Texture2DArray.FirstArraySlice = eye;
                        rtvDesc.Texture2DArray.ArraySize = 1;

                        ComPtr<ID3D11RenderTargetView> rtv;
                        CheckHr(
                            device_->CreateRenderTargetView(
                                target,
                                &rtvDesc,
                                rtv.ReleaseAndGetAddressOf()),
                            "CreateRenderTargetView");

                        const float focusedGreen[4] = {
                            0.00f, 1.00f, 0.12f, 1.00f};
                        const float visibleCyan[4] = {
                            0.00f, 0.85f, 1.00f, 1.00f};
                        const float otherYellow[4] = {
                            1.00f, 0.85f, 0.00f, 1.00f};

                        const float* clearColor = otherYellow;
                        if (sessionState_ == XR_SESSION_STATE_FOCUSED) {
                            clearColor = focusedGreen;
                        } else if (sessionState_ == XR_SESSION_STATE_VISIBLE) {
                            clearColor = visibleCyan;
                        }

                        context_->ClearRenderTargetView(rtv.Get(), clearColor);

                        projectionViews[eye].pose = views[eye].pose;
                        projectionViews[eye].fov = views[eye].fov;
                        projectionViews[eye].subImage.swapchain =
                            swapchain_.Handle();
                        projectionViews[eye].subImage.imageRect.offset = {0, 0};
                        projectionViews[eye].subImage.imageRect.extent = {
                            swapchain_.Width(), swapchain_.Height()};
                        projectionViews[eye].subImage.imageArrayIndex = eye;
                    }

                    swapchain_.Release();

                    projectionLayer.space = localSpace_;
                    projectionLayer.viewCount =
                        static_cast<std::uint32_t>(projectionViews.size());
                    projectionLayer.views = projectionViews.data();

                    submittedLayer =
                        reinterpret_cast<const XrCompositionLayerBaseHeader*>(
                            &projectionLayer);
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
    bool lastShouldRender_{};
    XrEnvironmentBlendMode blendMode_{XR_ENVIRONMENT_BLEND_MODE_OPAQUE};
    std::int64_t swapchainFormat_{DXGI_FORMAT_B8G8R8A8_UNORM};

    ComPtr<ID3D11Device> device_;
    ComPtr<ID3D11DeviceContext> context_;
    ProjectionSwapchain swapchain_;

    void InitializeOpenXr() {
        std::uint32_t extensionCount = 0;
        CheckXr(
            xrEnumerateInstanceExtensionProperties(
                nullptr, 0, &extensionCount, nullptr),
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
            "GeoGebraForQuest PC Visibility Test",
            XR_MAX_APPLICATION_NAME_SIZE - 1);
        create.applicationInfo.applicationVersion = 7;
        std::strncpy(
            create.applicationInfo.engineName,
            "GeoGebraForQuestPC-v0.7-Visibility",
            XR_MAX_ENGINE_NAME_SIZE - 1);
        create.applicationInfo.engineVersion = 7;
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

        Log(
            std::string("OpenXR runtime=") + properties.runtimeName +
            " version=" + std::to_string(XR_VERSION_MAJOR(properties.runtimeVersion)) +
            "." + std::to_string(XR_VERSION_MINOR(properties.runtimeVersion)) +
            "." + std::to_string(XR_VERSION_PATCH(properties.runtimeVersion)));

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
        const UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;

        CheckHr(
            D3D11CreateDevice(
                selected.Get(),
                D3D_DRIVER_TYPE_UNKNOWN,
                nullptr,
                flags,
                levels,
                static_cast<UINT>(std::size(levels)),
                D3D11_SDK_VERSION,
                device_.ReleaseAndGetAddressOf(),
                &obtained,
                context_.ReleaseAndGetAddressOf()),
            "D3D11CreateDevice");

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
                session_, 0, &formatCount, nullptr),
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
                "No supported 32-bit color swapchain format");
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

        swapchain_.Create(session_, swapchainFormat_, width, height);

        Log(
            "projection swapchain=" +
            std::to_string(width) + "x" +
            std::to_string(height) + " arraySize=2");
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};

        while (xrPollEvent(instance_, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto* changed =
                    reinterpret_cast<const XrEventDataSessionStateChanged*>(
                        &event);
                sessionState_ = changed->state;
                Log(std::string("sessionState=") + SessionStateName(sessionState_));

                switch (sessionState_) {
                    case XR_SESSION_STATE_READY: {
                        XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
                        begin.primaryViewConfigurationType =
                            XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                        CheckXr(
                            xrBeginSession(session_, &begin),
                            "xrBeginSession");
                        sessionRunning_ = true;
                        Log("xrBeginSession success");
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
                Log("instance loss pending");
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
            "GeoGebraForQuest PC v0.7 OpenXR visibility test starting, host pid=" +
            std::to_string(pid));
        OpenXrVisibilityTest app(pid);
        return app.Run();
    } catch (const std::exception& exception) {
        Log(std::string("Fatal: ") + exception.what());
        return 20;
    } catch (...) {
        Log("Fatal: unknown exception");
        return 21;
    }
}
