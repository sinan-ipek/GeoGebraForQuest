# GeoGebraForQuest

GeoGebraForQuest is an experimental Meta Quest wrapper around the local GeoGebra Math Apps bundle.

## Current development build: v0.7.3

The v0.7.x line automatically detects the visible GeoGebra 3D WebGL view, internally selects GeoGebra's Glasses projection, captures full-RGB left/right eye passes, and presents them to a native `StereoMode.LeftRight` media surface.

### v0.7.3 architecture

- The normal GeoGebra WebView remains the **front interaction layer**.
- The stereo media surface sits **behind** the WebView as an underlay.
- Only the active 3D WebGL canvas is made almost transparent; controller rays still hit the real WebView canvas.
- GeoGebra dialogs, settings, save/login UI and the virtual keyboard are no longer used as a reason to disable stereo globally. They simply draw in the WebView in front of the stereo underlay.
- The colour helper opens the 3D Projection settings, disables GeoGebra's `GrayScale` option, and then closes Settings through GeoGebra's real `SheetTitlePanel.closeBtn` control.
- Projection-selection buttons are internal implementation details and are hidden from the user.

This is still a debug/test build. The on-screen GGQ debug overlay is intentionally enabled so Quest-side tests can report stereo state, direct-eye frame counters, colour configuration, and underlay-hole state.
