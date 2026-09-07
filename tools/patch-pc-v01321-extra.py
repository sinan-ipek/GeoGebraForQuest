from pathlib import Path


def req(text, needle, label):
    if needle not in text:
        raise SystemExit(label)


p = Path('pc-xr/main-v11.cpp')
s = p.read_text(encoding='utf-8')

# Fine-grained accumulators. These are intentionally process-local and aggregated
# once per second; no per-frame disk IO is introduced.
field_marker = '''    double perfRefreshMsSum_{};
    double perfRefreshMsMax_{};
    double perfPredictedDisplayMs_{};'''
req(s, field_marker, 'v0.13.21 extra: field marker missing')
s = s.replace(field_marker, '''    double perfRefreshMsSum_{};
    double perfRefreshMsMax_{};
    double perfAUpdateMsSum_{};
    double perfAUpdateMsMax_{};
    std::uint64_t perfAUpdateCalls_{};
    double perfBReadMsSum_{};
    double perfBReadMsMax_{};
    std::uint64_t perfBReadCalls_{};
    double perfBUploadMsSum_{};
    double perfBUploadMsMax_{};
    std::uint64_t perfBUploadCalls_{};
    double perfWaitFrameMsSum_{};
    double perfWaitFrameMsMax_{};
    double perfAcquireMsSum_{};
    double perfAcquireMsMax_{};
    std::uint64_t perfAcquireCalls_{};
    double perfRenderEyesMsSum_{};
    double perfRenderEyesMsMax_{};
    std::uint64_t perfRenderEyesCalls_{};
    double perfEndFrameMsSum_{};
    double perfEndFrameMsMax_{};
    double perfPredictedDisplayMs_{};''', 1)

header_old = '''                     << "avg_frame_ms,max_frame_ms,avg_refresh_ms,max_refresh_ms,"
                     << "predicted_display_ms,should_render,session_state,"'''
req(s, header_old, 'v0.13.21 extra: CSV header marker missing')
s = s.replace(header_old, '''                     << "avg_frame_ms,max_frame_ms,avg_refresh_ms,max_refresh_ms,"
                     << "avg_a_update_ms,max_a_update_ms,avg_b_read_ms,max_b_read_ms,"
                     << "avg_b_upload_ms,max_b_upload_ms,avg_wait_frame_ms,max_wait_frame_ms,"
                     << "avg_acquire_ms,max_acquire_ms,avg_render_eyes_ms,max_render_eyes_ms,"
                     << "avg_end_frame_ms,max_end_frame_ms,"
                     << "predicted_display_ms,should_render,session_state,"''', 1)

avg_marker = '''        const double avgFrame = perfFrames_ ? perfFrameMsSum_ / perfFrames_ : 0.0;
        const double avgRefresh = perfFrames_ ? perfRefreshMsSum_ / perfFrames_ : 0.0;
'''
req(s, avg_marker, 'v0.13.21 extra: average marker missing')
s = s.replace(avg_marker, avg_marker + '''        const double avgAUpdate = perfAUpdateCalls_ ? perfAUpdateMsSum_ / perfAUpdateCalls_ : 0.0;
        const double avgBRead = perfBReadCalls_ ? perfBReadMsSum_ / perfBReadCalls_ : 0.0;
        const double avgBUpload = perfBUploadCalls_ ? perfBUploadMsSum_ / perfBUploadCalls_ : 0.0;
        const double avgWaitFrame = perfFrames_ ? perfWaitFrameMsSum_ / perfFrames_ : 0.0;
        const double avgAcquire = perfAcquireCalls_ ? perfAcquireMsSum_ / perfAcquireCalls_ : 0.0;
        const double avgRenderEyes = perfRenderEyesCalls_ ? perfRenderEyesMsSum_ / perfRenderEyesCalls_ : 0.0;
        const double avgEndFrame = perfFrames_ ? perfEndFrameMsSum_ / perfFrames_ : 0.0;
''', 1)

