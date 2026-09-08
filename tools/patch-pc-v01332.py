from pathlib import Path
import re


def req(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(label)


# ---------------------------------------------------------------------------
# GeoGebraForQuest PC v0.13.32 — GPU-native embedded SBS
#
# GeoGebra source now keeps [L|R] in the MAIN 3D WebGL backing store on every
# repaint. CEF exports the whole application as one accelerated D3D11 texture.
# The 3D rectangle inside that texture is horizontally compressed SBS.
#
# Active path:
#   GeoGebra WebGL [L|R] -> CEF shared D3D11 texture ->
#       PC GPU remap (show R in 3D rect)
#       XR GPU compositor (A_L | A_R)
#
# No JPEG/Base64, getImageData, ArrayBuffer pixels, RGBA/BGRA swizzle, stereo
# MMF pixel payload, or CPU->GPU stereo upload is used by the active runtime.
# The existing SBS MMF is retained ONLY as a tiny geometry/UI metadata channel.
# pixelFormat=4 means: eyes are embedded in A's CEF GPU texture.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1) JavaScript: reveal the main stereo WebGL canvas and stop all pixel capture.
#    Keep the proven v0.13.18 geometry/UI-overlay detector intact.
# ---------------------------------------------------------------------------
p = Path('pc/pc-stereo-layout.js')
s = p.read_text(encoding='utf-8')

install_marker = "  window.__ggqPcStereoRuntimeInstalledV123 = true;\n"
req(s, install_marker, 'v0.13.32 JS install marker missing')
reveal = r'''

  // GGQ v0.13.32: the source renderer itself now stores true L|R in the main
  // 2W WebGL backing store. Make that canvas compositor-visible so CEF's
  // accelerated shared texture carries the eyes directly on the GPU.
  (function revealGpuNativeStereoCanvas() {
    var style = document.getElementById('ggq-pc-v01332-gpu-native-sbs-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'ggq-pc-v01332-gpu-native-sbs-style';
      style.textContent =
        '.ggq-stereo-canvas{opacity:1!important;background:transparent!important;}' +
        '#ggq-renderer-right-eye{opacity:1!important;}';
      (document.head || document.documentElement).appendChild(style);
    }
    document.documentElement.setAttribute('data-ggq-pc-gpu-native-sbs', 'on');
    window.__ggqPcGpuNativeSbs = true;
  })();
'''
s = s.replace(install_marker, install_marker + reveal, 1)

# The v0.13.31 raw loop is deliberately left compiled but unreachable. This is
# useful as an emergency diagnostic fallback while guaranteeing zero runtime
# pixel readback. Replace only the single startup invocation.
startup = '  requestAnimationFrame(captureLoop);\n  bridge(\'panelReady\', \'\');\n})();'
req(s, startup, 'v0.13.32 capture-loop startup marker missing')
s = s.replace(
    startup,
    "  // v0.13.32: NO captureLoop — geometry events only.\n"
    "  bridge('panelReady', '');\n"
    "})();",
    1)

# Update runtime identity marker used by telemetry/debugging.
s = s.replace("kind: 'js-al-ar-pair-raw'", "kind: 'js-gpu-native-embedded-sbs'")
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2) C# SBS shared writer: add geometry-only format=4 publication.
# ---------------------------------------------------------------------------
p = Path('pc/StereoSharedFrameWriter.cs')
s = p.read_text(encoding='utf-8')
insert_marker = '    public void SetInactive(Rectangle stereoPanelClientBounds, Size applicationClientSize)\n'
req(s, insert_marker, 'v0.13.32 writer SetInactive marker missing')

geometry_writer = r'''    public void WriteGpuEmbeddedGeometry(
        Rectangle stereoPanelClientBounds,
        Size applicationClientSize,
        IReadOnlyList<Rectangle>? uiOverlayClientBounds)
    {
        if (_disposed ||
            applicationClientSize.Width < 2 || applicationClientSize.Height < 2 ||
            stereoPanelClientBounds.Width < 2 || stereoPanelClientBounds.Height < 2)
        {
            return;
        }

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

            // No stereo pixel payload exists in shared memory in v0.13.32.
            _view.Write(44, 0);
            _view.Write(48, 0);
            _view.Write(52, 0);
            _view.Write(56, unchecked((int)_sequence));
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

            // 4 = true L/R are embedded side-by-side inside A's CEF GPU 3D rect.
            _view.Write(116, 4);
            Thread.MemoryBarrier();
            _view.Write(8, evenSequence);
        }
    }

'''
s = s.replace(insert_marker, geometry_writer + insert_marker, 1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 3) Host geometry handler: publish only rect/UI metadata to XR.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')
geom_lock = '''            lock (_geometryLock)
            {
                _stereo3DRenderBounds = rect;
                _stereoUiOverlayBounds = overlays.ToArray();
                _stereo3DActive = true;
            }
'''
req(s, geom_lock, 'v0.13.32 generated geometry lock missing')
s = s.replace(
    geom_lock,
    geom_lock + '''
            // v0.13.32: no B pixels are published. XR needs only the location
            // of the embedded SBS canvas and the already-solved UI overlay rects.
            _sharedStereoFrames.WriteGpuEmbeddedGeometry(
                rect, renderSize, overlays);
''',
    1)

