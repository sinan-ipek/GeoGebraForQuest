#pragma once

#include <d3d11.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <windows.h>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace ggqv1312 {

using Microsoft::WRL::ComPtr;

inline void CheckHr1312(HRESULT hr, const char* what) {
    if (FAILED(hr)) {
        throw std::runtime_error(std::string(what) + " failed hr=0x" +
            [] (HRESULT v) {
                char b[16]{};
                sprintf_s(b, "%08X", static_cast<unsigned>(v));
                return std::string(b);
            }(hr));
    }
}

inline std::filesystem::path ExeDir1312() {
    std::wstring path(32768, L'\0');
    const DWORD n = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (n == 0 || n >= path.size()) return std::filesystem::current_path();
    path.resize(n);
    return std::filesystem::path(path).parent_path();
}

class SplashTexture {
public:
    void Load(ID3D11Device* device, const std::filesystem::path& path) {
        Reset();
        if (!device || !std::filesystem::exists(path)) return;

        ComPtr<IWICImagingFactory> factory;
        CheckHr1312(CoCreateInstance(
            CLSID_WICImagingFactory,
            nullptr,
            CLSCTX_INPROC_SERVER,
            IID_PPV_ARGS(&factory)),
            "CoCreateInstance(WIC)");

        ComPtr<IWICBitmapDecoder> decoder;
        CheckHr1312(factory->CreateDecoderFromFilename(
            path.c_str(), nullptr, GENERIC_READ,
            WICDecodeMetadataCacheOnLoad, &decoder),
            "CreateDecoderFromFilename");

        ComPtr<IWICBitmapFrameDecode> frame;
        CheckHr1312(decoder->GetFrame(0, &frame), "GetFrame");

        UINT w = 0, h = 0;
        CheckHr1312(frame->GetSize(&w, &h), "GetSize");
        if (w == 0 || h == 0) return;

        ComPtr<IWICFormatConverter> converter;
        CheckHr1312(factory->CreateFormatConverter(&converter), "CreateFormatConverter");
        CheckHr1312(converter->Initialize(
            frame.Get(), GUID_WICPixelFormat32bppBGRA,
            WICBitmapDitherTypeNone, nullptr, 0.0,
            WICBitmapPaletteTypeCustom),
            "FormatConverter::Initialize");

        const UINT stride = w * 4;
        std::vector<std::uint8_t> pixels(static_cast<size_t>(stride) * h);
        CheckHr1312(converter->CopyPixels(
            nullptr, stride, static_cast<UINT>(pixels.size()), pixels.data()),
            "CopyPixels");

        D3D11_TEXTURE2D_DESC td{};
        td.Width = w;
        td.Height = h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_IMMUTABLE;
        td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

        D3D11_SUBRESOURCE_DATA init{};
        init.pSysMem = pixels.data();
        init.SysMemPitch = stride;

        CheckHr1312(device->CreateTexture2D(&td, &init, &texture_), "CreateTexture2D(splash)");
        CheckHr1312(device->CreateShaderResourceView(texture_.Get(), nullptr, &srv_),
                    "CreateShaderResourceView(splash)");
        width_ = static_cast<int>(w);
        height_ = static_cast<int>(h);
    }

    void Reset() noexcept {
        srv_.Reset();
        texture_.Reset();
        width_ = 0;
        height_ = 0;
    }

    bool Valid() const noexcept { return srv_ && width_ > 0 && height_ > 0; }
    ID3D11ShaderResourceView* Srv() const noexcept { return srv_.Get(); }
    int Width() const noexcept { return width_; }
    int Height() const noexcept { return height_; }

private:
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    int width_{};
    int height_{};
};

} // namespace ggqv1312
