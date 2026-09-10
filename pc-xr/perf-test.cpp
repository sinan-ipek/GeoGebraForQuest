#include "v11-render.hpp"

#include <dxgi1_2.h>
#include <iomanip>
#include <sstream>

using namespace ggqv11;

namespace {

constexpr XrViewConfigurationType kViewConfiguration =
    XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
constexpr int kDefaultSeconds = 30;
constexpr int kSyntheticWidth = 1600;
constexpr int kSyntheticHeight = 1000;
constexpr int kSyntheticEyeWidth = 1600;
constexpr int kSyntheticEyeHeight = 1000;

std::string SiblingPath(const char* fileName) {
    char path[MAX_PATH]{};
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    std::string result(path);
    const auto slash = result.find_last_of("\\/");
    if (slash != std::string::npos) {
        result.resize(slash + 1);
    } else {
        result.clear();
    }
    result += fileName;
    return result;
}

void PerfLog(const std::string& text) {
    static std::ofstream log(SiblingPath("GeoGebraForQuestPC.XR.PerfTest.log"),
                             std::ios::out | std::ios::app);
    if (log.is_open()) {
        log << text << std::endl;
        log.flush();
    }
}

int ParseSeconds(int argc, wchar_t** argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::wstring(argv[i]) == L"--seconds") {
            const int value = static_cast<int>(std::wcstol(argv[i + 1], nullptr, 10));
            return std::clamp(value, 5, 300);
        }
    }
    return kDefaultSeconds;
}

class XrGpuPerfTest {
public:
    explicit XrGpuPerfTest(int seconds) : seconds_(seconds) {}

    ~XrGpuPerfTest() {
        Shutdown();
    }

    void Initialize() {
        CreateInstance();
        GetSystem();
        CreateD3D11Device();
        CreateSession();
        CreateReferenceSpace();
        CreateProjectionSwapchain();

        renderer_.Initialize(device_.Get());
        renderer_.InitializeCursor(device_.Get(), context_.Get());
        CreateSyntheticTextures();

        csv_.open(SiblingPath("GeoGebraForQuestPC.XR.PerfTest.csv"),
                  std::ios::out | std::ios::trunc);
        if (csv_.is_open()) {
            csv_ << "frame,target_hz,wait_ms,workload_ms,loop_ms,should_render,layer_submitted\n";
            csv_.flush();
        }

        PerfLog("============================================================");
        PerfLog("GeoGebraForQuest PC v0.14.0 XR GPU Performance Test");
        PerfLog("Path: synthetic VRAM texture -> D3D11 -> OpenXR -> Meta Link -> Quest");
        PerfLog("Excluded: GeoGebra, CEF, JavaScript, getImageData, MMF pixels, CPU upload");
        PerfLog("Duration=" + std::to_string(seconds_) + " s");
    }

    int Run() {
        while (!exitRequested_ && !testComplete_) {
            PollEvents();

            if (!sessionRunning_) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            RenderFrame();
        }

        WriteSummary();
        return 0;
    }

    const std::string& Summary() const {
        return summary_;
    }

private:
    int seconds_{};

    XrInstance instance_{XR_NULL_HANDLE};
    XrSystemId systemId_{XR_NULL_SYSTEM_ID};
    XrSession session_{XR_NULL_HANDLE};
    XrSpace localSpace_{XR_NULL_HANDLE};
    XrSessionState sessionState_{XR_SESSION_STATE_UNKNOWN};
    bool sessionRunning_{};
    bool exitRequested_{};
    bool testComplete_{};

    ComPtr<ID3D11Device> device_;
    ComPtr<ID3D11DeviceContext> context_;

    ProjectionSwapchain projectionSwapchain_;
    ProjectionRenderer renderer_;
    DXGI_FORMAT projectionFormat_{DXGI_FORMAT_UNKNOWN};

    SourceTexture baseTexture_;
    SourceTexture stereoTexture_;

    std::vector<XrViewConfigurationView> viewConfigViews_;
    std::array<XrView, 2> views_{{
        {XR_TYPE_VIEW},
        {XR_TYPE_VIEW}
    }};

