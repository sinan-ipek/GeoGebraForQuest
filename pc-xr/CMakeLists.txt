cmake_minimum_required(VERSION 3.24)
project(GeoGebraForQuestPCXR LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_API_LAYERS OFF CACHE BOOL "" FORCE)
set(BUILD_CONFORMANCE_TESTS OFF CACHE BOOL "" FORCE)
set(DYNAMIC_LOADER OFF CACHE BOOL "" FORCE)

# OpenXR SDK 1.1.62, 2026-07-31. Pin the exact SDK commit so PC builds are reproducible.
FetchContent_Declare(
  openxr_sdk
  URL https://github.com/KhronosGroup/OpenXR-SDK/archive/57af7fc61f9f2d492580cb28aab6d0ea59d8d417.zip
)
FetchContent_MakeAvailable(openxr_sdk)

# v0.13: no screen capture and no JPEG/base64 stereo transport.
# A: CEF accelerated D3D11 surface -> app-owned shared GPU texture -> XR GPU cache.
# B: Exp46 L/R -> temporary CEF GPU compositor phase -> cropped D3D11 SBS texture
#    -> app-owned shared GPU texture -> XR GPU cache.
# Both copies remain on the GPU; the CPU never carries image pixels.
add_executable(GeoGebraForQuestPC.XR
  main-v13.cpp
  v11-shared.hpp
  v11-render.hpp
  v13-gpu-stereo.hpp
)

target_compile_definitions(GeoGebraForQuestPC.XR PRIVATE
  XR_USE_PLATFORM_WIN32
  XR_USE_GRAPHICS_API_D3D11
  UNICODE
  _UNICODE
  NOMINMAX
  WIN32_LEAN_AND_MEAN
)

target_link_libraries(GeoGebraForQuestPC.XR PRIVATE
  openxr_loader
  d3d11
  d3dcompiler
  dxgi
  user32
)

if(MSVC)
  target_compile_options(GeoGebraForQuestPC.XR PRIVATE /W4 /EHsc /permissive-)
endif()

install(TARGETS GeoGebraForQuestPC.XR RUNTIME DESTINATION .)
