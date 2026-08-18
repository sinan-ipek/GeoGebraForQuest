#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/app/src/main/assets/web/GeoGebra"
TMP="$(mktemp -d)"
ZIP="$TMP/geogebra.zip"
URL="https://download.geogebra.org/package/geogebra-math-apps-bundle"

echo "GeoGebra Math Apps Bundle indiriliyor..."
curl -fL --retry 3 "$URL" -o "$ZIP"
unzip -q "$ZIP" -d "$TMP/unpack"
DEPLOY="$(find "$TMP/unpack" -name deployggb.js | head -n 1)"
[ -n "$DEPLOY" ] || { echo "deployggb.js bulunamadı"; exit 1; }
BUNDLE_ROOT="$(dirname "$DEPLOY")"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$BUNDLE_ROOT"/. "$DEST"/
echo "Tamam: $DEST"
