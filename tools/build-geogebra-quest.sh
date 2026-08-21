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

echo "[GGQ] applying Quest source patches"
python3 "$ROOT/tools/patch-geogebra-quest.py" "$SRC"

echo "[GGQ] compiling GeoGebra Web3D and its static runtime resources"
pushd "$SRC/source/web" >/dev/null
../../gradlew \
  :web:gwtCompile \
  :web:copyHtml \
  :web:mergeDeploy \
  -Pgmodule=org.geogebra.web.Web3D \
  -PdeployggbRoot=./HTML5/5.0/ \
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

# copyHtml is important: besides generating HTML/CSS it copies GeoGebra's
# resources/war tree and GIAC runtime files into war/. Earlier source builds
# copied only deployggb.js + web3d and therefore produced an incomplete local
# Math Apps runtime package on Quest.
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$WAR"/. "$DEST"/

# deployggb.js in our wrapper is deliberately configured to use the historical
# Math Apps Bundle layout: GeoGebra/HTML5/5.0/web3d/. Keep one canonical copy of
# the compiled GWT module there and remove the temporary root module directory.
mkdir -p "$DEST/HTML5/5.0"
rm -rf "$DEST/HTML5/5.0/web3d"
cp -R "$WAR/web3d" "$DEST/HTML5/5.0/web3d"
rm -rf "$DEST/web3d"

cat > "$DEST/GGQ_SOURCE_BUILD.txt" <<EOF
GeoGebraForQuest source build
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_GLASSES (render output replaced by full-colour SBS)
renderer=QuestStereoRenderer
gwt_module=org.geogebra.web.Web3D
static_runtime=copyHtml/resources-war included
EOF

echo "[GGQ] patched GeoGebra installed at $DEST"
echo "[GGQ] top-level package entries:"
find "$DEST" -maxdepth 1 -mindepth 1 -printf '%f\n' | sort | head -n 120
echo "[GGQ] Web3D bootstrap:"
ls -lh "$DEST/HTML5/5.0/web3d/web3d.nocache.js"