row_marker = '''                 << avgFrame << ',' << perfFrameMsMax_ << ','
                 << avgRefresh << ',' << perfRefreshMsMax_ << ','
                 << perfPredictedDisplayMs_ << ','
'''
req(s, row_marker, 'v0.13.21 extra: CSV row marker missing')
s = s.replace(row_marker, '''                 << avgFrame << ',' << perfFrameMsMax_ << ','
                 << avgRefresh << ',' << perfRefreshMsMax_ << ','
                 << avgAUpdate << ',' << perfAUpdateMsMax_ << ','
                 << avgBRead << ',' << perfBReadMsMax_ << ','
                 << avgBUpload << ',' << perfBUploadMsMax_ << ','
                 << avgWaitFrame << ',' << perfWaitFrameMsMax_ << ','
                 << avgAcquire << ',' << perfAcquireMsMax_ << ','
                 << avgRenderEyes << ',' << perfRenderEyesMsMax_ << ','
                 << avgEndFrame << ',' << perfEndFrameMsMax_ << ','
                 << perfPredictedDisplayMs_ << ','
''', 1)

reset_marker = '''        perfFrameMsSum_ = perfFrameMsMax_ = 0.0;
        perfRefreshMsSum_ = perfRefreshMsMax_ = 0.0;
'''
req(s, reset_marker, 'v0.13.21 extra: reset marker missing')
s = s.replace(reset_marker, reset_marker + '''        perfAUpdateMsSum_ = perfAUpdateMsMax_ = 0.0;
        perfBReadMsSum_ = perfBReadMsMax_ = 0.0;
        perfBUploadMsSum_ = perfBUploadMsMax_ = 0.0;
        perfWaitFrameMsSum_ = perfWaitFrameMsMax_ = 0.0;
        perfAcquireMsSum_ = perfAcquireMsMax_ = 0.0;
        perfRenderEyesMsSum_ = perfRenderEyesMsMax_ = 0.0;
        perfEndFrameMsSum_ = perfEndFrameMsMax_ = 0.0;
        perfAUpdateCalls_ = perfBReadCalls_ = perfBUploadCalls_ = 0;
        perfAcquireCalls_ = perfRenderEyesCalls_ = 0;
''', 1)

# A shared-GPU consumer: includes keyed mutex acquisition, CopyResource, Flush and
# query wait, exactly the synchronous section suspected of perturbing XR cadence.
a_old = '''                    if (baseTexture_.Update(
                            device_.Get(), context_.Get(), gpuFrame_)) {
                        if ((gpuSequence_ % 120) == 0) {'''
req(s, a_old, 'v0.13.21 extra: A update marker missing')
s = s.replace(a_old, '''                    const auto perfAStart = std::chrono::steady_clock::now();
                    const bool perfAUpdated = baseTexture_.Update(
                            device_.Get(), context_.Get(), gpuFrame_);
                    const double perfAMs = PerfMs(perfAStart, std::chrono::steady_clock::now());
                    perfAUpdateMsSum_ += perfAMs;
                    perfAUpdateMsMax_ = std::max(perfAUpdateMsMax_, perfAMs);
                    perfAUpdateCalls_++;
                    if (perfAUpdated) {
                        if ((gpuSequence_ % 120) == 0) {''', 1)

# B mapped-memory read: includes the full SBS memcpy into the C++ snapshot.
b_read_old = '''        SbsSnapshot sbsUpdate{};
        if (sbsReader_.ReadIfChanged(sbsSequence_, sbsUpdate)) {
            sbsSequence_ = sbsUpdate.sequence;'''
req(s, b_read_old, 'v0.13.21 extra: B read marker missing')
s = s.replace(b_read_old, '''        SbsSnapshot sbsUpdate{};
        const auto perfBReadStart = std::chrono::steady_clock::now();
        const bool perfBReadChanged = sbsReader_.ReadIfChanged(sbsSequence_, sbsUpdate);
        const double perfBReadMs = PerfMs(perfBReadStart, std::chrono::steady_clock::now());
        perfBReadMsSum_ += perfBReadMs;
        perfBReadMsMax_ = std::max(perfBReadMsMax_, perfBReadMs);
        perfBReadCalls_++;
        if (perfBReadChanged) {
            sbsSequence_ = sbsUpdate.sequence;''', 1)

# B D3D texture upload: captures texture allocation/reallocation and UpdateSubresource.
b_upload_old = '''                sbsTexture_.Upload(
                    device_.Get(),
                    context_.Get(),
                    sbsFrame_.sbs.data(),'''
req(s, b_upload_old, 'v0.13.21 extra: B upload marker missing')
s = s.replace(b_upload_old, '''                const auto perfBUploadStart = std::chrono::steady_clock::now();
                sbsTexture_.Upload(
                    device_.Get(),
                    context_.Get(),
                    sbsFrame_.sbs.data(),''', 1)