s = re.sub(
    r'(pc-stereo-layout\.js\?v=)[^"\']+',
    r'\g<1>0.13.32-gpu-native-sbs',
    s,
    count=1)
s = s.replace('GeoGebraForQuest PC v0.13.31', 'GeoGebraForQuest PC v0.13.32')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 4) Native PC presentation: GPU-remap the right half of the compressed SBS
#    3D rectangle back to the full 3D rectangle. UI-overlay pixels bypass the
#    remap so menus/stylebars remain normal.
# ---------------------------------------------------------------------------
p = Path('pc/MainFormV11.cs')
s = p.read_text(encoding='utf-8')
field_marker = '    private D3D11Buffer? _vertexBuffer;\n'
req(s, field_marker, 'v0.13.32 PC shader buffer field marker missing')
s = s.replace(field_marker, field_marker + '    private D3D11Buffer? _pcStereoParams;\n', 1)
p.write_text(s, encoding='utf-8')

p = Path('pc/MainFormV11.Graphics.cs')
s = p.read_text(encoding='utf-8')

old_shader = '''        const string shader = """
            Texture2D tex0 : register(t0);
            SamplerState samp0 : register(s0);
            struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD; };
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            PSIn VSMain(VSIn input) { PSIn o; o.pos=input.pos; o.uv=input.uv; return o; }
            float4 PSMain(PSIn input) : SV_Target {
                float4 c = tex0.Sample(samp0, input.uv);
                return float4(c.rgb, 1.0);
            }
            """;'''
req(s, old_shader, 'v0.13.32 original PC shader block missing')
new_shader = '''        const string shader = """
            Texture2D tex0 : register(t0);
            SamplerState samp0 : register(s0);
            cbuffer StereoParams : register(b0) {
                float4 panelRect;
                float4 overlay0;
                float4 overlay1;
                float4 overlay2;
                float4 state;
            };
            struct VSIn { float4 pos : POSITION; float2 uv : TEXCOORD; };
            struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
            PSIn VSMain(VSIn input) { PSIn o; o.pos=input.pos; o.uv=input.uv; return o; }
            bool Inside(float2 p, float4 r) {
                return p.x >= r.x && p.x <= r.z && p.y >= r.y && p.y <= r.w;
            }
            float4 PSMain(PSIn input) : SV_Target {
                float2 uv = input.uv;
                bool overlay =
                    (state.y > 0.5 && Inside(uv, overlay0)) ||
                    (state.y > 1.5 && Inside(uv, overlay1)) ||
                    (state.y > 2.5 && Inside(uv, overlay2));
                if (state.x > 0.5 && !overlay && Inside(uv, panelRect)) {
                    float width = max(0.000001, panelRect.z - panelRect.x);
                    float localX = saturate((uv.x - panelRect.x) / width);
                    // Main CEF 3D rectangle contains compressed [L|R]. PC shows R.
                    uv.x = panelRect.x + width * (0.5 + localX * 0.5);
                }
                float4 c = tex0.Sample(samp0, uv);
                return float4(c.rgb, 1.0);
            }
            """;'''
s = s.replace(old_shader, new_shader, 1)

vb_marker = '''        _vertexBuffer = new D3D11Buffer(
            _device,
            stream,
            new BufferDescription
            {
                BindFlags = BindFlags.VertexBuffer,
                SizeInBytes = Marshal.SizeOf<VertexDx11>() * FullScreenTriangle.Length
            });
'''
req(s, vb_marker, 'v0.13.32 PC vertex buffer creation marker missing')
s = s.replace(
    vb_marker,
    vb_marker + '''
        _pcStereoParams = new D3D11Buffer(
            _device,
            new BufferDescription
            {
                BindFlags = BindFlags.ConstantBuffer,
                SizeInBytes = Marshal.SizeOf<PcStereoShaderData>(),
                Usage = ResourceUsage.Dynamic,
                CpuAccessFlags = CpuAccessFlags.Write,
                OptionFlags = ResourceOptionFlags.None
            });
''',
    1)

