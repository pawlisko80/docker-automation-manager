#!/bin/bash
# Download static assets for DAM web UI (Alpine.js + Font Awesome)
# Run this once after cloning, updating, or when assets are missing.
# On QNAP: bash scripts/fetch-static.sh

set -e
STATIC_DIR="$(dirname "$0")/../dam/web/static"
mkdir -p "$STATIC_DIR"

echo "Downloading Alpine.js..."
curl -sL "https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.13.5/cdn.min.js" \
  -o "$STATIC_DIR/alpine.min.js"
echo "  alpine.min.js: $(wc -c < "$STATIC_DIR/alpine.min.js") bytes"

echo "Downloading Font Awesome CSS..."
curl -sL "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" \
  -o "$STATIC_DIR/fa.min.css"
echo "  fa.min.css: $(wc -c < "$STATIC_DIR/fa.min.css") bytes"

# FA requires webfonts for icons to render
WEBFONTS_DIR="$STATIC_DIR/webfonts"
mkdir -p "$WEBFONTS_DIR"
echo "Downloading Font Awesome webfonts..."
for font in fa-brands-400 fa-regular-400 fa-solid-900 fa-v4compatibility; do
  curl -sL "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/webfonts/${font}.woff2" \
    -o "$WEBFONTS_DIR/${font}.woff2" && echo "  ${font}.woff2" || echo "  ${font}.woff2 (skipped)"
done

echo "Done."