# Put the timing after the Upload call by matching its final rowPitch argument.
upload_tail = '''                    sbsFrame_.eyeHeight,
                    sbsFrame_.sbsStride);
'''
req(s, upload_tail, 'v0.13.21 extra: B upload tail missing')
s = s.replace(upload_tail, upload_tail + '''                const double perfBUploadMs = PerfMs(perfBUploadStart, std::chrono::steady_clock::now());
                perfBUploadMsSum_ += perfBUploadMs;
                perfBUploadMsMax_ = std::max(perfBUploadMsMax_, perfBUploadMs);
                perfBUploadCalls_++;
''', 1)

# xrWaitFrame is expected to block by design; recording it lets us distinguish
# compositor pacing from app-side work.
wait_old = '''        XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
        XrFrameState frameState{XR_TYPE_FRAME_STATE};
        CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");'''
req(s, wait_old, 'v0.13.21 extra: wait-frame marker missing')
s = s.replace(wait_old, '''        XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
        XrFrameState frameState{XR_TYPE_FRAME_STATE};
        const auto perfWaitStart = std::chrono::steady_clock::now();
        CheckXr(xrWaitFrame(session_, &waitInfo, &frameState), "xrWaitFrame");
        const double perfWaitMs = PerfMs(perfWaitStart, std::chrono::steady_clock::now());
        perfWaitFrameMsSum_ += perfWaitMs;
        perfWaitFrameMsMax_ = std::max(perfWaitFrameMsMax_, perfWaitMs);''', 1)

# Swapchain acquire+wait lives inside ProjectionSwapchain::Acquire().
acquire_old = '''                const std::uint32_t imageIndex = projectionSwapchain_.Acquire();
                ID3D11Texture2D* target ='''
req(s, acquire_old, 'v0.13.21 extra: acquire marker missing')
s = s.replace(acquire_old, '''                const auto perfAcquireStart = std::chrono::steady_clock::now();
                const std::uint32_t imageIndex = projectionSwapchain_.Acquire();
                const double perfAcquireMs = PerfMs(perfAcquireStart, std::chrono::steady_clock::now());
                perfAcquireMsSum_ += perfAcquireMs;
                perfAcquireMsMax_ = std::max(perfAcquireMsMax_, perfAcquireMs);
                perfAcquireCalls_++;
                ID3D11Texture2D* target =''', 1)

# Measure both RenderEye calls together. Start just before the eye loop and stop
# immediately before releasing the swapchain image.
eye_loop = '''                for (std::uint32_t eye = 0; eye < 2; ++eye) {
                    renderer_.RenderEye('''
req(s, eye_loop, 'v0.13.21 extra: eye loop marker missing')
s = s.replace(eye_loop, '''                const auto perfEyesStart = std::chrono::steady_clock::now();
                for (std::uint32_t eye = 0; eye < 2; ++eye) {
                    renderer_.RenderEye(''', 1)
release_marker = '''                projectionSwapchain_.Release();'''
req(s, release_marker, 'v0.13.21 extra: release marker missing')
s = s.replace(release_marker, '''                const double perfEyesMs = PerfMs(perfEyesStart, std::chrono::steady_clock::now());
                perfRenderEyesMsSum_ += perfEyesMs;
                perfRenderEyesMsMax_ = std::max(perfRenderEyesMsMax_, perfEyesMs);
                perfRenderEyesCalls_++;
                projectionSwapchain_.Release();''', 1)

# EndFrame timing catches runtime/compositor submission delays.
end_old = '''        CheckXr(xrEndFrame(session_, &endInfo), "xrEndFrame");'''
req(s, end_old, 'v0.13.21 extra: end-frame marker missing')
s = s.replace(end_old, '''        const auto perfEndStart = std::chrono::steady_clock::now();
        CheckXr(xrEndFrame(session_, &endInfo), "xrEndFrame");
        const double perfEndMs = PerfMs(perfEndStart, std::chrono::steady_clock::now());
        perfEndFrameMsSum_ += perfEndMs;
        perfEndFrameMsMax_ = std::max(perfEndFrameMsMax_, perfEndMs);''', 1)

p.write_text(s, encoding='utf-8')
print('v0.13.21 fine-grained XR timings applied')
