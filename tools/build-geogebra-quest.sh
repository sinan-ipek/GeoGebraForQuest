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

echo "[GGQ] exporting GeoGebra native context-menu hooks for Quest A"
python3 "$ROOT/tools/patch-geogebra-quest-v0927.py" "$SRC"

echo "[GGQ] routing Quest A to the selected GeoElement context menu"
python3 "$ROOT/tools/patch-geogebra-quest-v0928.py" "$SRC"

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
version=0.9.19
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_GLASSES (full-colour stereo camera math)
renderer=QuestStereoRenderer
backing_store=single_eye_width
viewport=LEFT_EYE and RIGHT_EYE both render at x=0
preserve_drawing_buffer=true
renderer_eye_capture=LEFT_EYE captured after left draw; buffer cleared; RIGHT_EYE captured after right draw
renderer_eye_canvases=ggq-renderer-left-eye,ggq-renderer-right-eye
gpu_sync=gl.finish before each eye canvas copy
presentation=registered VideoSurfacePanelRegistration with StereoMode.LeftRight
bridge=two explicit renderer-eye JPEG data URLs
native_composition=one renderer-left image to Surface left half; one renderer-right image to Surface right half; aspect preserved
no_final_sbs_split=true
no_quarter_diagnostics=true
quest_context_menu_hook=ggqOpenContextMenu,ggqCloseContextMenu
quest_context_menu_mode=selected_geoelements
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
