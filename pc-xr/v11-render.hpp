#pragma once
#include "v11-shared.hpp"

namespace ggqv11 {

class ProjectionSwapchain {
public:
    ~ProjectionSwapchain() { Reset(); }

    void Reset() {
        images_.clear();
        if (handle_ != XR_NULL_HANDLE) {
            xrDestroySwapchain(handle_);
            handle_ = XR_NULL_HANDLE;
        }
        width_ = 0;
        height_ = 0;
    }

    void Create(XrSession session, std::int64_t format, int width, int height) {
        Reset();
        XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
        info.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
        info.format = format;
        info.sampleCount = 1;
        info.width = static_cast<std::uint32_t>(width);
        info.height = static_cast<std::uint32_t>(height);
        info.faceCount = 1;
        info.arraySize = 2;
        info.mipCount = 1;
        CheckXr(xrCreateSwapchain(session, &info, &handle_), "xrCreateSwapchain");

        std::uint32_t count = 0;
        CheckXr(xrEnumerateSwapchainImages(handle_, 0, &count, nullptr),
            "xrEnumerateSwapchainImages(count)");
        images_.resize(count);
        for (auto& image : images_) {
            image = {XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR};
        }
        CheckXr(xrEnumerateSwapchainImages(
            handle_, count, &count,
            reinterpret_cast<XrSwapchainImageBaseHeader*>(images_.data())),
            "xrEnumerateSwapchainImages(images)");
        width_ = width;
        height_ = height;
    }

    std::uint32_t Acquire() {
        std::uint32_t index = 0;
        XrSwapchainImageAcquireInfo acquire{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
        CheckXr(xrAcquireSwapchainImage(handle_, &acquire, &index), "xrAcquireSwapchainImage");
        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(xrWaitSwapchainImage(handle_, &wait), "xrWaitSwapchainImage");
        return index;
    }

    void Release() {
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(xrReleaseSwapchainImage(handle_, &release), "xrReleaseSwapchainImage");
    }

    ID3D11Texture2D* Texture(std::uint32_t index) const { return images_.at(index).texture; }
    XrSwapchain Handle() const { return handle_; }
    int Width() const { return width_; }
    int Height() const { return height_; }

private:
    XrSwapchain handle_{XR_NULL_HANDLE};
    std::vector<XrSwapchainImageD3D11KHR> images_;
    int width_{};
    int height_{};
};

struct Vec3 {
    float x{};
    float y{};
    float z{};
};

Vec3 Add(const Vec3& a, const Vec3& b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

Vec3 Subtract(const Vec3& a, const Vec3& b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

Vec3 Scale(const Vec3& v, float s) {
    return {v.x * s, v.y * s, v.z * s};
}

Vec3 Cross(const Vec3& a, const Vec3& b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x};
}

Vec3 RotateByQuaternion(const XrQuaternionf& q, const Vec3& v) {
    const Vec3 qv{q.x, q.y, q.z};
    const Vec3 t = Scale(Cross(qv, v), 2.0f);
    return Add(v, Add(Scale(t, q.w), Cross(qv, t)));
}

Vec3 WorldToView(const XrPosef& eyePose, const Vec3& world) {
    const Vec3 translated{
        world.x - eyePose.position.x,
        world.y - eyePose.position.y,
        world.z - eyePose.position.z};
    const XrQuaternionf inverse{
        -eyePose.orientation.x,
        -eyePose.orientation.y,
        -eyePose.orientation.z,
        eyePose.orientation.w};
    return RotateByQuaternion(inverse, translated);
}

struct Vertex {
    float x, y, z, w;
    float u, v;
};

Vertex ProjectVertex(const XrView& view, const Vec3& world, float u, float v) {
    const Vec3 p = WorldToView(view.pose, world);
    const float depth = std::max(kNearDepthMeters, -p.z);

    const float tanLeft = std::tan(view.fov.angleLeft);
    const float tanRight = std::tan(view.fov.angleRight);
    const float tanDown = std::tan(view.fov.angleDown);
    const float tanUp = std::tan(view.fov.angleUp);
    const float horizontal = std::max(0.001f, tanRight - tanLeft);
    const float vertical = std::max(0.001f, tanUp - tanDown);

    const float clipX =
        (2.0f * p.x / horizontal) -
        (depth * (tanRight + tanLeft) / horizontal);
    const float clipY =
        (2.0f * p.y / vertical) -
        (depth * (tanUp + tanDown) / vertical);

    return {clipX, clipY, depth * 0.5f, depth, u, v};
}

struct PanelRect {
    float left{};
    float right{};
    float top{};
    float bottom{};
};

class ProjectionRenderer {
public:
    void Initialize(ID3D11Device* device) {
        static const char* shaderSource = R"(
Texture2D tex0 : register(t0);
SamplerState samp0 : register(s0);
struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD0; };
struct VSOut { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
VSOut VSMain(VSIn i) { VSOut o; o.pos=i.pos; o.uv=i.uv; return o; }
float4 PSMain(VSOut i) : SV_TARGET { return tex0.Sample(samp0, i.uv); }
)";

        ComPtr<ID3DBlob> vsBlob;
        ComPtr<ID3DBlob> psBlob;
        ComPtr<ID3DBlob> errors;
        HRESULT hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-v0.11",
            nullptr, nullptr, "VSMain", "vs_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0,
            &vsBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(static_cast<const char*>(errors->GetBufferPointer()), errors->GetBufferSize())
                : "vertex shader compile error";
            throw std::runtime_error(detail);
        }
        errors.Reset();
        hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-v0.11",
            nullptr, nullptr, "PSMain", "ps_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0,
            &psBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(static_cast<const char*>(errors->GetBufferPointer()), errors->GetBufferSize())
                : "pixel shader compile error";
            throw std::runtime_error(detail);
        }

