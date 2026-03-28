#!/usr/bin/env bash
# Build and package the passport-masar-extension for distribution.
# Minifies JS with terser (via npx), copies static files, outputs extension.zip.
#
# Usage:
#   ./scripts/build-extension.sh
#
# Output:
#   passport-masar-extension/dist/extension.zip

set -euo pipefail

command -v npx >/dev/null 2>&1 || { echo "ERROR: npx not found — install Node.js first"; exit 1; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTENSION_DIR="$REPO_ROOT/passport-masar-extension"
DIST_DIR="$EXTENSION_DIR/dist"
BUILD_DIR="$(mktemp -d)"

cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

echo "Building extension from $EXTENSION_DIR"

# Minify and obfuscate JS files
JS_FILES=("background.js" "popup.js" "strings.js" "content-main.js" "content-relay.js" "config.js")
for js in "${JS_FILES[@]}"; do
    echo "  Minifying $js"
    npx --yes terser@5 "$EXTENSION_DIR/$js" \
        --compress drop_console=true \
        --mangle \
        --output "$BUILD_DIR/$js"
done

# Copy static files verbatim
cp "$EXTENSION_DIR/manifest.json" "$BUILD_DIR/"
cp "$EXTENSION_DIR/popup.html"    "$BUILD_DIR/"
cp "$EXTENSION_DIR/popup.css"     "$BUILD_DIR/"
cp -r "$EXTENSION_DIR/icons"      "$BUILD_DIR/"

# Package
mkdir -p "$DIST_DIR"
(cd "$BUILD_DIR" && zip -r - .) > "$DIST_DIR/extension.zip"

SIZE=$(wc -c < "$DIST_DIR/extension.zip")
echo "Built: $DIST_DIR/extension.zip ($SIZE bytes)"