    std::ofstream csv_;
    std::vector<double> waitSamples_;
    std::vector<double> workloadSamples_;
    std::vector<double> loopSamples_;
    std::uint64_t frameCount_{};
    std::uint64_t shouldRenderCount_{};
    std::uint64_t submittedCount_{};
    double latestTargetHz_{};
    bool metricsStarted_{};
    std::chrono::steady_clock::time_point metricsStart_{};
    std::chrono::steady_clock::time_point previousFrameEnd_{};
    std::string summary_;

    void CreateInstance() {
        std::uint32_t extensionCount = 0;
        CheckXr(xrEnumerateInstanceExtensionProperties(
                    nullptr, 0, &extensionCount, nullptr),
                "xrEnumerateInstanceExtensionProperties(count)");

        std::vector<XrExtensionProperties> extensions(
            extensionCount, {XR_TYPE_EXTENSION_PROPERTIES});
        CheckXr(xrEnumerateInstanceExtensionProperties(
                    nullptr,
                    extensionCount,
                    &extensionCount,
                    extensions.data()),
                "xrEnumerateInstanceExtensionProperties(list)");

        bool d3d11Available = false;
        for (const auto& extension : extensions) {
            if (std::strcmp(extension.extensionName,
                            XR_KHR_D3D11_ENABLE_EXTENSION_NAME) == 0) {
                d3d11Available = true;
                break;
            }
        }
        if (!d3d11Available) {
            throw std::runtime_error("XR_KHR_D3D11_enable is not available");
        }

        const char* enabledExtensions[] = {
            XR_KHR_D3D11_ENABLE_EXTENSION_NAME
        };

        XrInstanceCreateInfo createInfo{XR_TYPE_INSTANCE_CREATE_INFO};
        std::strcpy(createInfo.applicationInfo.applicationName, "GGQ XR GPU PerfTest");
        createInfo.applicationInfo.applicationVersion = 1400;
        std::strcpy(createInfo.applicationInfo.engineName, "GGQ Native D3D11");
        createInfo.applicationInfo.engineVersion = 1400;
        createInfo.applicationInfo.apiVersion = XR_CURRENT_API_VERSION;
        createInfo.enabledExtensionCount = 1;
        createInfo.enabledExtensionNames = enabledExtensions;

        CheckXr(xrCreateInstance(&createInfo, &instance_), "xrCreateInstance");

        XrInstanceProperties properties{XR_TYPE_INSTANCE_PROPERTIES};
        CheckXr(xrGetInstanceProperties(instance_, &properties),
                "xrGetInstanceProperties");

        std::ostringstream runtime;
        runtime << "OpenXR runtime=" << properties.runtimeName
                << " version="
                << XR_VERSION_MAJOR(properties.runtimeVersion) << "."
                << XR_VERSION_MINOR(properties.runtimeVersion) << "."
                << XR_VERSION_PATCH(properties.runtimeVersion);
        PerfLog(runtime.str());
    }

    void GetSystem() {
        XrSystemGetInfo getInfo{XR_TYPE_SYSTEM_GET_INFO};
        getInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
        CheckXr(xrGetSystem(instance_, &getInfo, &systemId_), "xrGetSystem");
    }

