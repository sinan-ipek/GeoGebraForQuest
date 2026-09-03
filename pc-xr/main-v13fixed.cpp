// GeoGebraForQuest PC v0.13 — fixed XR surface / native-quality target
//
// Keep the proven v0.12 OpenXR loop, but decouple render quality from the
// physical panel geometry. OpenXR's recommended eye target is supersampled
// modestly and clamped to the Quest 3 useful physical raster/runtime maximum.

#include "v11-render.hpp"

namespace {

constexpr float kRenderQualityScale = 1.25f;
constexpr std::uint32_t kQuest3PhysicalEyeWidth = 2064;
constexpr std::uint32_t kQuest3PhysicalEyeHeight = 2208;

XrResult GgqEnumerateV13Views(
    XrInstance instance,
    XrSystemId systemId,
    XrViewConfigurationType viewConfigurationType,
    std::uint32_t viewCapacityInput,
    std::uint32_t* viewCountOutput,
    XrViewConfigurationView* views) {

    const XrResult result = ::xrEnumerateViewConfigurationViews(
        instance, systemId, viewConfigurationType,
        viewCapacityInput, viewCountOutput, views);

    if (XR_FAILED(result) || viewCapacityInput == 0 || !views || !viewCountOutput)
        return result;

    const std::uint32_t count = std::min(viewCapacityInput, *viewCountOutput);
    for (std::uint32_t i = 0; i < count; ++i) {
        auto& view = views[i];
        const auto recW = std::max<std::uint32_t>(1, view.recommendedImageRectWidth);
        const auto recH = std::max<std::uint32_t>(1, view.recommendedImageRectHeight);
        const auto maxW = std::max<std::uint32_t>(1, view.maxImageRectWidth);
        const auto maxH = std::max<std::uint32_t>(1, view.maxImageRectHeight);
        const auto targetW = static_cast<std::uint32_t>(std::lround(recW * kRenderQualityScale));
        const auto targetH = static_cast<std::uint32_t>(std::lround(recH * kRenderQualityScale));
        view.recommendedImageRectWidth = std::min({targetW, kQuest3PhysicalEyeWidth, maxW});
        view.recommendedImageRectHeight = std::min({targetH, kQuest3PhysicalEyeHeight, maxH});
    }

    ggqv11::Log("v0.13 eye target = OpenXR recommended x1.25, clamped to Quest3 physical/runtime max");
    return result;
}

} // namespace

#define xrEnumerateViewConfigurationViews GgqEnumerateV13Views
#include "main-v11.cpp"
#undef xrEnumerateViewConfigurationViews
