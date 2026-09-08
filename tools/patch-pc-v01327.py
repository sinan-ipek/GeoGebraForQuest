from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


def sub_once(pattern: str, repl: str, text: str, label: str, flags=0) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: replacements={count}")
    return out


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.27
#
# Architecture experiment: one FULL stereo application panel.
#
#   A_R = the ordinary full CEF GPU image. The patched GeoGebra renderer already
#         leaves RIGHT_EYE in the visible/main WebGL canvas after every requested
#         stereo pair and renders ordinary repaints RIGHT_EYE-only.
#
#   A_L = a GPU copy of A_R in which ONLY the 3D viewport is replaced by the
#         renderer's explicit LEFT_EYE snapshot. Existing GeoGebra UI/menu pixels
#         are then restored over that viewport from A_R.
#
#   FULL_SBS = A_L | A_R, composed entirely on the XR D3D11 GPU.
#
# Quest/OpenXR renders one physical application panel. The left physical eye
# samples the left half of FULL_SBS; the right physical eye samples the right
# half. There is no A/B depth sandwich, no transparent 3D hole and no B panel.
#
# Transport carries ONLY the L 3D image as raw RGBA ArrayBuffer. A_R already
# arrives through the proven CEF accelerated shared-texture path.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1) JavaScript: v0.13.24 raw transport -> LEFT eye only.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

# Do not artificially cap the experiment at 30 fps. The one-in-flight ACK gate
# still prevents backlog, so the actual renderer/IPC throughput self-throttles.
s = s.replace('  var CAPTURE_INTERVAL_MS = 33;', '  var CAPTURE_INTERVAL_MS = 16;', 1)
s = s.replace("kind: 'js-stereo-raw-arraybuffer'", "kind: 'js-al-ar-left-raw'", 1)

s = sub_once(
    r"  function ensureRawCaptureCanvasSize\(eyeWidth, eyeHeight\) \{.*?\n  \}\n",
    r'''  function ensureRawCaptureCanvasSize(eyeWidth, eyeHeight) {
    if (rawCaptureCanvas.width !== eyeWidth) rawCaptureCanvas.width = eyeWidth;
    if (rawCaptureCanvas.height !== eyeHeight) rawCaptureCanvas.height = eyeHeight;
    if (rawCaptureContext) {
      rawCaptureContext.imageSmoothingEnabled = true;
      rawCaptureContext.imageSmoothingQuality = 'high';
    }
  }
''',
    s,
    'v0.13.27 one-eye capture-size replacement',
    re.S)

capture_start = s.find('  function beginRawStereoCapture(serial, requestedAt) {')
capture_end = s.find('\n  // Called by the C# host after the ArrayBuffer', capture_start)
if capture_start < 0 or capture_end < 0:
    raise SystemExit('v0.13.27 beginRawStereoCapture block missing')

