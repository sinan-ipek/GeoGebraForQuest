#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/app/src/main/assets/web/GeoGebra"
WORK="${GGQ_GEOGEBRA_WORK:-$ROOT/.geogebra-source-work}"
SRC="$WORK/geogebra"

GEOGEBRA_COMMIT="1d19a6ba1ed9fe4815d2cddc9b085c83d156f875"

rm -rf "$WORK"
mkdir -p "$WORK"

echo "[GGQ] cloning GeoGebra source @ $GEOGEBRA_COMMIT"
git clone --filter=blob:none --no-checkout https://github.com/geogebra/geogebra.git "$SRC"
git -C "$SRC" fetch --depth 1 origin "$GEOGEBRA_COMMIT"
git -C "$SRC" checkout --detach "$GEOGEBRA_COMMIT"

echo "[GGQ] applying Quest full-colour stereo source patches"
python3 "$ROOT/tools/patch-geogebra-quest.py" "$SRC"

echo "[GGQ] applying historical stereo stability patch"
python3 "$ROOT/tools/patch-geogebra-quest-v097.py" "$SRC"

echo "[GGQ] enabling readable WebGL buffer"
python3 "$ROOT/tools/patch-geogebra-quest-v0913.py" "$SRC"

echo "[GGQ] adding explicit LEFT_EYE / RIGHT_EYE renderer capture hooks"
python3 "$ROOT/tools/patch-geogebra-quest-v0918.py" "$SRC"

echo "[GGQ] collapsing stereo rendering to one shared W x H viewport"
python3 "$ROOT/tools/patch-geogebra-quest-v0919.py" "$SRC"

echo "[GGQ] reusing final main WebGL canvas for RIGHT_EYE"
python3 "$ROOT/tools/patch-geogebra-quest-v0920.py" "$SRC"

echo "[GGQ] enabling demand-driven LEFT_EYE stereo pairs"
python3 "$ROOT/tools/patch-geogebra-quest-v0921.py" "$SRC"

echo "[GGQ] restoring exp8 serial-gated demand capture scheduler"
python3 "$ROOT/tools/patch-quest-stereo-js-exp8.py" \
  "$ROOT/app/src/main/assets/web/quest-stereo-layout.js"

echo "[GGQ] removing dynamic 540 capture and fixing stereo capture at 720px"
python3 "$ROOT/tools/patch-quest-stereo-js-exp10.py" \
  "$ROOT/app/src/main/assets/web/quest-stereo-layout.js"

echo "[GGQ] raising stereo cadence to ~24fps and reporting depth-pointer hover"
python3 "$ROOT/tools/patch-quest-stereo-js-exp11.py" \
  "$ROOT/app/src/main/assets/web/quest-stereo-layout.js"

echo "[GGQ] exporting GeoGebra native context-menu hooks for Quest A"
python3 "$ROOT/tools/patch-geogebra-quest-v0927.py" "$SRC"

echo "[GGQ] routing Quest A to the selected GeoElement context menu"
python3 "$ROOT/tools/patch-geogebra-quest-v0928.py" "$SRC"

echo "[GGQ] adding selected-first pointer-hit fallback for Quest A"
python3 "$ROOT/tools/patch-geogebra-quest-v0929.py" "$SRC"

echo "[GGQ] anchoring Quest A popup and fallback hit-test to real pointer coordinates"
python3 "$ROOT/tools/patch-geogebra-quest-v0930.py" "$SRC"

echo "[GGQ] keeping native temporary Grip rotation without synthetic white ray continuation"
python3 "$ROOT/tools/patch-geogebra-quest-v0931.py" "$SRC"

echo "[GGQ] adding exp22 deterministic login READY/SUCCESS handshake"
python3 "$ROOT/tools/patch-geogebra-quest-v0933.py" "$SRC"

echo "[GGQ] separating GeoGebra SSID cookie auth from OAuth token auth"
python3 "$ROOT/tools/patch-geogebra-quest-v0934.py" "$SRC"

echo "[GGQ] exporting exp39 direct LoginOperationW OAuth entrypoint"
python3 "$ROOT/tools/patch-geogebra-quest-v0935.py" "$SRC"

echo "[GGQ] calibrating glasses projection for the fixed Quest panel"
python3 "$ROOT/tools/patch-geogebra-quest-v0936.py" "$SRC"

echo "[GGQ] retaining last stereo frame and real popup-state detection"
python3 "$ROOT/tools/patch-android-ui-exp9.py" "$ROOT"

echo "[GGQ] removing UI-priority scheduling and fixing stereo-hole right-click routing"
python3 "$ROOT/tools/patch-android-rightclick-exp10.py" "$ROOT"