        CheckHr(device->CreateVertexShader(
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &vertexShader_),
            "CreateVertexShader");
        CheckHr(device->CreatePixelShader(
            psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &pixelShader_),
            "CreatePixelShader");

        const D3D11_INPUT_ELEMENT_DESC elements[] = {
            {"POSITION", 0, DXGI_FORMAT_R32G32B32A32_FLOAT, 0, 0,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
            {"TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT, 0, 16,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
        };
        CheckHr(device->CreateInputLayout(
            elements, static_cast<UINT>(std::size(elements)),
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), &inputLayout_),
            "CreateInputLayout");

        D3D11_BUFFER_DESC vb{};
        vb.ByteWidth = sizeof(Vertex) * 6;
        vb.Usage = D3D11_USAGE_DYNAMIC;
        vb.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        CheckHr(device->CreateBuffer(&vb, nullptr, &vertexBuffer_), "CreateBuffer(vertex)");

        D3D11_SAMPLER_DESC sampler{};
        sampler.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sampler.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.MinLOD = 0.0f;
        sampler.MaxLOD = D3D11_FLOAT32_MAX;
        CheckHr(device->CreateSamplerState(&sampler, &sampler_), "CreateSamplerState");

        D3D11_RASTERIZER_DESC raster{};
        raster.FillMode = D3D11_FILL_SOLID;
        raster.CullMode = D3D11_CULL_NONE;
        raster.DepthClipEnable = TRUE;
        CheckHr(device->CreateRasterizerState(&raster, &rasterizer_), "CreateRasterizerState");

    }

    void InitializeCursor(ID3D11Device* device, ID3D11DeviceContext* context) {
        const std::uint32_t cursorPixel = 0xFF00FFFFu;
        cursorTexture_.Upload(
            device, context,
            reinterpret_cast<const std::uint8_t*>(&cursorPixel), 1, 1, 4);
    }

