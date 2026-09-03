#include "v11-render.hpp"
#include "v13-gpu-stereo.hpp"

#include <dxgi1_2.h>

#include <iomanip>
#include <sstream>

using namespace ggqv11;
using namespace ggqv13;

namespace {

constexpr XrViewConfigurationType kViewConfiguration =
    XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
constexpr float kProjectionResolutionScale = 1.30f;
constexpr int kProjectionDimensionCap = 3072;

class OpenXrApp {
public:
    explicit OpenXrApp(DWORD hostPid) : hostPid_(hostPid) {}

    ~OpenXrApp() {
        Shutdown();
    }

    void Initialize() {
        inputWriter_.Initialize();
        CreateInstance();
        GetSystem();
        CreateD3D11Device();
        CreateSession();
        CreateReferenceSpace();
        CreateActions();
        CreateProjectionSwapchain();

        renderer_.Initialize(device_.Get());
        renderer_.InitializeCursor(device_.Get(), context_.Get());

        Log("GeoGebraForQuest PC v0.13 initialized: A GPU + B GPU direct, no JPEG/base64/CPU image transport");
    }

    int Run() {
        while (!exitRequested_ && ProcessAlive(hostPid_)) {
            PollEvents();

            if (!sessionRunning_) {
                inputWriter_.Publish(false, 0.0f, 0.0f, false);
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            RenderFrame();
        }

        inputWriter_.Publish(false, 0.0f, 0.0f, false);
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

    XrActionSet actionSet_{XR_NULL_HANDLE};
    XrAction aimAction_{XR_NULL_HANDLE};
    XrAction triggerAction_{XR_NULL_HANDLE};
    XrSpace aimSpace_{XR_NULL_HANDLE};
    XrPath rightHandPath_{XR_NULL_PATH};
    bool triggerDown_{};

    ComPtr<ID3D11Device> device_;
    ComPtr<ID3D11DeviceContext> context_;

    ProjectionSwapchain projectionSwapchain_;
    ProjectionRenderer renderer_;
    DXGI_FORMAT projectionFormat_{DXGI_FORMAT_UNKNOWN};

    GpuFrameInfoReader gpuFrameReader_;
    SharedGpuTextureCache baseTexture_;
    std::int64_t gpuSequence_{};
    GpuFrameInfo gpuFrame_{};

    StereoGpuFrameInfoReader stereoFrameReader_;
    SharedGpuTextureCache stereoTexture_;
    std::int64_t stereoSequence_{};
    StereoGpuFrameInfo stereoFrame_{};

    XrInputWriter inputWriter_;

    std::vector<XrViewConfigurationView> viewConfigViews_;
    std::array<XrView, 2> views_{{
        {XR_TYPE_VIEW},
        {XR_TYPE_VIEW}
    }};

    void CreateInstance() {
        std::uint32_t extensionCount = 0;
        CheckXr(xrEnumerateInstanceExtensionProperties(
            nullptr, 0, &extensionCount, nullptr),
            "xrEnumerateInstanceExtensionProperties(count)");

        std::vector<XrExtensionProperties> extensions(
            extensionCount,
            {XR_TYPE_EXTENSION_PROPERTIES});
        CheckXr(xrEnumerateInstanceExtensionProperties(
            nullptr,
            extensionCount,
            &extensionCount,
            extensions.data()),
            "xrEnumerateInstanceExtensionProperties(list)");

        bool d3d11Available = false;
        for (const auto& extension : extensions) {
            if (std::strcmp(
                    extension.extensionName,
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
        std::strcpy(createInfo.applicationInfo.applicationName, "GeoGebraForQuest PC");
        createInfo.applicationInfo.applicationVersion = 13;
        std::strcpy(createInfo.applicationInfo.engineName, "GGQ OpenXR");
        createInfo.applicationInfo.engineVersion = 13;
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
        Log(runtime.str());
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
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
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
        adapterLog << "OpenXR D3D11 adapter=" << adapterName
                   << " featureLevel=0x" << std::hex
                   << static_cast<unsigned int>(featureLevel);
        Log(adapterLog.str());
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

    XrPath Path(const char* text) const {
        XrPath path = XR_NULL_PATH;
        CheckXr(xrStringToPath(instance_, text, &path), "xrStringToPath");
        return path;
    }

    void CreateActions() {
        rightHandPath_ = Path("/user/hand/right");

        XrActionSetCreateInfo setInfo{XR_TYPE_ACTION_SET_CREATE_INFO};
        std::strcpy(setInfo.actionSetName, "ggq_controls");
        std::strcpy(setInfo.localizedActionSetName, "GeoGebra Controls");
        setInfo.priority = 0;
        CheckXr(xrCreateActionSet(instance_, &setInfo, &actionSet_),
            "xrCreateActionSet");

        XrActionCreateInfo aimInfo{XR_TYPE_ACTION_CREATE_INFO};
        aimInfo.actionType = XR_ACTION_TYPE_POSE_INPUT;
        std::strcpy(aimInfo.actionName, "right_aim");
        std::strcpy(aimInfo.localizedActionName, "Right Aim");
        aimInfo.countSubactionPaths = 1;
        aimInfo.subactionPaths = &rightHandPath_;
        CheckXr(xrCreateAction(actionSet_, &aimInfo, &aimAction_),
            "xrCreateAction(aim)");

        XrActionCreateInfo triggerInfo{XR_TYPE_ACTION_CREATE_INFO};
        triggerInfo.actionType = XR_ACTION_TYPE_FLOAT_INPUT;
        std::strcpy(triggerInfo.actionName, "right_trigger");
        std::strcpy(triggerInfo.localizedActionName, "Right Trigger");
        triggerInfo.countSubactionPaths = 1;
        triggerInfo.subactionPaths = &rightHandPath_;
        CheckXr(xrCreateAction(actionSet_, &triggerInfo, &triggerAction_),
            "xrCreateAction(trigger)");

        const XrPath touchProfile =
            Path("/interaction_profiles/oculus/touch_controller");
        const XrPath aimBinding =
            Path("/user/hand/right/input/aim/pose");
        const XrPath triggerBinding =
            Path("/user/hand/right/input/trigger/value");

        const XrActionSuggestedBinding bindings[] = {
            {aimAction_, aimBinding},
            {triggerAction_, triggerBinding}
        };
        XrInteractionProfileSuggestedBinding suggested{
            XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
        suggested.interactionProfile = touchProfile;
        suggested.countSuggestedBindings =
            static_cast<std::uint32_t>(std::size(bindings));
        suggested.suggestedBindings = bindings;

        const XrResult suggestResult =
            xrSuggestInteractionProfileBindings(instance_, &suggested);
        if (XR_FAILED(suggestResult)) {
            Log("xrSuggestInteractionProfileBindings(Oculus Touch) failed result=" +
                std::to_string(suggestResult));
        }

        XrSessionActionSetsAttachInfo attachInfo{
            XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};
        attachInfo.countActionSets = 1;
        attachInfo.actionSets = &actionSet_;
        CheckXr(xrAttachSessionActionSets(session_, &attachInfo),
            "xrAttachSessionActionSets");

        XrActionSpaceCreateInfo actionSpaceInfo{
            XR_TYPE_ACTION_SPACE_CREATE_INFO};
        actionSpaceInfo.action = aimAction_;
        actionSpaceInfo.subactionPath = rightHandPath_;
        actionSpaceInfo.poseInActionSpace.orientation.w = 1.0f;
        CheckXr(xrCreateActionSpace(session_, &actionSpaceInfo, &aimSpace_),
            "xrCreateActionSpace(right aim)");
    }

    void CreateProjectionSwapchain() {
        std::uint32_t viewCount = 0;
        CheckXr(xrEnumerateViewConfigurationViews(
            instance_, systemId_, kViewConfiguration,
            0, &viewCount, nullptr),
            "xrEnumerateViewConfigurationViews(count)");
        if (viewCount != 2) {
            throw std::runtime_error(
                "PRIMARY_STEREO did not report exactly two views");
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
            const int recommendedWidth =
                static_cast<int>(view.recommendedImageRectWidth);
            const int recommendedHeight =
                static_cast<int>(view.recommendedImageRectHeight);
            const int maxWidth = static_cast<int>(view.maxImageRectWidth);
            const int maxHeight = static_cast<int>(view.maxImageRectHeight);

            const int scaledWidth = std::min(
                std::min(
                    static_cast<int>(std::lround(
                        recommendedWidth * kProjectionResolutionScale)),
                    maxWidth),
                kProjectionDimensionCap);
            const int scaledHeight = std::min(
                std::min(
                    static_cast<int>(std::lround(
                        recommendedHeight * kProjectionResolutionScale)),
                    maxHeight),
                kProjectionDimensionCap);

            width = std::max(width, scaledWidth);
            height = std::max(height, scaledHeight);
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

        Log("Projection swapchain HQ=" + std::to_string(width) + "x" +
            std::to_string(height) + " arraySize=2 scale=" +
            std::to_string(kProjectionResolutionScale));
    }

    void PollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance_, &event) == XR_SUCCESS) {
            switch (event.type) {
                case XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED: {
                    const auto& changed =
                        *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                    sessionState_ = changed.state;
                    Log(std::string("sessionState=") +
                        SessionStateName(sessionState_));

                    if (sessionState_ == XR_SESSION_STATE_READY &&
                        !sessionRunning_) {
                        XrSessionBeginInfo beginInfo{XR_TYPE_SESSION_BEGIN_INFO};
                        beginInfo.primaryViewConfigurationType = kViewConfiguration;
                        CheckXr(xrBeginSession(session_, &beginInfo),
                            "xrBeginSession");
                        sessionRunning_ = true;
                        Log("xrBeginSession success");
                    } else if (sessionState_ == XR_SESSION_STATE_STOPPING &&
                               sessionRunning_) {
                        CheckXr(xrEndSession(session_), "xrEndSession");
                        sessionRunning_ = false;
                        triggerDown_ = false;
                        inputWriter_.Publish(false, 0.0f, 0.0f, false);
                    } else if (
                        sessionState_ == XR_SESSION_STATE_EXITING ||
                        sessionState_ == XR_SESSION_STATE_LOSS_PENDING) {
                        exitRequested_ = true;
                    }
                    break;
                }
                case XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING:
                    exitRequested_ = true;
                    break;
                default:
                    break;
            }

            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
    }

    PanelRect MakeBaseRect() const {
        const int width = std::max(1, baseTexture_.Width());
        const int height = std::max(1, baseTexture_.Height());
        const float screenHeight =
            kScreenWidthMeters * static_cast<float>(height) /
            static_cast<float>(width);
        return {
            -kScreenWidthMeters * 0.5f,
             kScreenWidthMeters * 0.5f,
             screenHeight * 0.5f,
            -screenHeight * 0.5f
        };
    }

    bool MakeStereoRect(const PanelRect& base, PanelRect& stereo) const {
        if (!stereoFrame_.active ||
            stereoFrame_.clientWidth < 2 || stereoFrame_.clientHeight < 2 ||
            stereoFrame_.panelWidth < 2 || stereoFrame_.panelHeight < 2) {
            return false;
        }

        const float clientWidth = static_cast<float>(stereoFrame_.clientWidth);
        const float clientHeight = static_cast<float>(stereoFrame_.clientHeight);
        const float leftN = std::clamp(
            stereoFrame_.panelLeft / clientWidth, 0.0f, 1.0f);
        const float rightN = std::clamp(
            (stereoFrame_.panelLeft + stereoFrame_.panelWidth) / clientWidth,
            0.0f, 1.0f);
        const float topN = std::clamp(
            stereoFrame_.panelTop / clientHeight, 0.0f, 1.0f);
        const float bottomN = std::clamp(
            (stereoFrame_.panelTop + stereoFrame_.panelHeight) / clientHeight,
            0.0f, 1.0f);

        if (rightN <= leftN || bottomN <= topN) return false;

        const float baseWidth = base.right - base.left;
        const float baseHeight = base.top - base.bottom;
        const float distanceScale =
            kStereoDistanceMeters / kScreenDistanceMeters;

        const float aLeft = base.left + baseWidth * leftN;
        const float aRight = base.left + baseWidth * rightN;
        const float aTop = base.top - baseHeight * topN;
        const float aBottom = base.top - baseHeight * bottomN;

        stereo = {
            aLeft * distanceScale,
            aRight * distanceScale,
            aTop * distanceScale,
            aBottom * distanceScale
        };
        return true;
    }

    bool UpdatePointer(
        XrTime displayTime,
        const PanelRect& baseRect,
        float& cursorX,
        float& cursorY) {

        if (sessionState_ != XR_SESSION_STATE_FOCUSED) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        XrActiveActionSet activeActionSet{};
        activeActionSet.actionSet = actionSet_;
        activeActionSet.subactionPath = XR_NULL_PATH;

        XrActionsSyncInfo syncInfo{XR_TYPE_ACTIONS_SYNC_INFO};
        syncInfo.countActiveActionSets = 1;
        syncInfo.activeActionSets = &activeActionSet;
        const XrResult syncResult = xrSyncActions(session_, &syncInfo);
        if (XR_FAILED(syncResult)) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        XrActionStateGetInfo poseGet{XR_TYPE_ACTION_STATE_GET_INFO};
        poseGet.action = aimAction_;
        poseGet.subactionPath = rightHandPath_;
        XrActionStatePose poseState{XR_TYPE_ACTION_STATE_POSE};
        CheckXr(xrGetActionStatePose(session_, &poseGet, &poseState),
            "xrGetActionStatePose");

        XrActionStateGetInfo triggerGet{XR_TYPE_ACTION_STATE_GET_INFO};
        triggerGet.action = triggerAction_;
        triggerGet.subactionPath = rightHandPath_;
        XrActionStateFloat triggerState{XR_TYPE_ACTION_STATE_FLOAT};
        CheckXr(xrGetActionStateFloat(session_, &triggerGet, &triggerState),
            "xrGetActionStateFloat");

        if (!poseState.isActive) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        XrSpaceLocation location{XR_TYPE_SPACE_LOCATION};
        const XrResult locateResult = xrLocateSpace(
            aimSpace_, localSpace_, displayTime, &location);
        if (XR_FAILED(locateResult)) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        constexpr XrSpaceLocationFlags required =
            XR_SPACE_LOCATION_POSITION_VALID_BIT |
            XR_SPACE_LOCATION_ORIENTATION_VALID_BIT;
        if ((location.locationFlags & required) != required) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        const Vec3 origin{
            location.pose.position.x,
            location.pose.position.y,
            location.pose.position.z};
        const Vec3 direction = RotateByQuaternion(
            location.pose.orientation,
            Vec3{0.0f, 0.0f, -1.0f});

        if (std::abs(direction.z) < 0.0001f) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        const float t =
            (-kScreenDistanceMeters - origin.z) / direction.z;
        if (t <= 0.0f) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        const Vec3 hit = Add(origin, Scale(direction, t));
        const float width = baseRect.right - baseRect.left;
        const float height = baseRect.top - baseRect.bottom;
        const float u = (hit.x - baseRect.left) / width;
        const float v = (baseRect.top - hit.y) / height;
        const bool valid =
            u >= 0.0f && u <= 1.0f &&
            v >= 0.0f && v <= 1.0f;

        if (!valid) {
            triggerDown_ = false;
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
            return false;
        }

        if (triggerState.isActive) {
            if (!triggerDown_ && triggerState.currentState >= 0.65f) {
                triggerDown_ = true;
            } else if (triggerDown_ && triggerState.currentState <= 0.45f) {
                triggerDown_ = false;
            }
        } else {
            triggerDown_ = false;
        }

        inputWriter_.Publish(true, u, v, triggerDown_);

        const float cursorScale =
            kCursorDistanceMeters / kScreenDistanceMeters;
        cursorX = hit.x * cursorScale;
        cursorY = hit.y * cursorScale;
        return true;
    }

    void RefreshSources() {
        GpuFrameInfo gpuUpdate{};
        if (gpuFrameReader_.ReadIfChanged(gpuSequence_, gpuUpdate)) {
            gpuSequence_ = gpuUpdate.sequence;
            gpuFrame_ = gpuUpdate;
            if (!gpuFrame_.active) baseTexture_.Reset();
        }

        if (gpuFrame_.active && gpuFrame_.sharedHandle) {
            try {
                baseTexture_.Update(
                    device_.Get(),
                    context_.Get(),
                    gpuFrame_.sequence,
                    gpuFrame_.active,
                    gpuFrame_.sharedHandle,
                    gpuFrame_.width,
                    gpuFrame_.height,
                    gpuFrame_.format);
            } catch (const std::exception& ex) {
                Log(std::string("A GPU cache error: ") + ex.what());
            }
        }

        StereoGpuFrameInfo stereoUpdate{};
        if (stereoFrameReader_.ReadIfChanged(stereoSequence_, stereoUpdate)) {
            stereoSequence_ = stereoUpdate.sequence;
            stereoFrame_ = stereoUpdate;
            if (!stereoFrame_.active) stereoTexture_.Reset();
        }

        if (stereoFrame_.active && stereoFrame_.sharedHandle &&
            stereoFrame_.eyeWidth > 1 && stereoFrame_.eyeHeight > 1) {
            try {
                stereoTexture_.Update(
                    device_.Get(),
                    context_.Get(),
                    stereoFrame_.sequence,
                    stereoFrame_.active,
                    stereoFrame_.sharedHandle,
                    stereoFrame_.eyeWidth * 2,
                    stereoFrame_.eyeHeight,
                    stereoFrame_.format);
            } catch (const std::exception& ex) {
                Log(std::string("B GPU cache error: ") + ex.what());
            }
        }
    }

    void RenderFrame() {
        XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
        XrFrameState frameState{XR_TYPE_FRAME_STATE};
        CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");

        XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
        CheckXr(xrBeginFrame(session_, &beginInfo), "xrBeginFrame");

        RefreshSources();

        std::array<XrCompositionLayerProjectionView, 2> projectionViews{{
            {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}
        }};
        XrCompositionLayerProjection projectionLayer{
            XR_TYPE_COMPOSITION_LAYER_PROJECTION};
        std::array<const XrCompositionLayerBaseHeader*, 1> layers{};
        std::uint32_t layerCount = 0;

        if (frameState.shouldRender && baseTexture_.Valid()) {
            XrViewLocateInfo locateInfo{XR_TYPE_VIEW_LOCATE_INFO};
            locateInfo.viewConfigurationType = kViewConfiguration;
            locateInfo.displayTime = frameState.predictedDisplayTime;
            locateInfo.space = localSpace_;

            XrViewState viewState{XR_TYPE_VIEW_STATE};
            std::uint32_t viewCount = 0;
            for (auto& view : views_) view = {XR_TYPE_VIEW};
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

                const PanelRect baseRect = MakeBaseRect();
                PanelRect stereoRect{};
                const bool stereoValid =
                    stereoTexture_.Valid() && MakeStereoRect(baseRect, stereoRect);

                float cursorX = 0.0f;
                float cursorY = 0.0f;
                const bool cursorValid = UpdatePointer(
                    frameState.predictedDisplayTime,
                    baseRect,
                    cursorX,
                    cursorY);

                const std::uint32_t imageIndex = projectionSwapchain_.Acquire();
                ID3D11Texture2D* target =
                    projectionSwapchain_.Texture(imageIndex);

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
                        stereoValid ? stereoTexture_.Srv() : nullptr,
                        stereoValid ? &stereoRect : nullptr,
                        eye == 1,
                        cursorValid,
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
            } else {
                inputWriter_.Publish(false, 0.0f, 0.0f, false);
            }
        } else {
            inputWriter_.Publish(false, 0.0f, 0.0f, false);
        }

        XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
        endInfo.displayTime = frameState.predictedDisplayTime;
        endInfo.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
        endInfo.layerCount = layerCount;
        endInfo.layers = layerCount ? layers.data() : nullptr;
        CheckXr(xrEndFrame(session_, &endInfo), "xrEndFrame");
    }

    void Shutdown() noexcept {
        inputWriter_.Publish(false, 0.0f, 0.0f, false);

        try {
            projectionSwapchain_.Reset();
        } catch (...) {
        }

        baseTexture_.Reset();
        stereoTexture_.Reset();

        if (aimSpace_ != XR_NULL_HANDLE) {
            xrDestroySpace(aimSpace_);
            aimSpace_ = XR_NULL_HANDLE;
        }
        if (actionSet_ != XR_NULL_HANDLE) {
            xrDestroyActionSet(actionSet_);
            actionSet_ = XR_NULL_HANDLE;
            aimAction_ = XR_NULL_HANDLE;
            triggerAction_ = XR_NULL_HANDLE;
        }
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
    const DWORD hostPid = ParsePid(argc, argv);
    if (hostPid == 0) {
        MessageBoxW(
            nullptr,
            L"GeoGebraForQuestPC.XR.exe --pid <host process id> ile başlatılmalıdır.",
            L"GeoGebraForQuest PC v0.13",
            MB_OK | MB_ICONERROR);
        return 2;
    }

    try {
        Log("GeoGebraForQuest PC v0.13 XR starting, host pid=" +
            std::to_string(hostPid));
        OpenXrApp app(hostPid);
        app.Initialize();
        return app.Run();
    } catch (const std::exception& ex) {
        Log(std::string("Fatal: ") + ex.what());
        return 1;
    } catch (...) {
        Log("Fatal: unknown exception");
        return 1;
    }
}
