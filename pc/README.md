# GeoGebraForQuest PC v0.1.0 — Exp46 base

This is the first Windows/PCVR prototype of **GeoGebraForQuest PC**.

## Source base

The GeoGebra/Web3D stereo renderer comes from the current Quest experimental line:

- Quest branch: `experimental-embedded-stereo`
- PC branch: `pc-v0.1-exp46-base`
- Base at branch creation: Exp46 (`0.9.30-exp46-hover-target-grip-focus`)
- Upstream GeoGebra source commit remains the one pinned by `tools/build-geogebra-quest.sh`

The Android/Quest lifecycle hacks are **not** copied into the Windows shell. Windows uses its own native WebView2 profile, popup, file picker and save flow while reusing the patched GeoGebra Web3D/stereo renderer.

## v0.1 architecture

```text
GeoGebraForQuestPC.exe
  |
  |-- WebView2: local patched GeoGebra Web3D
  |-- physical PC mouse + keyboard
  |-- native Windows local .ggb open/save
  |-- shared WebView2 profile for GeoGebra login/popups
  |-- Stereo Panel B: mono PC preview by default
  |
  +-- shared memory: L/R eye frames + B rectangle
          |
          v
GeoGebraForQuestPC.XR.exe
  |
  |-- active Windows OpenXR runtime
  |-- captures the visible app client area as one large quad
  |-- base app quad -> BOTH eyes
  |-- B left texture -> LEFT eye only
  +-- B right texture -> RIGHT eye only
          |
          v
Meta Quest Link cable OR Air Link
```

The application does not have separate cable and Wi-Fi code paths. Link vs Air Link is selected by the Meta PCVR connection/runtime.

## Expected v0.1 user flow

1. Connect Quest to the PC using Meta Quest Link, either USB Link cable or Air Link.
2. Make Meta Quest Link the active OpenXR runtime when testing without SteamVR.
3. Start `GeoGebraForQuestPC.exe`.
4. The app automatically starts its OpenXR companion. If the headset/runtime was not ready, use **Quest'e Bağlan** to retry.
5. Use GeoGebra normally with the physical PC mouse and keyboard.
6. Open a 3D Graphics view. Stereo Panel B receives the Exp46 left/right eye renderer frames.
7. On the PC, B defaults to a normal mono preview. In Quest, B is replaced by real left/right eye-specific textures.
8. **PC'de SBS** is only a diagnostic monitor preview toggle and does not change Quest stereo routing.

## Files

- `pc/MainForm.cs` — Windows GeoGebra UI, WebView2 bridge, open/save, XR launch
- `pc/StereoPanelControl.cs` — PC-side B panel preview
- `pc/StereoSharedFrameWriter.cs` — cross-process L/R frame transport
- `pc/XrCompanionManager.cs` — starts/stops the XR process
- `pc-xr/main.cpp` — OpenXR + D3D11 compositor
- `pc-xr/CMakeLists.txt` — pinned OpenXR SDK build
- `pc/build.ps1` — final Windows package build
- `.github/workflows/pc-v0.1-exp46-build.yml` — Linux Web3D + Windows build pipeline

## Known v0.1 limitations

This is intentionally a first integration test, not a release candidate.

- The PC app image is captured from the **visible Windows client area** using GDI screen capture. Keep the GeoGebraForQuest PC window visible and unobscured while testing in Quest. A later version should replace this with Windows Graphics Capture so occlusion/minimization does not matter.
- The first OpenXR panel is fixed in local space at startup. Quest-controller move/resize behavior from the standalone Quest app is not yet ported.
- B eye routing is implemented, but headset/device testing is still required to verify scale, placement, eye order, latency and runtime compatibility.
- Online login is deliberately implemented with a normal persistent WebView2 browser profile rather than the standalone Quest app's Android cold-process/session-recovery path. It must be tested independently on Windows.
- Local open/save has both GeoGebra's normal browser UI and explicit Windows wrapper buttons; behavior must be tested with real `.ggb` files.

## Build

The recommended build is GitHub Actions because the patched GeoGebra GWT/Web3D build is already proven on Linux.

The workflow produces:

```text
GeoGebraForQuest-PC-v0.1.0-exp46-win-x64.zip
```

with this layout:

```text
GeoGebraForQuestPC.exe
assets/
xr/
  GeoGebraForQuestPC.XR.exe
  openxr_loader.dll   (when produced as a sidecar by the SDK build)
```