echo "[GGQ] keeping depth-pointer hover bridge for stereo cursor diagnostics"
python3 "$ROOT/tools/patch-android-ray-exp11.py" "$ROOT"

echo "[GGQ] routing right Grip to native temporary rotation on safe startup path"
python3 "$ROOT/tools/patch-android-exp13.py" "$ROOT"

echo "[GGQ] keeping cloud login inside the patched local app"
python3 "$ROOT/tools/patch-android-exp15.py" "$ROOT"

echo "[GGQ] handing GeoGebra Open-in-app URLs back to the MAIN patched AppW"
python3 "$ROOT/tools/patch-android-exp17.py" "$ROOT"

echo "[GGQ] handing authenticated popup SSID session back to MAIN local AppW"
python3 "$ROOT/tools/patch-android-exp18.py" "$ROOT"

echo "[GGQ] compiling GeoGebra Web3D and static runtime resources"
pushd "$SRC/source/web" >/dev/null
../../gradlew \
  :web:gwtCompile \
  :web:copyHtml \
  :web:mergeDeploy \
  -Pgmodule=org.geogebra.web.Web3D \
  -PdeployggbRoot=./ \
  --no-daemon \
  --stacktrace
popd >/dev/null

WAR="$SRC/source/web/web/war"
[ -f "$WAR/deployggb.js" ] || {
  echo "[GGQ] deployggb.js missing"
  find "$WAR" -maxdepth 2 -type f | head -n 80 || true
  exit 1
}
[ -f "$WAR/web3d/web3d.nocache.js" ] || {
  echo "[GGQ] web3d bootstrap missing"
  find "$WAR" -maxdepth 2 -type f | head -n 120 || true
  exit 1
}
[ -f "$WAR/css/bundles/bundle.css" ] || {
  echo "[GGQ] bundle.css missing"
  find "$WAR/css" -maxdepth 2 -type f | head -n 120 || true
  exit 1
}

rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$WAR"/. "$DEST"/

cat > "$DEST/GGQ_SOURCE_BUILD.txt" <<EOF
GeoGebraForQuest source build
version=0.9.28
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_GLASSES (full-colour stereo camera math)
projection_calibration=exp45 eye_to_screen_px=1080 eye_separation_px=46 fixed Quest panel geometry
renderer=QuestStereoRenderer
backing_store=single_eye_width
viewport=LEFT_EYE and RIGHT_EYE both render at x=0
preserve_drawing_buffer=true
renderer_normal_frame=RIGHT_EYE only
renderer_stereo_pair=requested LEFT_EYE snapshot then RIGHT_EYE main WebGL canvas
renderer_eye_sources=left=ggq-renderer-left-eye;right=main_webgl_canvas_alias_ggq-renderer-right-eye
stereo_request_hooks=ggqRequestStereoFrame,ggqGetStereoFrameSerial
gpu_sync=gl.finish only when a requested LEFT_EYE snapshot is produced
presentation=registered VideoSurfacePanelRegistration with StereoMode.LeftRight
bridge=serial-gated JPEG pair delivery; fixed 720px; no dynamic resolution; quality 0.78
stereo_scheduler=42ms (~24fps) demand cadence; no UI-priority/adaptive backoff; last frame retained across slow gaps
native_composition=left and right JPEGs to Surface SBS halves; full-half fill preserved
no_final_sbs_split=true
no_quarter_diagnostics=true
quest_context_menu_hook=ggqOpenContextMenu,ggqCloseContextMenu
quest_context_menu_mode=selected_geoelements_then_exact_pointer_native_3d_hit
quest_context_pointer=transparent stereo-hole canvas remains valid input surface
depth_pointer=Meta beam remains visible to A; GeoGebra 3D cursor remains separate; no synthetic continuation line
grip_rotate=right Grip native temporary MODE_ROTATEVIEW; release restores oldMode with EXIT_TEMPORARY_MODE; startup-safe no GrabbableSystem lookup
cloud_login=trusted OAuth token and SSID-cookie paths wait for local LoginOperationW READY and close popup only after local SUCCESS ACK
cloud_login_cookie=SSID is authenticated as cookie; successful API response persists real OAuth token
cloud_openfromggt=trusted ggtcallback url forwarded to MAIN window.ggbApplet.openFile; popup closed after handoff
cloud_materials=account-selected Open-in-app files load through local GgbAPIW ArchiveLoader, never remote popup Classic
runtime_layout=source-war-root
module_base=./
static_runtime=copyHtml/resources-war included
EOF

echo "[GGQ] patched GeoGebra installed at $DEST"
echo "[GGQ] required runtime files:"
ls -lh \
  "$DEST/deployggb.js" \
  "$DEST/web3d/web3d.nocache.js" \
  "$DEST/css/bundles/bundle.css"
