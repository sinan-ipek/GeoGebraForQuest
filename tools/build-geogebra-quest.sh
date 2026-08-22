#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/app/src/main/assets/web/GeoGebra"
WORK="${GGQ_GEOGEBRA_WORK:-$ROOT/.geogebra-source-work}"
SRC="$WORK/geogebra"

# Pinned source revision inspected while designing the Quest stereo renderer.
GEOGEBRA_COMMIT="1d19a6ba1ed9fe4815d2cddc9b085c83d156f875"

rm -rf "$WORK"
mkdir -p "$WORK"

echo "[GGQ] cloning GeoGebra source @ $GEOGEBRA_COMMIT"
git clone --filter=blob:none --no-checkout https://github.com/geogebra/geogebra.git "$SRC"
git -C "$SRC" fetch --depth 1 origin "$GEOGEBRA_COMMIT"
git -C "$SRC" checkout --detach "$GEOGEBRA_COMMIT"

echo "[GGQ] applying Quest full-colour SBS source patches"
python3 "$ROOT/tools/patch-geogebra-quest.py" "$SRC"

echo "[GGQ] applying permanent stereo backing-store stability patch"
python3 "$ROOT/tools/patch-geogebra-quest-v097.py" "$SRC"

echo "[GGQ] enabling readable WebGL SBS buffer for live Quest stereo capture"
python3 "$ROOT/tools/patch-geogebra-quest-v0913.py" "$SRC"

echo "[GGQ] compiling GeoGebra Web3D and its static runtime resources"
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
version=0.9.17
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_GLASSES (full-colour SBS, permanent Quest draw path)
renderer=QuestStereoRenderer
backing_store=always_2x_width
viewport=left_eye_then_right_eye
preserve_drawing_buffer=true
presentation=registered VideoSurfacePanelRegistration with StereoMode.LeftRight
stereo_panel=verified v0.9.11 settings: 800x400 pixels, 0.80x0.45 metres, Panel+Transform+Grabbable
capture=WebGL backing store split into four equal horizontal quarters
bridge=four independent quarter JPEG data URLs
native_composition=selectable quarter pair 1+2 or 1+3 mapped to Surface L|R halves
diagnostic_goal=identify real eye packing after v0.9.16 showed nested views inside nominal halves
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