    void RenderEye(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        ID3D11Texture2D* target,
        DXGI_FORMAT targetFormat,
        UINT arraySlice,
        int targetWidth,
        int targetHeight,
        const XrView& view,
        ID3D11ShaderResourceView* baseSrv,
        const PanelRect& baseRect,
        ID3D11ShaderResourceView* sbsSrv,
        const PanelRect* stereoRect,
        bool rightEye,
        bool cursorValid,
        float cursorX,
        float cursorY) {

        D3D11_RENDER_TARGET_VIEW_DESC rtvDesc{};
        rtvDesc.Format = targetFormat;
        rtvDesc.ViewDimension = D3D11_RTV_DIMENSION_TEXTURE2DARRAY;
        rtvDesc.Texture2DArray.MipSlice = 0;
        rtvDesc.Texture2DArray.FirstArraySlice = arraySlice;
        rtvDesc.Texture2DArray.ArraySize = 1;
        ComPtr<ID3D11RenderTargetView> rtv;
        CheckHr(device->CreateRenderTargetView(target, &rtvDesc, &rtv),
            "CreateRenderTargetView(eye)");

        ID3D11RenderTargetView* rtvs[] = {rtv.Get()};
        context->OMSetRenderTargets(1, rtvs, nullptr);
        const float clear[4] = {0.012f, 0.012f, 0.016f, 1.0f};
        context->ClearRenderTargetView(rtv.Get(), clear);

        D3D11_VIEWPORT viewport{};
        viewport.Width = static_cast<float>(targetWidth);
        viewport.Height = static_cast<float>(targetHeight);
        viewport.MinDepth = 0.0f;
        viewport.MaxDepth = 1.0f;
        context->RSSetViewports(1, &viewport);
        context->RSSetState(rasterizer_.Get());
        context->IASetInputLayout(inputLayout_.Get());
        context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        const UINT stride = sizeof(Vertex);
        const UINT offset = 0;
        ID3D11Buffer* buffers[] = {vertexBuffer_.Get()};
        context->IASetVertexBuffers(0, 1, buffers, &stride, &offset);
        context->VSSetShader(vertexShader_.Get(), nullptr, 0);
        context->PSSetShader(pixelShader_.Get(), nullptr, 0);
        ID3D11SamplerState* samplers[] = {sampler_.Get()};
        context->PSSetSamplers(0, 1, samplers);

        if (baseSrv) {
            DrawQuad(context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f);
        }

        if (sbsSrv && stereoRect) {
            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;
            DrawQuad(context, view, *stereoRect, -kStereoDistanceMeters,
                sbsSrv, u0, 0.0f, u1, 1.0f);
        }

        if (cursorValid && cursorTexture_.Valid()) {
            PanelRect cursor{
                cursorX - kCursorSizeMeters * 0.5f,
                cursorX + kCursorSizeMeters * 0.5f,
                cursorY + kCursorSizeMeters * 0.5f,
                cursorY - kCursorSizeMeters * 0.5f};
            DrawQuad(context, view, cursor, -kCursorDistanceMeters,
                cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f);
        }

        ID3D11ShaderResourceView* nullSrv[] = {nullptr};
        context->PSSetShaderResources(0, 1, nullSrv);
        context->OMSetRenderTargets(0, nullptr, nullptr);
    }

private:
    ComPtr<ID3D11VertexShader> vertexShader_;
    ComPtr<ID3D11PixelShader> pixelShader_;
    ComPtr<ID3D11InputLayout> inputLayout_;
    ComPtr<ID3D11Buffer> vertexBuffer_;
    ComPtr<ID3D11SamplerState> sampler_;
    ComPtr<ID3D11RasterizerState> rasterizer_;
    SourceTexture cursorTexture_;

    void DrawQuad(
        ID3D11DeviceContext* context,
        const XrView& view,
        const PanelRect& rect,
        float z,
        ID3D11ShaderResourceView* texture,
        float u0, float v0, float u1, float v1) {

        const Vec3 tl{rect.left, rect.top, z};
        const Vec3 tr{rect.right, rect.top, z};
        const Vec3 bl{rect.left, rect.bottom, z};
        const Vec3 br{rect.right, rect.bottom, z};
        const std::array<Vertex, 6> vertices = {
            ProjectVertex(view, tl, u0, v0),
            ProjectVertex(view, bl, u0, v1),
            ProjectVertex(view, tr, u1, v0),
            ProjectVertex(view, tr, u1, v0),
            ProjectVertex(view, bl, u0, v1),
            ProjectVertex(view, br, u1, v1),
        };

        D3D11_MAPPED_SUBRESOURCE mapped{};
        CheckHr(context->Map(vertexBuffer_.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped),
            "Map(vertex)");
        std::memcpy(mapped.pData, vertices.data(), sizeof(vertices));
        context->Unmap(vertexBuffer_.Get(), 0);

        ID3D11ShaderResourceView* srvs[] = {texture};
        context->PSSetShaderResources(0, 1, srvs);
        context->Draw(6, 0);
    }
};


} // namespace ggqv11