    void CreateD3D11Device() {
        PFN_xrGetD3D11GraphicsRequirementsKHR getRequirements = nullptr;
        CheckXr(xrGetInstanceProcAddr(
                    instance_,
                    "xrGetD3D11GraphicsRequirementsKHR",
                    reinterpret_cast<PFN_xrVoidFunction*>(&getRequirements)),
                "xrGetInstanceProcAddr(xrGetD3D11GraphicsRequirementsKHR)");
        if (!getRequirements) {
            throw std::runtime_error("xrGetD3D11GraphicsRequirementsKHR is null");
        }

        XrGraphicsRequirementsD3D11KHR requirements{
            XR_TYPE_GRAPHICS_REQUIREMENTS_D3D11_KHR};
        CheckXr(getRequirements(instance_, systemId_, &requirements),
                "xrGetD3D11GraphicsRequirementsKHR");

        ComPtr<IDXGIFactory1> factory;
        CheckHr(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");

        ComPtr<IDXGIAdapter1> selectedAdapter;
        DXGI_ADAPTER_DESC1 selectedDesc{};
        for (UINT index = 0;; ++index) {
            ComPtr<IDXGIAdapter1> adapter;
            if (factory->EnumAdapters1(index, &adapter) == DXGI_ERROR_NOT_FOUND) {
                break;
            }

            DXGI_ADAPTER_DESC1 desc{};
            CheckHr(adapter->GetDesc1(&desc), "IDXGIAdapter1::GetDesc1");
            if (LuidEqual(desc.AdapterLuid, requirements.adapterLuid)) {
                selectedAdapter = adapter;
                selectedDesc = desc;
                break;
            }
        }

        if (!selectedAdapter) {
            throw std::runtime_error("OpenXR-required D3D11 adapter was not found");
        }

        D3D_FEATURE_LEVEL featureLevel{};
        const UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
        CheckHr(D3D11CreateDevice(
                    selectedAdapter.Get(),
                    D3D_DRIVER_TYPE_UNKNOWN,
                    nullptr,
                    flags,
                    nullptr,
                    0,
                    D3D11_SDK_VERSION,
                    &device_,
                    &featureLevel,
                    &context_),
                "D3D11CreateDevice(OpenXR adapter)");

        std::wstring wideName(selectedDesc.Description);
        std::string adapterName(wideName.begin(), wideName.end());
        std::ostringstream adapterLog;
        adapterLog << "D3D11 adapter=" << adapterName
                   << " featureLevel=0x" << std::hex
                   << static_cast<unsigned int>(featureLevel);
        PerfLog(adapterLog.str());
    }

    void CreateSession() {
        XrGraphicsBindingD3D11KHR binding{XR_TYPE_GRAPHICS_BINDING_D3D11_KHR};
        binding.device = device_.Get();

        XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
        sessionInfo.next = &binding;
        sessionInfo.systemId = systemId_;
        CheckXr(xrCreateSession(instance_, &sessionInfo, &session_),
                "xrCreateSession");
    }

    void CreateReferenceSpace() {
        XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        spaceInfo.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
        spaceInfo.poseInReferenceSpace.orientation.w = 1.0f;
        CheckXr(xrCreateReferenceSpace(session_, &spaceInfo, &localSpace_),
                "xrCreateReferenceSpace(LOCAL)");
    }

    void CreateProjectionSwapchain() {
        std::uint32_t viewCount = 0;
        CheckXr(xrEnumerateViewConfigurationViews(
                    instance_, systemId_, kViewConfiguration,
                    0, &viewCount, nullptr),
                "xrEnumerateViewConfigurationViews(count)");
        if (viewCount != 2) {
            throw std::runtime_error("PRIMARY_STEREO did not report exactly two views");
        }

        viewConfigViews_.assign(
            viewCount,
            XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW});
        CheckXr(xrEnumerateViewConfigurationViews(
                    instance_, systemId_, kViewConfiguration,
                    viewCount, &viewCount, viewConfigViews_.data()),
                "xrEnumerateViewConfigurationViews(list)");

        int width = 1;
        int height = 1;
        for (const auto& view : viewConfigViews_) {
            width = std::max(width,
                static_cast<int>(view.recommendedImageRectWidth));
            height = std::max(height,
                static_cast<int>(view.recommendedImageRectHeight));
        }

        std::uint32_t formatCount = 0;
        CheckXr(xrEnumerateSwapchainFormats(
                    session_, 0, &formatCount, nullptr),
                "xrEnumerateSwapchainFormats(count)");
        std::vector<std::int64_t> formats(formatCount);
        CheckXr(xrEnumerateSwapchainFormats(
                    session_, formatCount, &formatCount, formats.data()),
                "xrEnumerateSwapchainFormats(list)");

        const DXGI_FORMAT preferred[] = {
            DXGI_FORMAT_R8G8B8A8_UNORM_SRGB,
            DXGI_FORMAT_B8G8R8A8_UNORM_SRGB,
            DXGI_FORMAT_R8G8B8A8_UNORM,
            DXGI_FORMAT_B8G8R8A8_UNORM
        };

        for (const DXGI_FORMAT candidate : preferred) {
            const auto value = static_cast<std::int64_t>(candidate);
            if (std::find(formats.begin(), formats.end(), value) != formats.end()) {
                projectionFormat_ = candidate;
                break;
            }
        }
        if (projectionFormat_ == DXGI_FORMAT_UNKNOWN) {
            throw std::runtime_error("No supported D3D11 color swapchain format");
        }

        projectionSwapchain_.Create(
            session_,
            static_cast<std::int64_t>(projectionFormat_),
            width,
            height);

        PerfLog("Projection swapchain=" + std::to_string(width) + "x" +
                std::to_string(height) + " arraySize=2");
    }