render_marker = '''                    context.VertexShader.Set(_vertexShader);
                    context.PixelShader.Set(_pixelShader);
                    context.PixelShader.SetSampler(0, _sampler);

                    var srv = _pcSrvs[_currentPcTexture];'''
req(s, render_marker, 'v0.13.32 RenderLoop shader marker missing')
render_new = '''                    context.VertexShader.Set(_vertexShader);
                    context.PixelShader.Set(_pixelShader);
                    context.PixelShader.SetSampler(0, _sampler);

                    if (_pcStereoParams is not null)
                    {
                        var shaderData = BuildPcStereoShaderData();
                        var box = context.MapSubresource(
                            _pcStereoParams, 0, MapMode.WriteDiscard, MapFlags.None);
                        Marshal.StructureToPtr(shaderData, box.DataPointer, false);
                        context.UnmapSubresource(_pcStereoParams, 0);
                        context.PixelShader.SetConstantBuffer(0, _pcStereoParams);
                    }

                    var srv = _pcSrvs[_currentPcTexture];'''
s = s.replace(render_marker, render_new, 1)

struct_marker = '''    [StructLayout(LayoutKind.Sequential)]
    private readonly struct VertexDx11
'''
req(s, struct_marker, 'v0.13.32 VertexDx11 struct marker missing')
helper = r'''    private PcStereoShaderData BuildPcStereoShaderData()
    {
        Rectangle panel;
        Rectangle[] overlays;
        Size size;
        bool active;
        lock (_geometryLock)
        {
            panel = _stereo3DRenderBounds;
            overlays = _stereoUiOverlayBounds;
            size = _browserSize;
            active = _stereo3DActive && !_stereoUiSuspended;
        }

        var w = Math.Max(1.0f, size.Width);
        var h = Math.Max(1.0f, size.Height);

        static Vector4 NormalizeRect(Rectangle r, float width, float height)
        {
            if (r.Width < 1 || r.Height < 1) return Vector4.Zero;
            return new Vector4(
                Math.Clamp(r.Left / width, 0.0f, 1.0f),
                Math.Clamp(r.Top / height, 0.0f, 1.0f),
                Math.Clamp(r.Right / width, 0.0f, 1.0f),
                Math.Clamp(r.Bottom / height, 0.0f, 1.0f));
        }

        var o0 = overlays.Length > 0 ? NormalizeRect(overlays[0], w, h) : Vector4.Zero;
        var o1 = overlays.Length > 1 ? NormalizeRect(overlays[1], w, h) : Vector4.Zero;
        var o2 = overlays.Length > 2 ? NormalizeRect(overlays[2], w, h) : Vector4.Zero;
        return new PcStereoShaderData
        {
            Panel = NormalizeRect(panel, w, h),
            Overlay0 = o0,
            Overlay1 = o1,
            Overlay2 = o2,
            State = new Vector4(active ? 1.0f : 0.0f, Math.Min(3, overlays.Length), 0, 0)
        };
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PcStereoShaderData
    {
        public Vector4 Panel;
        public Vector4 Overlay0;
        public Vector4 Overlay1;
        public Vector4 Overlay2;
        public Vector4 State;
    }

'''
s = s.replace(struct_marker, helper + struct_marker, 1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5) XR metadata reader: format=4 is geometry-only; do not copy pixel bytes.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-shared.hpp')
s = p.read_text(encoding='utf-8')

# Replace the v0.13.24/27 validity logic regardless of whether mono-left support
# is still present after the generated patch chain.
valid_start = s.find('            const bool legacySbs =')
if valid_start >= 0:
    valid_end = s.find('\n\n            if (valid) {', valid_start)
    if valid_end < 0:
        raise SystemExit('v0.13.32 XR extended validity end missing')
    new_valid = '''            const bool legacySbs =
                (candidate.pixelFormat == 1 || candidate.pixelFormat == 2) &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4;
            const bool monoLeft =
                candidate.pixelFormat == 3 &&
                candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 4;
            const bool embeddedGpu = candidate.pixelFormat == 4;
            const bool valid =
                candidate.active &&
                candidate.clientWidth > 1 &&
                candidate.clientHeight > 1 &&
                candidate.panelWidth > 1 &&
                candidate.panelHeight > 1 &&
                (legacySbs || monoLeft || embeddedGpu);'''
    s = s[:valid_start] + new_valid + s[valid_end:]
