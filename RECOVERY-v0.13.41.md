# GeoGebraForQuest PC v0.13.41 recovery checkpoint

This branch is intentionally rooted at `checkpoint-v0.13.35-working-depth`.

The v0.13.39 and v0.13.40 GPU full-frame SBS experiment is NOT carried into this branch.

Recovery acceptance tests:

1. PC 3D graphics must render normally (no white 3D viewport).
2. Quest stereo image must remain visible and retain real depth.
3. File/Open menus and dialogs must work normally.

The build artifact is labeled v0.13.41 recovery, but the executable core is deliberately the exact v0.13.35 reconstruction until these three baseline behaviors are reconfirmed.