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

# v0.4 keeps the normal GeoGebra PC window as the common base quad. A single
# hidden SBS texture [L|R] is overlaid only at GeoGebra's real 3D Graphics rect.
# The left OpenXR eye samples the left half; the right eye samples the right half.
add_executable(GeoGebraForQuestPC.XR main-v04.cpp)

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
  dxgi
  user32
  gdi32
  dwmapi
)

if(MSVC)
  target_compile_options(GeoGebraForQuestPC.XR PRIVATE /W4 /EHsc /permissive-)
endif()

install(TARGETS GeoGebraForQuestPC.XR RUNTIME DESTINATION .)
