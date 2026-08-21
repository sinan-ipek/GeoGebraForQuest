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

echo "[GGQ] compiling GeoGebra Web3D from patched source"
pushd "$SRC/source/web" >/dev/null
../../gradlew \
  :web:gwtCompile \
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
[ -d "$WAR/web3d" ] || {
  echo "[GGQ] web3d output missing"
  find "$WAR" -maxdepth 2 -type d | sort | head -n 120 || true
  exit 1
}

rm -rf "$DEST"
mkdir -p "$DEST/HTML5/5.0"
cp "$WAR/deployggb.js" "$DEST/deployggb.js"
cp -R "$WAR/web3d" "$DEST/HTML5/5.0/web3d"

# Some applet UI resources are resolved beside deployggb.js / the compiled module.
# Copy the generated/static web resources when they exist, while keeping the
# canonical Web3D directory above.
for name in css js images keyboard sounds; do
  if [ -d "$WAR/$name" ]; then
    cp -R "$WAR/$name" "$DEST/$name"
  fi
done

cat > "$DEST/GGQ_SOURCE_BUILD.txt" <<EOF
GeoGebraForQuest source build
upstream_commit=$GEOGEBRA_COMMIT
projection=PROJECTION_QUEST_STEREO
renderer=QuestStereoRenderer
gwt_module=org.geogebra.web.Web3D
EOF

echo "[GGQ] patched GeoGebra installed at $DEST"
find "$DEST" -maxdepth 3 -type f | head -n 30
