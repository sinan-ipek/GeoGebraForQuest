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

# Keep the source build's native war layout intact. deployggb.js is generated
# with -PdeployggbRoot=./, therefore all runtime URLs resolve naturally as:
#   GeoGebra/web3d/...
#   GeoGebra/css/...
#   GeoGebra/js/...
#   GeoGebra/keyboard/...
# and so on. Do not move only web3d into HTML5/5.0: that leaves CSS and other
# resources behind at the package root and causes the local loader to request
# non-existent paths such as HTML5/5.0/css/bundles/bundle.css.
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$WAR"/. "$DEST"/

cat > "$DEST/GGQ_SOURCE_BUILD.txt" <<EOF
GeoGebraForQuest source build
version=0.9.10
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_GLASSES (full-colour SBS, permanent Quest draw path)
renderer=QuestStereoRenderer
backing_store=always_2x_width
viewport=left_eye_then_right_eye
presentation=independent synthetic L|R probe using stock SceneMaterial.setStereoMode(StereoMode.LeftRight)
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
