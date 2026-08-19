# GeoGebraForQuest v0.4.0 — integrated stereo portal

This version removes the 2D-Activity -> VR-Activity transition entirely.

The app launches directly as one Spatial SDK activity in passthrough. The complete GeoGebra UI is a single flat Android/WebView panel. GeoGebra behaves normally until the replacement Anaglyph/headset projection option is selected. At that point only the existing 3D Graphics viewport is made transparent and the native stereo scene is revealed behind that rectangle using Spatial SDK hole punching.

There is no second VR window, no second GeoGebra instance, and no mode-switch Activity launch when the headset icon is pressed.