new_capture = r'''  function beginRawStereoCapture(serial, requestedAt) {
    if (!rawCaptureContext || rawInFlight) return false;
    if (serial === lastDeliveredStereoSerial) return true;

    var geometry = geometryState;
    if (!geometry || !geometry.canvas || !geometry.rect) {
      reportInactive('ui-or-no-3d');
      return false;
    }

    // The source build guarantees that this hidden canvas is the completed
    // LEFT_EYE pass. RIGHT_EYE is deliberately NOT copied: it is already the
    // ordinary visible GeoGebra WebGL canvas and therefore already present in A.
    var eyes = getRendererEyeCanvases();
    if (!eyes || !eyes.left) return false;

    try {
      var sourceWidth = eyes.left.width | 0;
      var sourceHeight = eyes.left.height | 0;
      if (sourceWidth < 2 || sourceHeight < 2) return false;

      var captureSize = computeCaptureSize(sourceWidth, sourceHeight, geometry.rect);
      var eyeWidth = captureSize.width;
      var eyeHeight = captureSize.height;
      ensureRawCaptureCanvasSize(eyeWidth, eyeHeight);

      var drawStartedAt = performance.now();
      rawCaptureContext.setTransform(1, 0, 0, 1, 0, 0);
      rawCaptureContext.clearRect(0, 0, eyeWidth, eyeHeight);
      rawCaptureContext.drawImage(
        eyes.left,
        0, 0, sourceWidth, sourceHeight,
        0, 0, eyeWidth, eyeHeight
      );
      var drawMs = Math.max(0, performance.now() - drawStartedAt);
      perfDrawCount++;
      perfDrawMsSum += drawMs;
      perfDrawMsMax = Math.max(perfDrawMsMax, drawMs);

      var readStartedAt = performance.now();
      var image = rawCaptureContext.getImageData(0, 0, eyeWidth, eyeHeight);
      var readMs = Math.max(0, performance.now() - readStartedAt);
      perfReadbackCount++;
      perfReadbackMsSum += readMs;
      perfReadbackMsMax = Math.max(perfReadbackMsMax, readMs);

      var expectedBytes = eyeWidth * eyeHeight * 4;
      if (!image || !image.data || image.data.byteLength !== expectedBytes) {
        throw new Error('raw LEFT byte length uyuşmuyor');
      }

      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      rawInFlight = true;
      rawInFlightSerial = serial;
      rawInFlightRequestedAt = requestedAt;
      rawPostedAt = performance.now();

      var postStartedAt = performance.now();
      var posted = postHostMessage({
        type: 'stereoRawLeft',
        serial: serial,
        eyeWidth: eyeWidth,
        eyeHeight: eyeHeight,
        stride: eyeWidth * 4,
        rgba: image.data.buffer
      });
      var postMs = Math.max(0, performance.now() - postStartedAt);
      if (!posted) {
        rawInFlight = false;
        rawInFlightSerial = -1;
        rawInFlightRequestedAt = 0;
        rawPostedAt = 0;
        nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
        return false;
      }

      perfPostCount++;
      perfPostMsSum += postMs;
      perfPostMsMax = Math.max(perfPostMsMax, postMs);
      perfRawBytesSum += expectedBytes;
      perfRawBytesMax = Math.max(perfRawBytesMax, expectedBytes);
      perfLastEyeWidth = eyeWidth;
      perfLastEyeHeight = eyeHeight;
      return true;
    } catch (error) {
      rawInFlight = false;
      rawInFlightSerial = -1;
      rawInFlightRequestedAt = 0;
      rawPostedAt = 0;
      pendingStereoSerial = null;
      pendingStereoRequestedAt = 0;
      nextStereoRequestAt = performance.now() + CAPTURE_INTERVAL_MS;
      reportRuntimeError(
        'Raw LEFT capture hatası: ' +
        (error && error.message ? error.message : String(error || 'bilinmeyen hata'))
      );
      return false;
    }
  }
'''
s = s[:capture_start] + new_capture + s[capture_end:]

for forbidden in (
    "type: 'stereoRawSbs'",
    'eyeWidth * 2 * 4,\n        rgba: image.data.buffer',
    'eyes.right,\n        0, 0, sourceWidth, sourceHeight'
):
    if forbidden in s:
        raise SystemExit(f'v0.13.27 full-SBS JS still carries old two-eye raw path: {forbidden}')

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) Host: accept one raw LEFT image and publish one-eye RGBA into the existing
#    shared-memory transport. Header pixelFormat=3 identifies mono LEFT payload.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')

start = s.find('    private bool TryHandleRawStereoMessage(object? message)')
end = s.find('    private void AckRawStereo(long serial, bool ok)', start)
if start < 0 or end < 0:
    raise SystemExit('v0.13.27 host raw handler block missing')

