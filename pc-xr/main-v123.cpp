// GeoGebraForQuest PC v0.12.3 XR-Behind Native
//
// Keep the proven v0.12 OpenXR session/input/frame loop intact, but make the
// per-eye render target Quest-3-specific. Meta lists Quest 3's physical display
// resolution as 2064x2208 per eye. We use that as the maximum useful raster
// target and still respect the active OpenXR runtime's maxImageRect limits.
//
// The wrapper is defined before the macro so it calls the real loader function.
// The macro then affects only calls made by the included proven main-v11.cpp.

#include "v11-render.hpp"

namespace {

constexpr std::uint32_t kQuest3PhysicalEyeWidth = 2064;
constexpr std::uint32_t kQuest3PhysicalEyeHeight = 2208;

XrResult GgqEnumerateQuest3ViewConfigurationViews(
    XrInstance instance,
    XrSystemId systemId,
    XrViewConfigurationType viewConfigurationType,
    std::uint32_t viewCapacityInput,
    std::uint32_t* viewCountOutput,
    XrViewConfigurationView* views) {

    const XrResult result = ::xrEnumerateViewConfigurationViews(
        instance,
        systemId,
        viewConfigurationType,
        viewCapacityInput,
        viewCountOutput,
        views);

    if (XR_FAILED(result) ||
        viewCapacityInput == 0 ||
        views == nullptr ||
        viewCountOutput == nullptr) {
        return result;
    }

    const std::uint32_t count = std::min(viewCapacityInput, *viewCountOutput);
    for (std::uint32_t i = 0; i < count; ++i) {
        auto& view = views[i];
        const std::uint32_t maxWidth =
            std::max<std::uint32_t>(1, view.maxImageRectWidth);
        const std::uint32_t maxHeight =
            std::max<std::uint32_t>(1, view.maxImageRectHeight);

        view.recommendedImageRectWidth =
            std::min(kQuest3PhysicalEyeWidth, maxWidth);
        view.recommendedImageRectHeight =
            std::min(kQuest3PhysicalEyeHeight, maxHeight);
    }

    ggqv11::Log(
        "v0.12.3 Quest target: physical 2064x2208 per eye, clamped to OpenXR maxImageRect");
    return result;
}

} // namespace

#define xrEnumerateViewConfigurationViews GgqEnumerateQuest3ViewConfigurationViews
#include "main-v11.cpp"
#undef xrEnumerateViewConfigurationViews