else:
    old_valid_tail = '''                candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                candidate.sbsStride == candidate.eyeWidth * 2 * 4 &&
                (candidate.pixelFormat == 1 || candidate.pixelFormat == 2);'''
    req(s, old_valid_tail, 'v0.13.32 XR simple validity marker missing')
    s = s.replace(
        old_valid_tail,
        '''                ((candidate.pixelFormat == 4) ||
                 (candidate.eyeWidth > 1 && candidate.eyeWidth <= kMaxEyeWidth &&
                  candidate.eyeHeight > 1 && candidate.eyeHeight <= kMaxEyeHeight &&
                  candidate.sbsStride == candidate.eyeWidth * 2 * 4 &&
                  (candidate.pixelFormat == 1 || candidate.pixelFormat == 2)));''',
        1)

copy_marker = '''            if (valid) {
                const std::size_t bytes =
                    static_cast<std::size_t>(candidate.sbsStride) *
                    static_cast<std::size_t>(candidate.eyeHeight);
                if (bytes <= kMaxSbsBytes) {
                    candidate.sbs.resize(bytes);
                    std::memcpy(candidate.sbs.data(), view_ + kSbsOffset, bytes);
                }
            }'''
req(s, copy_marker, 'v0.13.32 XR SBS copy block missing')
s = s.replace(
    copy_marker,
    '''            if (valid && candidate.pixelFormat != 4) {
                const std::size_t bytes =
                    static_cast<std::size_t>(candidate.sbsStride) *
                    static_cast<std::size_t>(candidate.eyeHeight);
                if (bytes <= kMaxSbsBytes) {
                    candidate.sbs.resize(bytes);
                    std::memcpy(candidate.sbs.data(), view_ + kSbsOffset, bytes);
                }
            }''',
    1)
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6) XR FullSbsComposer: split the embedded SBS directly out of fullAR.
# ---------------------------------------------------------------------------
p = Path('pc-xr/v11-render.hpp')
s = p.read_text(encoding='utf-8')

block_start = s.find('        const bool pairReady = stereoPair && pairFrame && pairFrame->active &&')
block_end = s.find('\n        ID3D11ShaderResourceView* nullSrv[] = {nullptr};', block_start)
if block_start < 0 or block_end < 0:
    raise SystemExit('v0.13.32 FullSbs pair block missing')