new_host = r'''    private bool TryHandleRawStereoMessage(object? message)
    {
        if (message is not IDictionary<string, object> values ||
            !values.TryGetValue("type", out var typeObject) ||
            !string.Equals(typeObject?.ToString(), "stereoRawLeft", StringComparison.Ordinal))
        {
            return false;
        }

        long serial = -1;
        try
        {
            if (!values.TryGetValue("serial", out var serialObject) ||
                !values.TryGetValue("eyeWidth", out var widthObject) ||
                !values.TryGetValue("eyeHeight", out var heightObject) ||
                !values.TryGetValue("stride", out var strideObject) ||
                !values.TryGetValue("rgba", out var rgbaObject) ||
                rgbaObject is not byte[] rgba)
            {
                throw new InvalidDataException("CEF raw LEFT mesajı eksik.");
            }

            serial = Convert.ToInt64(serialObject);
            var eyeWidth = Convert.ToInt32(widthObject);
            var eyeHeight = Convert.ToInt32(heightObject);
            var stride = Convert.ToInt32(strideObject);
            HandleRawStereoLeft(rgba, eyeWidth, eyeHeight, stride, serial);
        }
        catch (Exception ex)
        {
            _cefPageText = "Raw LEFT IPC: " + ex.Message;
            BeginInvokeSafe(UpdateWindowTitle);
            AckRawStereo(serial, false);
        }
        return true;
    }

    private void HandleRawStereoLeft(
        byte[] rgba,
        int eyeWidth,
        int eyeHeight,
        int stride,
        long serial)
    {
        if (_closing || _stereoUiSuspended)
        {
            AckRawStereo(serial, false);
            return;
        }

        var expectedStride = checked(eyeWidth * 4);
        var expectedBytes = checked(expectedStride * eyeHeight);
        if (eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > 2048 || eyeHeight > 2048 ||
            stride != expectedStride || rgba.Length != expectedBytes)
        {
            throw new InvalidDataException(
                $"Raw LEFT boyutu geçersiz: {eyeWidth}x{eyeHeight}, stride={stride}, bytes={rgba.Length}");
        }

        bool active;
        Rectangle rect;
        Rectangle[] overlays;
        Size clientSize;
        lock (_geometryLock)
        {
            active = _stereo3DActive;
            rect = _stereo3DRenderBounds;
            overlays = _stereoUiOverlayBounds;
            clientSize = _browserSize;
        }

        if (!active || rect.Width < 2 || rect.Height < 2 ||
            clientSize.Width < 2 || clientSize.Height < 2)
        {
            AckRawStereo(serial, false);
            return;
        }

        var frame = Interlocked.Increment(ref _stereoFrameNumber);
        var publishWatch = System.Diagnostics.Stopwatch.StartNew();
        _sharedStereoFrames.WriteRawLeftRgba(
            rgba,
            eyeWidth,
            eyeHeight,
            stride,
            rect,
            clientSize,
            overlays,
            frame);
        publishWatch.Stop();
        _performanceTelemetry.RecordRawFrame(
            rgba.Length,
            publishWatch.Elapsed.TotalMilliseconds,
            eyeWidth,
            eyeHeight,
            stride);

        if ((frame % 30) == 0) BeginInvokeSafe(UpdateWindowTitle);
        AckRawStereo(serial, true);
    }

'''
s = s[:start] + new_host + s[end:]

s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.27-al-ar-full-sbs',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.24', 'GeoGebraForQuest PC v0.13.27')
s = s.replace('v0.13.24', 'v0.13.27')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Shared-memory writer: mono LEFT RGBA. We intentionally do NOT duplicate the
#    eye in shared memory; the XR GPU builds the full A_L | A_R texture.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')