    static void PutPixel(
        std::vector<std::uint8_t>& pixels,
        int width,
        int x,
        int y,
        std::uint8_t b,
        std::uint8_t g,
        std::uint8_t r) {

        const std::size_t i =
            (static_cast<std::size_t>(y) * width + x) * 4;
        pixels[i + 0] = b;
        pixels[i + 1] = g;
        pixels[i + 2] = r;
        pixels[i + 3] = 255;
    }

    void CreateSyntheticTextures() {
        std::vector<std::uint8_t> base(
            static_cast<std::size_t>(kSyntheticWidth) * kSyntheticHeight * 4,
            255);

        for (int y = 0; y < kSyntheticHeight; ++y) {
            for (int x = 0; x < kSyntheticWidth; ++x) {
                const bool major = (x % 200 < 3) || (y % 200 < 3);
                const bool minor = (x % 50 == 0) || (y % 50 == 0);
                std::uint8_t level = 28;
                if (minor) level = 48;
                if (major) level = 78;
                PutPixel(base, kSyntheticWidth, x, y, level, level, level);
            }
        }

        baseTexture_.Upload(
            device_.Get(), context_.Get(), base.data(),
            kSyntheticWidth, kSyntheticHeight, kSyntheticWidth * 4);

        const int sbsWidth = kSyntheticEyeWidth * 2;
        std::vector<std::uint8_t> sbs(
            static_cast<std::size_t>(sbsWidth) * kSyntheticEyeHeight * 4,
            255);

        for (int eye = 0; eye < 2; ++eye) {
            const int eyeOffset = eye * kSyntheticEyeWidth;
            const int disparity = eye == 0 ? 22 : -22;
            const int cx = kSyntheticEyeWidth / 2 + disparity;
            const int cy = kSyntheticEyeHeight / 2;

            for (int y = 0; y < kSyntheticEyeHeight; ++y) {
                for (int x = 0; x < kSyntheticEyeWidth; ++x) {
                    const bool major = (x % 160 < 3) || (y % 160 < 3);
                    const bool minor = (x % 40 == 0) || (y % 40 == 0);
                    const int dx = x - cx;
                    const int dy = y - cy;
                    const bool circle =
                        std::abs(dx * dx + dy * dy - 170 * 170) < 1600;
                    const bool box =
                        std::abs(dx) < 110 && std::abs(dy) < 110;

                    std::uint8_t b = 22;
                    std::uint8_t g = 22;
                    std::uint8_t r = 30;
                    if (minor) {
                        b = 48; g = 48; r = 62;
                    }
                    if (major) {
                        b = 86; g = 86; r = 110;
                    }
                    if (circle) {
                        b = 255; g = 210; r = 70;
                    }
                    if (box) {
                        b = 60; g = 180; r = 255;
                    }

                    PutPixel(sbs, sbsWidth, eyeOffset + x, y, b, g, r);
                }
            }
        }

        stereoTexture_.Upload(
            device_.Get(), context_.Get(), sbs.data(),
            sbsWidth, kSyntheticEyeHeight, sbsWidth * 4);

        PerfLog("Synthetic textures uploaded once to VRAM: base=" +
                std::to_string(kSyntheticWidth) + "x" +
                std::to_string(kSyntheticHeight) +
                " stereo=" + std::to_string(sbsWidth) + "x" +
                std::to_string(kSyntheticEyeHeight));
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance_, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto& changed =
                    *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                sessionState_ = changed.state;
                PerfLog(std::string("sessionState=") +
                        SessionStateName(sessionState_));

                if (sessionState_ == XR_SESSION_STATE_READY && !sessionRunning_) {
                    XrSessionBeginInfo beginInfo{XR_TYPE_SESSION_BEGIN_INFO};
                    beginInfo.primaryViewConfigurationType = kViewConfiguration;
                    CheckXr(xrBeginSession(session_, &beginInfo), "xrBeginSession");
                    sessionRunning_ = true;
                    PerfLog("xrBeginSession success");
                } else if (sessionState_ == XR_SESSION_STATE_STOPPING &&
                           sessionRunning_) {
                    CheckXr(xrEndSession(session_), "xrEndSession");
                    sessionRunning_ = false;
                } else if (sessionState_ == XR_SESSION_STATE_EXITING ||
                           sessionState_ == XR_SESSION_STATE_LOSS_PENDING) {
                    exitRequested_ = true;
                }
            } else if (event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING) {
                exitRequested_ = true;
            }
            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
    }

    PanelRect BaseRect() const {
        const float height =
            kScreenWidthMeters * static_cast<float>(kSyntheticHeight) /
            static_cast<float>(kSyntheticWidth);
        return {
            -kScreenWidthMeters * 0.5f,
             kScreenWidthMeters * 0.5f,
             height * 0.5f,
            -height * 0.5f
        };
    }

    static PanelRect StereoRect(const PanelRect& base) {
        const float width = base.right - base.left;
        const float height = base.top - base.bottom;
        return {
            base.left + width * 0.06f,
            base.right - width * 0.06f,
            base.top - height * 0.08f,
            base.bottom + height * 0.08f
        };
    }

    void RenderFrame() {
        const auto loopStart = std::chrono::steady_clock::now();

        XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
        XrFrameState frameState{XR_TYPE_FRAME_STATE};
        CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");
        const auto afterWait = std::chrono::steady_clock::now();

        XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
        CheckXr(xrBeginFrame(session_, &beginInfo), "xrBeginFrame");
        const auto workloadStart = std::chrono::steady_clock::now();

        std::array<XrCompositionLayerProjectionView, 2> projectionViews{{
            {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}
        }};
        XrCompositionLayerProjection projectionLayer{
            XR_TYPE_COMPOSITION_LAYER_PROJECTION};
        std::array<const XrCompositionLayerBaseHeader*, 1> layers{};
        std::uint32_t layerCount = 0;

        if (frameState.predictedDisplayPeriod > 0) {
            latestTargetHz_ =
                1.0e9 / static_cast<double>(frameState.predictedDisplayPeriod);
        }

        if (frameState.shouldRender) {
            ++shouldRenderCount_;

            XrViewLocateInfo locateInfo{XR_TYPE_VIEW_LOCATE_INFO};
            locateInfo.viewConfigurationType = kViewConfiguration;
            locateInfo.displayTime = frameState.predictedDisplayTime;
            locateInfo.space = localSpace_;

            XrViewState viewState{XR_TYPE_VIEW_STATE};
            std::uint32_t viewCount = 0;
            for (auto& view : views_) {
                view = {XR_TYPE_VIEW};
            }
            CheckXr(xrLocateViews(
                        session_,
                        &locateInfo,
                        &viewState,
                        static_cast<std::uint32_t>(views_.size()),
                        &viewCount,
                        views_.data()),
                    "xrLocateViews");

            constexpr XrViewStateFlags requiredViewFlags =
                XR_VIEW_STATE_POSITION_VALID_BIT |
                XR_VIEW_STATE_ORIENTATION_VALID_BIT;

            if (viewCount == 2 &&
                (viewState.viewStateFlags & requiredViewFlags) == requiredViewFlags) {

                const PanelRect baseRect = BaseRect();
                const PanelRect stereoRect = StereoRect(baseRect);
                const std::uint32_t imageIndex = projectionSwapchain_.Acquire();
                ID3D11Texture2D* target = projectionSwapchain_.Texture(imageIndex);

                const double phase = static_cast<double>(frameCount_) * 0.045;
                const float cursorX = static_cast<float>(std::sin(phase) * 0.55);
                const float cursorY = static_cast<float>(std::cos(phase * 0.71) * 0.24);

                for (std::uint32_t eye = 0; eye < 2; ++eye) {
                    renderer_.RenderEye(
                        device_.Get(),
                        context_.Get(),
                        target,
                        projectionFormat_,
                        eye,
                        projectionSwapchain_.Width(),
                        projectionSwapchain_.Height(),
                        views_[eye],
                        baseTexture_.Srv(),
                        baseRect,
                        stereoTexture_.Srv(),
                        &stereoRect,
                        eye == 1,
                        true,
                        cursorX,
                        cursorY);

                    projectionViews[eye].pose = views_[eye].pose;
                    projectionViews[eye].fov = views_[eye].fov;
                    projectionViews[eye].subImage.swapchain =
                        projectionSwapchain_.Handle();
                    projectionViews[eye].subImage.imageRect.offset = {0, 0};
                    projectionViews[eye].subImage.imageRect.extent = {
                        projectionSwapchain_.Width(),
                        projectionSwapchain_.Height()};
                    projectionViews[eye].subImage.imageArrayIndex = eye;
                }

                projectionSwapchain_.Release();

                projectionLayer.space = localSpace_;
                projectionLayer.viewCount =
                    static_cast<std::uint32_t>(projectionViews.size());
                projectionLayer.views = projectionViews.data();
                layers[0] = reinterpret_cast<const XrCompositionLayerBaseHeader*>(
                    &projectionLayer);
                layerCount = 1;
                ++submittedCount_;
            }
        }

        XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
        endInfo.displayTime = frameState.predictedDisplayTime;
        endInfo.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
        endInfo.layerCount = layerCount;
        endInfo.layers = layerCount ? layers.data() : nullptr;
        CheckXr(xrEndFrame(session_, &endInfo), "xrEndFrame");

        const auto frameEnd = std::chrono::steady_clock::now();
        const double waitMs =
            std::chrono::duration<double, std::milli>(afterWait - loopStart).count();
        const double workloadMs =
            std::chrono::duration<double, std::milli>(frameEnd - workloadStart).count();
        double loopMs = 0.0;
        if (metricsStarted_) {
            loopMs =
                std::chrono::duration<double, std::milli>(frameEnd - previousFrameEnd_).count();
        }

        if (!metricsStarted_) {
            metricsStarted_ = true;
            metricsStart_ = frameEnd;
        } else if (loopMs > 0.0) {
            loopSamples_.push_back(loopMs);
        }
        previousFrameEnd_ = frameEnd;

        waitSamples_.push_back(waitMs);
        workloadSamples_.push_back(workloadMs);
        ++frameCount_;

        if (csv_.is_open()) {
            csv_ << frameCount_ << ','
                 << std::fixed << std::setprecision(3)
                 << latestTargetHz_ << ','
                 << waitMs << ','
                 << workloadMs << ','
                 << loopMs << ','
                 << (frameState.shouldRender ? 1 : 0) << ','
                 << (layerCount ? 1 : 0) << '\n';
            if ((frameCount_ % 180) == 0) {
                csv_.flush();
            }
        }

        if ((frameCount_ % 180) == 0) {
            PerfLog(CurrentSummary(false));
        }

        const double elapsedSeconds =
            std::chrono::duration<double>(frameEnd - metricsStart_).count();
        if (elapsedSeconds >= static_cast<double>(seconds_)) {
            testComplete_ = true;
        }
    }

    static double Average(const std::vector<double>& values) {
        if (values.empty()) return 0.0;
        double total = 0.0;
        for (double value : values) total += value;
        return total / static_cast<double>(values.size());
    }

    static double Percentile95(const std::vector<double>& values) {
        if (values.empty()) return 0.0;
        std::vector<double> copy = values;
        std::sort(copy.begin(), copy.end());
        const std::size_t index = std::min(
            copy.size() - 1,
            static_cast<std::size_t>(std::ceil(copy.size() * 0.95) - 1));
        return copy[index];
    }

    std::string CurrentSummary(bool final) const {
        double elapsedSeconds = 0.0;
        if (metricsStarted_) {
            elapsedSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - metricsStart_).count();
        }
        const double deliveredFps =
            elapsedSeconds > 0.0
                ? static_cast<double>(frameCount_) / elapsedSeconds
                : 0.0;
        const double submitPercent =
            frameCount_ > 0
                ? 100.0 * static_cast<double>(submittedCount_) /
                    static_cast<double>(frameCount_)
                : 0.0;

        std::ostringstream out;
        out << (final ? "FINAL " : "LIVE ")
            << std::fixed << std::setprecision(2)
            << "target=" << latestTargetHz_ << " Hz"
            << " delivered=" << deliveredFps << " FPS"
            << " workload_avg=" << Average(workloadSamples_) << " ms"
            << " workload_p95=" << Percentile95(workloadSamples_) << " ms"
            << " loop_p95=" << Percentile95(loopSamples_) << " ms"
            << " submitted=" << submitPercent << "%"
            << " frames=" << frameCount_;
        return out.str();
    }

    void WriteSummary() {
        summary_ = CurrentSummary(true);
        PerfLog(summary_);
        PerfLog("CSV=" + SiblingPath("GeoGebraForQuestPC.XR.PerfTest.csv"));
        PerfLog("LOG=" + SiblingPath("GeoGebraForQuestPC.XR.PerfTest.log"));
        if (csv_.is_open()) {
            csv_.flush();
            csv_.close();
        }
    }

    void Shutdown() noexcept {
        try {
            projectionSwapchain_.Reset();
        } catch (...) {
        }

        baseTexture_.Reset();
        stereoTexture_.Reset();

        if (localSpace_ != XR_NULL_HANDLE) {
            xrDestroySpace(localSpace_);
            localSpace_ = XR_NULL_HANDLE;
        }
        if (session_ != XR_NULL_HANDLE) {
            if (sessionRunning_) {
                xrEndSession(session_);
                sessionRunning_ = false;
            }
            xrDestroySession(session_);
            session_ = XR_NULL_HANDLE;
        }
        if (instance_ != XR_NULL_HANDLE) {
            xrDestroyInstance(instance_);
            instance_ = XR_NULL_HANDLE;
        }

        context_.Reset();
        device_.Reset();
    }
};

} // namespace

int wmain(int argc, wchar_t** argv) {
    const int seconds = ParseSeconds(argc, argv);

    try {
        XrGpuPerfTest app(seconds);
        app.Initialize();
        const int result = app.Run();

        const std::string summary = app.Summary();
        const std::wstring wideSummary(summary.begin(), summary.end());
        MessageBoxW(
            nullptr,
            wideSummary.c_str(),
            L"GeoGebraForQuest PC v0.14.0 XR GPU Performance Test",
            MB_OK | MB_ICONINFORMATION);
        return result;
    } catch (const std::exception& ex) {
        PerfLog(std::string("FATAL: ") + ex.what());
        const std::string message = std::string("XR GPU PerfTest failed:\n") + ex.what();
        const std::wstring wide(message.begin(), message.end());
        MessageBoxW(
            nullptr,
            wide.c_str(),
            L"GeoGebraForQuest XR PerfTest Error",
            MB_OK | MB_ICONERROR);
        return 1;
    } catch (...) {
        PerfLog("FATAL: unknown exception");
        MessageBoxW(
            nullptr,
            L"Unknown XR GPU PerfTest error.",
            L"GeoGebraForQuest XR PerfTest Error",
            MB_OK | MB_ICONERROR);
        return 1;
    }
}
