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

# v0.12.1 is deliberately based on the known-working v0.12 renderer.
# A: CEF OnAcceleratedPaint D3D11 texture -> application-owned shared D3D11 texture
#    -> GPU-to-GPU OpenXR texture. No Windows screen capture.
# B: proven Exp46 [L|R] stereo path from v0.12.
# Input/file handling/panel geometry: unchanged v0.12 behavior.
# Only final OpenXR per-eye projection raster is increased by main-v121.cpp.
add_executable(GeoGebraForQuestPC.XR
  main-v121.cpp
  main-v11.cpp
  v11-shared.hpp
  v11-render.hpp
)

# main-v11.cpp is included by main-v121.cpp; do not compile it as a second translation unit.
set_source_files_properties(main-v11.cpp PROPERTIES HEADER_FILE_ONLY TRUE)

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