method_start = s.find('    public void WriteRawSbsRgba(')
method_end = s.find('    public void SetInactive(', method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit('v0.13.27 WriteRawSbsRgba block missing')

new_writer = r'''    public void WriteRawLeftRgba(
        byte[] rgbaLeft,
        int eyeWidth,
        int eyeHeight,
        int leftStride,
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        IReadOnlyList<Rectangle>? uiOverlayClientBounds,
        long frameNumber)
    {
        if (_disposed || rgbaLeft is null ||
            applicationClientSize.Width < 1 || applicationClientSize.Height < 1 ||
            stereoPanelClientBounds.Width < 2 || stereoPanelClientBounds.Height < 2 ||
            eyeWidth < 2 || eyeHeight < 2 ||
            eyeWidth > MaxEyeWidth || eyeHeight > MaxEyeHeight)
        {
            return;
        }

        var expectedStride = checked(eyeWidth * 4);
        if (leftStride != expectedStride)
            throw new ArgumentException("Raw LEFT stride must be tightly packed RGBA.");
        var totalBytes = checked(leftStride * eyeHeight);
        if (rgbaLeft.Length != totalBytes)
            throw new ArgumentException("Raw LEFT RGBA byte length mismatch.");

        lock (_sync)
        {
            var evenSequence = Interlocked.Add(ref _sequence, 2);
            _view.Write(8, evenSequence - 1);
            _view.Write(16, 1);
            _view.Write(20, applicationClientSize.Width);
            _view.Write(24, applicationClientSize.Height);
            _view.Write(28, stereoPanelClientBounds.Left);
            _view.Write(32, stereoPanelClientBounds.Top);
            _view.Write(36, stereoPanelClientBounds.Width);
            _view.Write(40, stereoPanelClientBounds.Height);
            _view.Write(44, eyeWidth);
            _view.Write(48, eyeHeight);
            _view.Write(52, leftStride);
            _view.Write(56, unchecked((int)frameNumber));
            _view.Write(60, Environment.ProcessId);

            var overlayCount = Math.Min(
                MaxUiOverlayRects,
                uiOverlayClientBounds?.Count ?? 0);
            _view.Write(64, overlayCount);
            for (var i = 0; i < MaxUiOverlayRects; i++)
            {
                var offset = 68 + i * 16;
                var r = i < overlayCount
                    ? uiOverlayClientBounds![i]
                    : Rectangle.Empty;
                _view.Write(offset + 0, r.Left);
                _view.Write(offset + 4, r.Top);
                _view.Write(offset + 8, r.Width);
                _view.Write(offset + 12, r.Height);
            }

            // 3 = raw RGBA mono LEFT eye. RIGHT is already present in A GPU.
            _view.Write(116, 3);
            _view.WriteArray(HeaderSize, rgbaLeft, 0, totalBytes);

            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s[:method_start] + new_writer + s[method_end:]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) XR shared reader: pixelFormat=3 means one RGBA LEFT image, stride=W*4.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
s = p.read_text(encoding='utf-8')

old_valid = '''            const bool valid =
                candidate.active &&
                candidate.clientWidth > 1 &&
                candidate.clientHeight > 1 &&
                candidate.panelWidth > 1 &&
                candidate.panelHeight > 1 &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4 &&
                (candidate.pixelFormat == 1 || candidate.pixelFormat == 2);'''
req(s, old_valid, 'v0.13.27 XR raw validity block missing')
new_valid = '''            const bool legacySbs =
                (candidate.pixelFormat == 1 || candidate.pixelFormat == 2) &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4;
            const bool monoLeft =
                candidate.pixelFormat == 3 &&
                candidate.sbsStride == candidate.eyeWidth * 4;
            const bool valid =
                candidate.active &&
                candidate.clientWidth > 1 &&
                candidate.clientHeight > 1 &&
                candidate.panelWidth > 1 &&
                candidate.panelHeight > 1 &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                (legacySbs || monoLeft);'''
s = s.replace(old_valid, new_valid, 1)

# Raw RGBA is R8G8B8A8 for both old full-SBS format=2 and new mono-LEFT format=3.
s = s.replace(
    '        const DXGI_FORMAT desiredFormat = pixelFormat == 2\n',
    '        const DXGI_FORMAT desiredFormat = (pixelFormat == 2 || pixelFormat == 3)\n',
    1)

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) XR GPU compositor: construct one full A_L | A_R texture.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

insert_marker = 'class ProjectionRenderer {\n'
req(s, insert_marker, 'v0.13.27 ProjectionRenderer marker missing')

composer = r'''// GGQ v0.13.27 full A_L/A_R SBS single-panel path.
// A_R is the full CEF GPU image. A_L starts as the same image and receives one
// GPU-scaled LEFT 3D patch plus the already-discovered A UI/menu overlay patches.
class FullSbsComposer {
public:
    void Initialize(ID3D11Device* device) {
        static const char* shaderSource = R"(
Texture2D tex0 : register(t0);
SamplerState samp0 : register(s0);
struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD0; };
struct VSOut { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
VSOut VSMain(VSIn i) {
    VSOut o;
    o.pos = i.pos;
    o.uv = i.uv;
    return o;
}
float4 PSMain(VSOut i) : SV_TARGET {
    return tex0.Sample(samp0, i.uv);
}
)";

        ComPtr<ID3DBlob> vsBlob;
        ComPtr<ID3DBlob> psBlob;
        ComPtr<ID3DBlob> errors;
        HRESULT hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-FullSbs-v01327",
            nullptr, nullptr, "VSMain", "vs_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0, &vsBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(static_cast<const char*>(errors->GetBufferPointer()), errors->GetBufferSize())
                : "FullSbs vertex shader compile error";
            throw std::runtime_error(detail);
        }
        errors.Reset();
        hr = D3DCompile(
            shaderSource, std::strlen(shaderSource), "GGQ-FullSbs-v01327",
            nullptr, nullptr, "PSMain", "ps_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS, 0, &psBlob, &errors);
        if (FAILED(hr)) {
            const std::string detail = errors
                ? std::string(static_cast<const char*>(errors->GetBufferPointer()), errors->GetBufferSize())
                : "FullSbs pixel shader compile error";
            throw std::runtime_error(detail);
        }

        CheckHr(device->CreateVertexShader(
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &vs_),
            "CreateVertexShader(FullSbs)");
        CheckHr(device->CreatePixelShader(
            psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &ps_),
            "CreatePixelShader(FullSbs)");

        const D3D11_INPUT_ELEMENT_DESC elements[] = {
            {"POSITION", 0, DXGI_FORMAT_R32G32B32A32_FLOAT, 0, 0,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
            {"TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT, 0, 16,
             D3D11_INPUT_PER_VERTEX_DATA, 0},
        };
        CheckHr(device->CreateInputLayout(
            elements, static_cast<UINT>(std::size(elements)),
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), &layout_),
            "CreateInputLayout(FullSbs)");

        D3D11_BUFFER_DESC vb{};
        vb.ByteWidth = sizeof(Vertex) * 6;
        vb.Usage = D3D11_USAGE_DYNAMIC;
        vb.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        CheckHr(device->CreateBuffer(&vb, nullptr, &vb_), "CreateBuffer(FullSbs vertex)");

        D3D11_SAMPLER_DESC sampler{};
        sampler.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sampler.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        sampler.MinLOD = 0.0f;
        sampler.MaxLOD = D3D11_FLOAT32_MAX;
        CheckHr(device->CreateSamplerState(&sampler, &sampler_),
            "CreateSamplerState(FullSbs)");

        D3D11_RASTERIZER_DESC raster{};
        raster.FillMode = D3D11_FILL_SOLID;
        raster.CullMode = D3D11_CULL_NONE;
        raster.DepthClipEnable = TRUE;
        CheckHr(device->CreateRasterizerState(&raster, &raster_),
            "CreateRasterizerState(FullSbs)");
    }

    ID3D11ShaderResourceView* Compose(
        ID3D11Device* device,
        ID3D11DeviceContext* context,
        ID3D11ShaderResourceView* fullAR,
        int fullWidth,
        int fullHeight,
        ID3D11ShaderResourceView* left3D,
        const SbsSnapshot* leftFrame) {

        if (!fullAR || fullWidth < 2 || fullHeight < 2) return nullptr;
        EnsureTarget(device, fullWidth, fullHeight);
        if (!rtv_ || !srv_) return nullptr;

        ID3D11RenderTargetView* rtvs[] = {rtv_.Get()};
        context->OMSetRenderTargets(1, rtvs, nullptr);
        const float clear[4] = {0, 0, 0, 1};
        context->ClearRenderTargetView(rtv_.Get(), clear);

        D3D11_VIEWPORT viewport{};
        viewport.Width = static_cast<float>(fullWidth * 2);
        viewport.Height = static_cast<float>(fullHeight);
        viewport.MinDepth = 0.0f;
        viewport.MaxDepth = 1.0f;
        context->RSSetViewports(1, &viewport);
        context->RSSetState(raster_.Get());
        context->IASetInputLayout(layout_.Get());
        context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        const UINT stride = sizeof(Vertex);
        const UINT offset = 0;
        ID3D11Buffer* buffers[] = {vb_.Get()};
        context->IASetVertexBuffers(0, 1, buffers, &stride, &offset);
        context->VSSetShader(vs_.Get(), nullptr, 0);
        context->PSSetShader(ps_.Get(), nullptr, 0);
        ID3D11SamplerState* samplers[] = {sampler_.Get()};
        context->PSSetSamplers(0, 1, samplers);

        // Both complete application images begin as A_R. This duplicates all UI
        // pixels on the GPU; GeoGebra itself is NOT rendered twice.
        DrawRect(context, fullAR,
            0.0f, 0.0f, static_cast<float>(fullWidth), static_cast<float>(fullHeight),
            0.0f, 0.0f, 1.0f, 1.0f, fullWidth, fullHeight);
        DrawRect(context, fullAR,
            static_cast<float>(fullWidth), 0.0f,
            static_cast<float>(fullWidth * 2), static_cast<float>(fullHeight),
            0.0f, 0.0f, 1.0f, 1.0f, fullWidth, fullHeight);

        const bool leftReady = left3D && leftFrame && leftFrame->active &&
            leftFrame->pixelFormat == 3 &&
            leftFrame->clientWidth > 1 && leftFrame->clientHeight > 1 &&
            leftFrame->panelWidth > 1 && leftFrame->panelHeight > 1;

        if (leftReady) {
            const float cw = static_cast<float>(leftFrame->clientWidth);
            const float ch = static_cast<float>(leftFrame->clientHeight);
            const float sx = static_cast<float>(fullWidth) / cw;
            const float sy = static_cast<float>(fullHeight) / ch;

            const float panelL = std::clamp(leftFrame->panelLeft * sx, 0.0f, static_cast<float>(fullWidth));
            const float panelT = std::clamp(leftFrame->panelTop * sy, 0.0f, static_cast<float>(fullHeight));
            const float panelR = std::clamp(
                (leftFrame->panelLeft + leftFrame->panelWidth) * sx,
                0.0f, static_cast<float>(fullWidth));
            const float panelB = std::clamp(
                (leftFrame->panelTop + leftFrame->panelHeight) * sy,
                0.0f, static_cast<float>(fullHeight));

            if (panelR > panelL + 1.0f && panelB > panelT + 1.0f) {
                // Replace only the 3D viewport in A_L with true LEFT_EYE.
                DrawRect(context, left3D,
                    panelL, panelT, panelR, panelB,
                    0.0f, 0.0f, 1.0f, 1.0f, fullWidth, fullHeight);
            }

            // Menus/stylebars already solved by v0.13.18: copy the corresponding
            // A_R pixels back over the LEFT 3D patch, so UI is identical in A_L/R.
            const int overlayCount = std::clamp(
                leftFrame->uiOverlayCount, 0, kMaxUiOverlayRects);
            for (int i = 0; i < overlayCount; ++i) {
                const auto& r = leftFrame->uiOverlays[i];
                if (r.width < 2 || r.height < 2) continue;

                const float l = std::clamp(r.left * sx, 0.0f, static_cast<float>(fullWidth));
                const float t = std::clamp(r.top * sy, 0.0f, static_cast<float>(fullHeight));
                const float rr = std::clamp((r.left + r.width) * sx, 0.0f, static_cast<float>(fullWidth));
                const float bb = std::clamp((r.top + r.height) * sy, 0.0f, static_cast<float>(fullHeight));
                if (rr <= l + 1.0f || bb <= t + 1.0f) continue;

                const float u0 = l / static_cast<float>(fullWidth);
                const float v0 = t / static_cast<float>(fullHeight);
                const float u1 = rr / static_cast<float>(fullWidth);
                const float v1 = bb / static_cast<float>(fullHeight);
                DrawRect(context, fullAR, l, t, rr, bb,
                    u0, v0, u1, v1, fullWidth, fullHeight);
            }
        }

        ID3D11ShaderResourceView* nullSrv[] = {nullptr};
        context->PSSetShaderResources(0, 1, nullSrv);
        context->OMSetRenderTargets(0, nullptr, nullptr);
        return srv_.Get();
    }

    bool Valid() const { return srv_ != nullptr; }

private:
    ComPtr<ID3D11VertexShader> vs_;
    ComPtr<ID3D11PixelShader> ps_;
    ComPtr<ID3D11InputLayout> layout_;
    ComPtr<ID3D11Buffer> vb_;
    ComPtr<ID3D11SamplerState> sampler_;
    ComPtr<ID3D11RasterizerState> raster_;
    ComPtr<ID3D11Texture2D> texture_;
    ComPtr<ID3D11RenderTargetView> rtv_;
    ComPtr<ID3D11ShaderResourceView> srv_;
    int eyeWidth_{};
    int eyeHeight_{};

    void EnsureTarget(ID3D11Device* device, int width, int height) {
        if (texture_ && eyeWidth_ == width && eyeHeight_ == height) return;
        srv_.Reset();
        rtv_.Reset();
        texture_.Reset();

        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = static_cast<UINT>(width * 2);
        desc.Height = static_cast<UINT>(height);
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DEFAULT;
        desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        CheckHr(device->CreateTexture2D(&desc, nullptr, &texture_),
            "CreateTexture2D(FullSbs)");
        CheckHr(device->CreateRenderTargetView(texture_.Get(), nullptr, &rtv_),
            "CreateRenderTargetView(FullSbs)");
        CheckHr(device->CreateShaderResourceView(texture_.Get(), nullptr, &srv_),
            "CreateShaderResourceView(FullSbs)");
        eyeWidth_ = width;
        eyeHeight_ = height;
        Log("v0.13.27 FullSbs target=" + std::to_string(width * 2) + "x" +
            std::to_string(height));
    }

    void DrawRect(
        ID3D11DeviceContext* context,
        ID3D11ShaderResourceView* texture,
        float l, float t, float r, float b,
        float u0, float v0, float u1, float v1,
        int eyeWidth, int eyeHeight) {

        if (!texture || r <= l || b <= t) return;
        const float totalWidth = static_cast<float>(eyeWidth * 2);
        const float totalHeight = static_cast<float>(eyeHeight);
        const float x0 = 2.0f * l / totalWidth - 1.0f;
        const float x1 = 2.0f * r / totalWidth - 1.0f;
        const float y0 = 1.0f - 2.0f * t / totalHeight;
        const float y1 = 1.0f - 2.0f * b / totalHeight;

        const std::array<Vertex, 6> vertices = {{
            {x0, y0, 0.0f, 1.0f, u0, v0},
            {x0, y1, 0.0f, 1.0f, u0, v1},
            {x1, y0, 0.0f, 1.0f, u1, v0},
            {x1, y0, 0.0f, 1.0f, u1, v0},
            {x0, y1, 0.0f, 1.0f, u0, v1},
            {x1, y1, 0.0f, 1.0f, u1, v1},
        }};

        D3D11_MAPPED_SUBRESOURCE mapped{};
        CheckHr(context->Map(vb_.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped),
            "Map(FullSbs vertex)");
        std::memcpy(mapped.pData, vertices.data(), sizeof(vertices));
        context->Unmap(vb_.Get(), 0);
        ID3D11ShaderResourceView* srvs[] = {texture};
        context->PSSetShaderResources(0, 1, srvs);
        context->Draw(6, 0);
    }
};

