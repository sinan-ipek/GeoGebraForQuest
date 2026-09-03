// GeoGebraForQuest PC v0.12.1 quality-safe wrapper.
// Keep the proven v0.12 renderer/input/stereo code byte-for-byte, but ask OpenXR
// for a 25% larger per-eye projection surface. This changes only the final XR
// raster resolution; panel geometry, controller mapping and SBS stereo transport
// remain the v0.12 implementation.

// Parse OpenXR/D3D declarations before introducing the field-name macro below.
// main-v11.cpp includes v11-render.hpp again, but #pragma once makes that a no-op.
#include "v11-render.hpp"

#define recommendedImageRectWidth recommendedImageRectWidth * 5 / 4
#define recommendedImageRectHeight recommendedImageRectHeight * 5 / 4
#include "main-v11.cpp"
