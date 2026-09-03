// GeoGebraForQuest PC v0.12.4 — balanced Quest quality
//
// Keep the proven v0.12.3 XR-behind-native presentation path, but stop forcing
// every eye to the Quest 3 physical panel raster.  The OpenXR runtime's
// recommended size is the correct starting point for distortion/pre-warp; we
// apply a modest quality headroom and clamp to both Quest 3 physical pixels and
// the runtime maxImageRect limits.

#include "v11-render.hpp"

namespace {

constexpr float kRenderQualityScale = 1.12f;
constexpr std::uint32_t kQuest3PhysicalEyeWidth = 2064;
constexpr std::uint32_t kQuest3PhysicalEyeHeight = 2208;

XrResult GgqEnumerateBalancedViewConfigurationViews(
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

    if (XR_FAILED(result) || viewCapacityInput == 0 || views == nullptr ||
        viewCountOutput == nullptr) {
        return result;
    }

    const std::uint32_t count = std::min(viewCapacityInput, *viewCountOutput);
    for (std::uint32_t i = 0; i < count; ++i) {
        auto& view = views[i];
        const auto runtimeRecommendedWidth =
            std::max<std::uint32_t>(1, view.recommendedImageRectWidth);
        const auto runtimeRecommendedHeight =
            std::max<std::uint32_t>(1, view.recommendedImageRectHeight);
        const auto runtimeMaxWidth =
            std::max<std::uint32_t>(1, view.maxImageRectWidth);
        const auto runtimeMaxHeight =
            std::max<std::uint32_t>(1, view.maxImageRectHeight);

        const auto qualityWidth = static_cast<std::uint32_t>(
            std::lround(runtimeRecommendedWidth * kRenderQualityScale));
        const auto qualityHeight = static_cast<std::uint32_t>(
            std::lround(runtimeRecommendedHeight * kRenderQualityScale));

        view.recommendedImageRectWidth = std::min(
            {qualityWidth, kQuest3PhysicalEyeWidth, runtimeMaxWidth});
        view.recommendedImageRectHeight = std::min(
            {qualityHeight, kQuest3PhysicalEyeHeight, runtimeMaxHeight});
    }

    ggqv11::Log(
        "v0.12.4 render target: OpenXR recommended x1.12, clamped to Quest3 physical/max");
    return result;
}

} // namespace

#define xrEnumerateViewConfigurationViews GgqEnumerateBalancedViewConfigurationViews
#include "main-v11.cpp"
#undef xrEnumerateViewConfigurationViews