'''
s = s.replace(insert_marker, composer + insert_marker, 1)

# Replace the old A-hole/B-behind content stage. Cursors remain the already proven
# XR overlay and therefore do not create a second application panel.
content_start = s.find('        const bool stereoVisible = sbsSrv != nullptr && stereoRect != nullptr;')
content_end = s.find('\n\n        const MousePointerState mouse', content_start)
if content_start < 0 or content_end < 0:
    raise SystemExit('v0.13.27 old B content stage missing')
new_content = r'''        // GGQ v0.13.27: one content panel. full-SBS is A_L|A_R and sits on
        // the exact A plane. There is no secondary B geometry and no transparent hole.
        if (sbsSrv) {
            const float u0 = rightEye ? 0.5f : 0.0f;
            const float u1 = rightEye ? 1.0f : 0.5f;
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                sbsSrv, u0, 0.0f, u1, 1.0f, true);
        } else if (baseSrv) {
            // Splash/fallback remains an ordinary full panel.
            DrawQuad(
                context, view, baseRect, -kScreenDistanceMeters,
                baseSrv, 0.0f, 0.0f, 1.0f, 1.0f, true);
        }'''
s = s[:content_start] + new_content + s[content_end:]
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) XR main loop: upload mono LEFT, compose full SBS on GPU, then feed that one
#    source texture to both physical eyes.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

member_marker = '    ProjectionRenderer renderer_;\n'
req(s, member_marker, 'v0.13.27 renderer member marker missing')
s = s.replace(member_marker, member_marker + '    FullSbsComposer fullSbsComposer_;\n', 1)

init_marker = '        renderer_.Initialize(device_.Get());\n'
req(s, init_marker, 'v0.13.27 renderer init marker missing')
s = s.replace(init_marker, init_marker + '        fullSbsComposer_.Initialize(device_.Get());\n', 1)

# v0.13.24 uploads eyeWidth*2. Mono LEFT uses eyeWidth.
s = s.replace(
    '                    sbsFrame_.eyeWidth * 2,\n                    sbsFrame_.eyeHeight,\n                    sbsFrame_.sbsStride,\n                    sbsFrame_.pixelFormat);',
    '                    sbsFrame_.pixelFormat == 3 ? sbsFrame_.eyeWidth : sbsFrame_.eyeWidth * 2,\n                    sbsFrame_.eyeHeight,\n                    sbsFrame_.sbsStride,\n                    sbsFrame_.pixelFormat);',
    1)

block_start = s.find('                PanelRect stereoRect{};\n                const bool stereoValid =')
block_end = s.find('\n                float cursorX = 0.0f;', block_start)
if block_start < 0 or block_end < 0:
    raise SystemExit('v0.13.27 stereoValid block missing')
new_block = r'''                ID3D11ShaderResourceView* fullSbsSrv = nullptr;
                if (!showSplash && baseTexture_.Valid()) {
                    const bool leftReady =
                        sbsTexture_.Valid() && sbsFrame_.active &&
                        sbsFrame_.pixelFormat == 3 && !sbsFrame_.sbs.empty();
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        leftReady ? sbsTexture_.Srv() : nullptr,
                        leftReady ? &sbsFrame_ : nullptr);
                }
