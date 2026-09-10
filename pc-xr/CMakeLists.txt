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

function(ggq_configure_xr_target target_name)
  target_compile_definitions(${target_name} PRIVATE
    XR_USE_PLATFORM_WIN32
    XR_USE_GRAPHICS_API_D3D11
    UNICODE
    _UNICODE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
  )

  target_link_libraries(${target_name} PRIVATE
    openxr_loader
    d3d11
    d3dcompiler
    dxgi
    user32
  )

  if(MSVC)
    target_compile_options(${target_name} PRIVATE /W4 /EHsc /permissive-)
  endif()
endfunction()

# Production XR companion retained unchanged from the v0.13.35 working-depth baseline.
add_executable(GeoGebraForQuestPC.XR
  main-v123.cpp
  main-v11.cpp
  v11-shared.hpp
  v11-render.hpp
  v123-mouse.hpp
)

# main-v11.cpp is included by main-v123.cpp so the proven implementation is not
# compiled as a second translation unit.
set_source_files_properties(main-v11.cpp PROPERTIES HEADER_FILE_ONLY TRUE)

ggq_configure_xr_target(GeoGebraForQuestPC.XR)

# v0.14.0 diagnostic executable. This deliberately excludes GeoGebra, CEF,
# JavaScript stereo capture, pixel MMF transport, and host-process IPC. Synthetic
# textures are uploaded once during startup and then remain in VRAM. Every frame
# therefore measures only our native D3D11 renderer + OpenXR + Meta Link path.
add_executable(GeoGebraForQuestPC.XR.PerfTest
  perf-test.cpp
  v11-shared.hpp
  v11-render.hpp
  v123-mouse.hpp
)

ggq_configure_xr_target(GeoGebraForQuestPC.XR.PerfTest)

install(TARGETS
  GeoGebraForQuestPC.XR
  GeoGebraForQuestPC.XR.PerfTest
  RUNTIME DESTINATION .
)
