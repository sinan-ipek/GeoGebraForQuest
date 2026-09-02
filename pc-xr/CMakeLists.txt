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

# v0.8 isolates B-panel composition from the real SBS texture path.
# The OpenXR projection contains the captured normal GeoGebra window as A.
# B is a solid diagnostic rectangle: magenta in both eyes, then red in the
# left eye and blue in the right eye. A small top-left square is green when
# the existing shared-memory header contains usable 3D-panel geometry and
# orange when v0.8 is using its fixed fallback rectangle.
add_executable(GeoGebraForQuestPC.XR main-v08.cpp)

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
  gdi32
)

if(MSVC)
  target_compile_options(GeoGebraForQuestPC.XR PRIVATE /W4 /EHsc /permissive-)
endif()

install(TARGETS GeoGebraForQuestPC.XR RUNTIME DESTINATION .)