embedded_block = r'''        const bool pairReady = pairFrame && pairFrame->active &&
            pairFrame->pixelFormat == 4 &&
            pairFrame->clientWidth > 1 && pairFrame->clientHeight > 1 &&
            pairFrame->panelWidth > 1 && pairFrame->panelHeight > 1;

        if (pairReady) {
            const float cw = static_cast<float>(pairFrame->clientWidth);
            const float ch = static_cast<float>(pairFrame->clientHeight);
            const float sx = static_cast<float>(fullWidth) / cw;
            const float sy = static_cast<float>(fullHeight) / ch;

            const float panelL = std::clamp(pairFrame->panelLeft * sx, 0.0f, static_cast<float>(fullWidth));
            const float panelT = std::clamp(pairFrame->panelTop * sy, 0.0f, static_cast<float>(fullHeight));
            const float panelR = std::clamp(
                (pairFrame->panelLeft + pairFrame->panelWidth) * sx,
                0.0f, static_cast<float>(fullWidth));
            const float panelB = std::clamp(
                (pairFrame->panelTop + pairFrame->panelHeight) * sy,
                0.0f, static_cast<float>(fullHeight));

            if (panelR > panelL + 1.0f && panelB > panelT + 1.0f) {
                const float fuW = static_cast<float>(fullWidth);
                const float fuH = static_cast<float>(fullHeight);
                const float mid = (panelL + panelR) * 0.5f;
                const float v0 = panelT / fuH;
                const float v1 = panelB / fuH;

                // The CEF source's 3D rectangle is compressed [L|R]. Stretch
                // its left half into A_L's full 3D rectangle.
                DrawRect(context, fullAR,
                    panelL, panelT, panelR, panelB,
                    panelL / fuW, v0, mid / fuW, v1,
                    fullWidth, fullHeight);

                // Stretch its right half into A_R's full 3D rectangle.
                DrawRect(context, fullAR,
                    fuW + panelL, panelT, fuW + panelR, panelB,
                    mid / fuW, v0, panelR / fuW, v1,
                    fullWidth, fullHeight);
            }

            // Restore normal, unwarped UI/menu pixels over the 3D patch in both
            // complete eye images.
            const int overlayCount = std::clamp(
                pairFrame->uiOverlayCount, 0, kMaxUiOverlayRects);
            for (int i = 0; i < overlayCount; ++i) {
                const auto& r = pairFrame->uiOverlays[i];
                if (r.width < 2 || r.height < 2) continue;

                const float l = std::clamp(r.left * sx, 0.0f, static_cast<float>(fullWidth));
                const float t = std::clamp(r.top * sy, 0.0f, static_cast<float>(fullHeight));
                const float rr = std::clamp((r.left + r.width) * sx, 0.0f, static_cast<float>(fullWidth));
                const float bb = std::clamp((r.top + r.height) * sy, 0.0f, static_cast<float>(fullHeight));
                if (rr <= l + 1.0f || bb <= t + 1.0f) continue;

                const float u0 = l / static_cast<float>(fullWidth);
                const float ov0 = t / static_cast<float>(fullHeight);
                const float u1 = rr / static_cast<float>(fullWidth);
                const float ov1 = bb / static_cast<float>(fullHeight);

                DrawRect(context, fullAR,
                    l, t, rr, bb,
                    u0, ov0, u1, ov1, fullWidth, fullHeight);
                DrawRect(context, fullAR,
                    static_cast<float>(fullWidth) + l, t,
                    static_cast<float>(fullWidth) + rr, bb,
                    u0, ov0, u1, ov1, fullWidth, fullHeight);
            }
        }
'''
s = s[:block_start] + embedded_block + s[block_end:]
s = s.replace('JPEG-PROOF A_L/A_R SBS single-panel path',
              'GPU-NATIVE EMBEDDED-SBS A_L/A_R single-panel path')
s = s.replace('TRUE A_L/A_R SBS single-panel path',
              'GPU-NATIVE EMBEDDED-SBS A_L/A_R single-panel path')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 7) XR main: geometry-only frame, no stereo SourceTexture upload.
# ---------------------------------------------------------------------------
p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

# Skip CPU pixel upload for format=4. Existing upload path remains as fallback.
upload_if = '            if (sbsFrame_.active && !sbsFrame_.sbs.empty()) {'
if upload_if in s:
    s = s.replace(upload_if,
                  '            if (sbsFrame_.active && sbsFrame_.pixelFormat != 4 && !sbsFrame_.sbs.empty()) {',
                  1)

# Generated v0.13.28/29/31 compose block.
compose_pattern = re.compile(
    r'''                    const bool pairReady =\n.*?                    fullSbsSrv = fullSbsComposer_\.Compose\(\n                        device_\.Get\(\), context_\.Get\(\),\n                        baseTexture_\.Srv\(\),\n                        baseTexture_\.Width\(\), baseTexture_\.Height\(\),\n                        .*?\n                        .*?\);''',
    re.S)
match = compose_pattern.search(s)
if not match:
    raise SystemExit('v0.13.32 XR generated compose block missing')
compose_new = '''                    const bool pairReady =
                        sbsFrame_.active && sbsFrame_.pixelFormat == 4;
                    fullSbsSrv = fullSbsComposer_.Compose(
                        device_.Get(), context_.Get(),
                        baseTexture_.Srv(),
                        baseTexture_.Width(), baseTexture_.Height(),
                        nullptr,
                        pairReady ? &sbsFrame_ : nullptr);'''
s = s[:match.start()] + compose_new + s[match.end():]

s = s.replace(
    'initialized: A CEF GPU + proven JPEG L/R -> GPU A_L|A_R full-SBS single panel',
    'initialized: CEF GPU embedded L|R -> GPU A_L|A_R single panel, zero pixel IPC')
s = s.replace(
    'initialized: A CEF GPU + raw TRUE L/R -> GPU A_L|A_R full-SBS single panel',
    'initialized: CEF GPU embedded L|R -> GPU A_L|A_R single panel, zero pixel IPC')
