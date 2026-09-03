#pragma once
#include "v11-shared.hpp"
#include "v123-mouse.hpp"

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
        CheckXr(xrAcquireSwapchainImage(handle_, &acquire, &index),
            "xrAcquireSwapchainImage");
        XrSwapchainImageWaitInfo wait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
        wait.timeout = XR_INFINITE_DURATION;
        CheckXr(xrWaitSwapchainImage(handle_, &wait), "xrWaitSwapchainImage");
        return index;
    }

    void Release() {
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        CheckXr(xrReleaseSwapchainImage(handle_, &release),
            "xrReleaseSwapchainImage");
    }

    ID3D11Texture2D* Texture(std::uint32_t index) const {
        return images_.at(index).texture;
    }
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
cbuffer SampleParams : register(b0) {
    float4 uvBounds;
    float4 flags;
};
struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD0; };
struct VSOut { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
VSOut VSMain(VSIn i) {
    VSOut o;
    o.pos = i.pos;
    o.uv = i.uv;
    return o;
}
float2 boundedUv(float2 uv) {
    return clamp(uv, uvBounds.xy, uvBounds.zw);
}
float4 PSMain(VSOut i) : SV_TARGET {
    float4 center = tex0.Sample(samp0, boundedUv(i.uv));
    if (flags.x < 0.5) return center;

    uint texW = 1;
    uint texH = 1;
    tex0.GetDimensions(texW, texH);
    float2 dx = ddx(i.uv);
    float2 dy = ddy(i.uv);
    float2 sourceDx = dx * float2(texW, texH);
    float2 sourceDy = dy * float2(texW, texH);
    float footprint = max(length(sourceDx), length(sourceDy));

    // If one destination pixel maps to about one source texel, ordinary bilinear
    // filtering is already optimal. When the CEF/WebGL source is much denser than
    // the Quest eye buffer, integrate four sub-samples over the pixel footprint.
    // This preserves one-pixel GeoGebra lines instead of letting them disappear or
    // break into dotted segments during minification.
    if (footprint <= 1.12) return center;

    float2 ox = dx * 0.25;
    float2 oy = dy * 0.25;
    float4 c0 = tex0.Sample(samp0, boundedUv(i.uv - ox - oy));
    float4 c1 = tex0.Sample(samp0, boundedUv(i.uv + ox - oy));
    float4 c2 = tex0.Sample(samp0, boundedUv(i.uv - ox + oy));
    float4 c3 = tex0.Sample(samp0, boundedUv(i.uv + ox + oy));
    return (c0 + c1 + c2 + c3) * 0.25;
}
)";

        ComPtr<ID3DBlob> vsBlob;
        ComPtr<ID3DBlob> psBlob;
        ComPtr<ID3DBlob> errors;
        HRESULT hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-v0.12.3",
            nullptr, nullptr, "VSMain", "vs_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0,
            &vsBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(
                    static_cast<const char*>(errors->GetBufferPointer()),
                    errors->GetBufferSize())
                : "vertex shader compile error";
            throw std::runtime_error(detail);
        }
        errors.Reset();
        hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-v0.12.3",
            nullptr, nullptr, "PSMain", "ps_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0,
            &psBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(
                    static_cast<const char*>(errors->GetBufferPointer()),
                    errors->GetBufferSize())
                : "pixel shader compile error";
            throw std::runtime_error(detail);
        }

        CheckHr(device->CreateVertexShader(
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(),
            nullptr, &vertexShader_),
            "CreateVertexShader");
        CheckHr(device->CreatePixelShader(
            psBlob->GetBufferPointer(), psBlob->GetBufferSize(),
            nullptr, &pixelShader_),
            "CreatePixelShader");

        const D3D11_INPUT_ELEMENT_DESC elements[] = {
            {"POSITION", 0, DXGI_FORMAT_R32G32B32A32_FLOAT, 0, 0,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
            {"TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT, 0, 16,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
        };
        CheckHr(device->CreateInputLayout(
            elements,
            static_cast<UINT>(std::size(elements)),
            vsBlob->GetBufferPointer(),
            vsBlob->GetBufferSize(),
            &inputLayout_),
            "CreateInputLayout");

        D3D11_BUFFER_DESC vb{};
        vb.ByteWidth = sizeof(Vertex) * 6;
        vb.Usage = D3D11_USAGE_DYNAMIC;
        vb.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        CheckHr(device->CreateBuffer(&vb, nullptr, &vertexBuffer_),
            "CreateBuffer(vertex)");

        D3D11_BUFFER_DESC cb{};
        cb.ByteWidth = sizeof(SampleParamsData);
        cb.Usage = D3D11_USAGE_DEFAULT;
        cb.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        CheckHr(device->CreateBuffer(&cb, nullptr, &sampleParamsBuffer_),
            "CreateBuffer(sample params)");

        D3D11_SAMPLER_DESC sampler{};
        sampler.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sampler.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.MinLOD = 0.0f;
        sampler.MaxLOD = D3D11_FLOAT32_MAX;
        CheckHr(device->CreateSamplerState(&sampler, &sampler_),
            "CreateSamplerState");

        D3D11_RASTERIZER_DESC raster{};
        raster.FillMode = D3D11_FILL_SOLID;
        raster.CullMode = D3D11_CULL_NONE;
        raster.DepthClipEnable = TRUE;
        CheckHr(device->CreateRasterizerState(&raster, &rasterizer_),
            "CreateRasterizerState");
    }

    void InitializeCursor(ID3D11Device* device, ID3D11DeviceContext* context) {
        const std::uint32_t controllerPixel = 0xFF00FFFFu;
        const std::uint32_t mousePixel = 0xFFFFFFFFu;
        cursorTexture_.Upload(
            device, context,
            reinterpret_cast<const std::uint8_t*>(&controllerPixel),
            1, 1, 4);
        mouseCursorTexture_.Upload(
            device, context,
            reinterpret_cast<const std::uint8_t*>(&mousePixel),
            1, 1, 4);
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
        ID3D11Buffer* sampleBuffers[] = {sampleParamsBuffer_.Get()};
        context->PSSetConstantBuffers(0, 1, sampleBuffers);

        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;
        if (stereoVisible) {
            // The old v0.12 geometry was calculated for a panel 2 cm IN FRONT of A.
            // Convert it back to A's exact 3D viewport, then place B 2 cm BEHIND A
            // while preserving the same angular boundary in the headset.
            const float frontToBase =
                kScreenDistanceMeters / kStereoDistanceMeters;
            PanelRect baseHole = ScalePanelRect(*stereoRect, frontToBase);
            baseHole = ClampPanelRect(baseHole, baseRect);

            constexpr float behindDistance = kScreenDistanceMeters + 0.02f;
            const float baseToBehind = behindDistance / kScreenDistanceMeters;
            const PanelRect behindStereo =
                ScalePanelRect(baseHole, baseToBehind);

            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;

            // B first. It is geometrically behind A.
            DrawQuad(
                context, view, behindStereo, -behindDistance,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);

            // A second, but with the exact 3D viewport omitted. This is the XR-only
            // transparent 3D window: PC still receives the untouched full CEF image.
            if (baseSrv) {
                DrawBaseWithHole(
                    context, view, baseRect, baseHole, baseSrv);
            }
        } else if (baseSrv) {
            // When a GeoGebra menu/dialog covers 3D, JS marks B inactive. Then A is
            // completely opaque again, so menus can never be hidden behind B.
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
        }

        const MousePointerState mouse = mouseReader_.ReadLatest();
        if (mouse.valid && mouseCursorTexture_.Valid()) {
            const float baseWidth = baseRect.right - baseRect.left;
            const float baseHeight = baseRect.top - baseRect.bottom;
            const float hitX = baseRect.left + baseWidth * mouse.u;
            const float hitY = baseRect.top - baseHeight * mouse.v;
            const float scale = kCursorDistanceMeters / kScreenDistanceMeters;
            const float mouseX = hitX * scale;
            const float mouseY = hitY * scale;
            PanelRect mouseCursor{
                mouseX - kCursorSizeMeters * 0.42f,
                mouseX + kCursorSizeMeters * 0.42f,
                mouseY + kCursorSizeMeters * 0.42f,
                mouseY - kCursorSizeMeters * 0.42f};
            DrawQuad(
                context, view, mouseCursor, -kCursorDistanceMeters,
                mouseCursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);
        }

        if (cursorValid && cursorTexture_.Valid()) {
            PanelRect cursor{
                cursorX - kCursorSizeMeters * 0.5f,
                cursorX + kCursorSizeMeters * 0.5f,
                cursorY + kCursorSizeMeters * 0.5f,
                cursorY - kCursorSizeMeters * 0.5f};
            DrawQuad(
                context, view, cursor, -kCursorDistanceMeters,
                cursorTexture_.Srv(), 0.0f, 0.0f, 1.0f, 1.0f, false);
        }

        ID3D11ShaderResourceView* nullSrv[] = {nullptr};
        context->PSSetShaderResources(0, 1, nullSrv);
        context->OMSetRenderTargets(0, nullptr, nullptr);
    }

private:
    struct SampleParamsData {
        float uvBounds[4];
        float flags[4];
    };

    ComPtr<ID3D11VertexShader> vertexShader_;
    ComPtr<ID3D11PixelShader> pixelShader_;
    ComPtr<ID3D11InputLayout> inputLayout_;
    ComPtr<ID3D11Buffer> vertexBuffer_;
    ComPtr<ID3D11Buffer> sampleParamsBuffer_;
    ComPtr<ID3D11SamplerState> sampler_;
    ComPtr<ID3D11RasterizerState> rasterizer_;
    SourceTexture cursorTexture_;
    SourceTexture mouseCursorTexture_;
    MousePointerSharedReader mouseReader_;

    static PanelRect ScalePanelRect(const PanelRect& rect, float scale) {
        return {
            rect.left * scale,
            rect.right * scale,
            rect.top * scale,
            rect.bottom * scale
        };
    }

    static PanelRect ClampPanelRect(
        const PanelRect& rect,
        const PanelRect& bounds) {
        PanelRect result{
            std::max(rect.left, bounds.left),
            std::min(rect.right, bounds.right),
            std::min(rect.top, bounds.top),
            std::max(rect.bottom, bounds.bottom)
        };
        if (result.right < result.left) result.right = result.left;
        if (result.top < result.bottom) result.top = result.bottom;
        return result;
    }

    void DrawBaseWithHole(
        ID3D11DeviceContext* context,
        const XrView& view,
        const PanelRect& base,
        const PanelRect& hole,
        ID3D11ShaderResourceView* texture) {

        const float width = std::max(0.0001f, base.right - base.left);
        const float height = std::max(0.0001f, base.top - base.bottom);
        const float uLeft = std::clamp((hole.left - base.left) / width, 0.0f, 1.0f);
        const float uRight = std::clamp((hole.right - base.left) / width, 0.0f, 1.0f);
        const float vTop = std::clamp((base.top - hole.top) / height, 0.0f, 1.0f);
        const float vBottom = std::clamp((base.top - hole.bottom) / height, 0.0f, 1.0f);

        constexpr float epsilon = 0.0001f;

        if (base.top - hole.top > epsilon) {
            DrawQuad(
                context, view,
                {base.left, base.right, base.top, hole.top},
                -kScreenDistanceMeters,
                texture, 0.0f, 0.0f, 1.0f, vTop, true);
        }
        if (hole.bottom - base.bottom > epsilon) {
            DrawQuad(
                context, view,
                {base.left, base.right, hole.bottom, base.bottom},
                -kScreenDistanceMeters,
                texture, 0.0f, vBottom, 1.0f, 1.0f, true);
        }
        if (hole.left - base.left > epsilon && hole.top - hole.bottom > epsilon) {
            DrawQuad(
                context, view,
                {base.left, hole.left, hole.top, hole.bottom},
                -kScreenDistanceMeters,
                texture, 0.0f, vTop, uLeft, vBottom, true);
        }
        if (base.right - hole.right > epsilon && hole.top - hole.bottom > epsilon) {
            DrawQuad(
                context, view,
                {hole.right, base.right, hole.top, hole.bottom},
                -kScreenDistanceMeters,
                texture, uRight, vTop, 1.0f, vBottom, true);
        }
    }

    void DrawQuad(
        ID3D11DeviceContext* context,
        const XrView& view,
        const PanelRect& rect,
        float z,
        ID3D11ShaderResourceView* texture,
        float u0,
        float v0,
        float u1,
        float v1,
        bool highQuality) {

        if (!texture || rect.right <= rect.left || rect.top <= rect.bottom) return;

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
        CheckHr(context->Map(
            vertexBuffer_.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped),
            "Map(vertex)");
        std::memcpy(mapped.pData, vertices.data(), sizeof(vertices));
        context->Unmap(vertexBuffer_.Get(), 0);

        SampleParamsData params{};
        params.uvBounds[0] = std::min(u0, u1);
        params.uvBounds[1] = std::min(v0, v1);
        params.uvBounds[2] = std::max(u0, u1);
        params.uvBounds[3] = std::max(v0, v1);
        params.flags[0] = highQuality ? 1.0f : 0.0f;
        context->UpdateSubresource(
            sampleParamsBuffer_.Get(), 0, nullptr, &params, 0, 0);

        ID3D11ShaderResourceView* srvs[] = {texture};
        context->PSSetShaderResources(0, 1, srvs);
        context->Draw(6, 0);
    }
};

} // namespace ggqv11