'''
s = s[:block_start] + new_block + s[block_end:]

# Replace the old B arguments in the RenderEye call; keep splash/base selection,
# pointer/cursor and all other established call arguments untouched.
old_args = '''                        baseRect,
                        stereoValid ? sbsTexture_.Srv() : nullptr,
                        stereoValid ? &stereoRect : nullptr,
                        stereoValid ? uiOverlayRects.data() : nullptr,
                        uiOverlayCount,
                        eye == 1,'''
req(s, old_args, 'v0.13.27 RenderEye old stereo argument block missing')
new_args = '''                        baseRect,
                        fullSbsSrv,
                        nullptr,
                        nullptr,
                        0,
                        eye == 1,'''
s = s.replace(old_args, new_args, 1)

# Human-readable XR startup label.
s = s.replace(
    'initialized: CEF GPU texture -> OpenXR projection, no screen capture',
    'initialized: A_R CEF GPU + raw L -> GPU A_L|A_R full-SBS single panel',
    1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 7) Version/package labels and build validation.
# ---------------------------------------------------------------------------
for file in ('pc/GeoGebraForQuest.PC.csproj', 'pc/build.ps1'):
    p = Path(file)
    s = p.read_text(encoding='utf-8')
    if file.endswith('.csproj'):
        s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.27</Version>', s, count=1)
        s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.27.0</FileVersion>', s, count=1)
        s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.27.0</AssemblyVersion>', s, count=1)
    else:
        s = s.replace(
            'GeoGebraForQuest-PC-v0.13.24-raw-arraybuffer-win-x64',
            'GeoGebraForQuest-PC-v0.13.27-al-ar-full-sbs-win-x64')
        s = s.replace('0.13.24-raw-arraybuffer', '0.13.27-al-ar-full-sbs')
        s = s.replace(r'0\.13\.24-raw-arraybuffer', r'0\.13\.27-al-ar-full-sbs')
        s = s.replace('js-stereo-raw-arraybuffer', 'js-al-ar-left-raw')
        s = s.replace('stereoRawSbs', 'stereoRawLeft')
        s = s.replace('WriteRawSbsRgba', 'WriteRawLeftRgba')
        s = s.replace('v0.13.24', 'v0.13.27')
        s = s.replace(r'v0\.13\.24', r'v0\.13\.27')

        # The old v0.13.22/24 validator requires B 2 cm behind A. This experiment
        # deliberately removes that architecture. Replace only that structural check.
        check_start = s.find('if ($renderText -notmatch "behindDistance = kScreenDistanceMeters')
        if check_start >= 0:
            check_end = s.find('\n}', check_start)
            if check_end < 0:
                raise SystemExit('v0.13.27 build validation end missing')
            check_end += 2
            if check_end < len(s) and s[check_end] == '\n':
                check_end += 1
            replacement = '''if ($renderText -notmatch "GGQ v0\\.13\\.27 full A_L/A_R SBS single-panel path" -or
    $renderText -notmatch "class FullSbsComposer" -or
    $renderText -notmatch "rightEye \\? 0\\.5f : 0\\.0f" -or
    $renderText -notmatch "footprint <= 1\\.12") {
    throw "v0.13.27 doğrulaması başarısız: full A_L/A_R SBS / single panel / quality minification eksik."
}
'''
            s = s[:check_start] + replacement + s[check_end:]

    p.write_text(s, encoding='utf-8')

# Final hard invariants.
checks = {
    'pc/pc-stereo-layout.js': ["type: 'stereoRawLeft'", "kind: 'js-al-ar-left-raw'"],
    'pc/MainFormV11.cs': ['HandleRawStereoLeft', 'WriteRawLeftRgba'],
    'pc/StereoSharedFrameWriter.cs': ['WriteRawLeftRgba', '_view.Write(116, 3)'],
    'pc-xr/v11-render.hpp': ['class FullSbsComposer', 'one content panel'],
    'pc-xr/main-v11.cpp': ['FullSbsComposer fullSbsComposer_', 'fullSbsComposer_.Compose']
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.27 final invariant missing in {file}: {needle}')

print('GeoGebraForQuest PC v0.13.27 A_L/A_R full-SBS single-panel architecture applied')