p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 8) Version/package labels + build guard replacement.
# ---------------------------------------------------------------------------
p = Path('pc/GeoGebraForQuest.PC.csproj')
s = p.read_text(encoding='utf-8')
s = re.sub(r'<Version>[^<]+</Version>', '<Version>0.13.32</Version>', s, count=1)
s = re.sub(r'<FileVersion>[^<]+</FileVersion>', '<FileVersion>0.13.32.0</FileVersion>', s, count=1)
s = re.sub(r'<AssemblyVersion>[^<]+</AssemblyVersion>', '<AssemblyVersion>0.13.32.0</AssemblyVersion>', s, count=1)
p.write_text(s, encoding='utf-8')

p = Path('pc/build.ps1')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'GeoGebraForQuest-PC-v0.13.31-raw-legacy-bgra-win-x64',
    'GeoGebraForQuest-PC-v0.13.32-gpu-native-sbs-win-x64')
s = s.replace('0.13.31-raw-legacy-bgra', '0.13.32-gpu-native-sbs')
s = s.replace(r'0\.13\.31-raw-legacy-bgra', r'0\.13\.32-gpu-native-sbs')
s = s.replace('v0.13.31', 'v0.13.32')
s = s.replace(r'v0\.13\.31', r'v0\.13\.32')

# Remove the inherited v0.13.31 requirement that the ACTIVE runtime call
# getImageData/raw IPC. v0.13.32 keeps those functions dead as fallback only.
start = s.find('if (-not $runtimeText.Contains("var CAPTURE_INTERVAL_MS = 16"))')
end_token = 'if (-not $sharedText.Contains("candidate.pixelFormat == 1"))'
end = s.find(end_token, start)
if start >= 0 and end >= 0:
    end_line = s.find('\n', end)
    end_line = len(s) if end_line < 0 else end_line + 1
    gpu_guard = '''if (-not $runtimeText.Contains("data-ggq-pc-gpu-native-sbs")) { throw "v0.13.32 doğrulaması: GPU-native SBS canvas reveal eksik." }
if ($runtimeText.Contains("requestAnimationFrame(captureLoop);`n  bridge('panelReady'")) { throw "v0.13.32 doğrulaması: active CPU capture loop hâlâ başlatılıyor." }
if (-not $writerText.Contains("WriteGpuEmbeddedGeometry")) { throw "v0.13.32 doğrulaması: geometry-only writer eksik." }
if (-not $writerText.Contains("_view.Write(116, 4)")) { throw "v0.13.32 doğrulaması: embedded GPU format=4 eksik." }
if (-not $sharedText.Contains("embeddedGpu")) { throw "v0.13.32 doğrulaması: XR geometry-only reader eksik." }
'''
    s = s[:start] + gpu_guard + s[end_line:]

p.write_text(s, encoding='utf-8')


# ---------------------------------------------------------------------------
# 9) Hard final invariants.
# ---------------------------------------------------------------------------
checks = {
    'pc/pc-stereo-layout.js': [
        'ggq-pc-v01332-gpu-native-sbs-style',
        'data-ggq-pc-gpu-native-sbs',
        'NO captureLoop',
    ],
    'pc/MainFormV11.cs': [
        'WriteGpuEmbeddedGeometry',
        '0.13.32-gpu-native-sbs',
        '_pcStereoParams',
    ],
    'pc/StereoSharedFrameWriter.cs': [
        'WriteGpuEmbeddedGeometry',
        '_view.Write(116, 4)',
    ],
    'pc/MainFormV11.Graphics.cs': [
        'cbuffer StereoParams',
        'BuildPcStereoShaderData',
        '0.5 + localX * 0.5',
    ],
    'pc-xr/v11-shared.hpp': [
        'embeddedGpu',
        'candidate.pixelFormat != 4',
    ],
    'pc-xr/v11-render.hpp': [
        'GPU-NATIVE EMBEDDED-SBS',
        'pairFrame->pixelFormat == 4',
        'const float mid = (panelL + panelR) * 0.5f;',
    ],
    'pc-xr/main-v11.cpp': [
        'sbsFrame_.pixelFormat == 4',
        'nullptr,',
        'fullSbsComposer_.Compose',
    ],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding='utf-8')
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'v0.13.32 invariant missing in {file}: {needle}')

runtime = Path('pc/pc-stereo-layout.js').read_text(encoding='utf-8')
# There must be exactly zero startup calls to the raw capture RAF loop.
if re.search(r'^\s*requestAnimationFrame\(captureLoop\);\s*$', runtime, re.M):
    raise SystemExit('v0.13.32 active captureLoop startup remains')

print('GeoGebraForQuest PC v0.13.32 GPU-native embedded SBS architecture applied')
