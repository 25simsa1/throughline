#!/bin/bash
# assembles the give-to-a-scholar zip. code comes from the repo, and the
# LOCAL rubric.md + gold/ (never in git) ride along so her copy is
# calibrated to her. usage: ./make-scholar-package.sh [outdir]
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-$HOME/Desktop}"
PKG_DIR="$(mktemp -d)/Throughline"
mkdir -p "$PKG_DIR"

cp -R loaders stages templates "$PKG_DIR/"
cp models.py store.py ingest.py schemas.py verify.py render.py llm.py \
   throughline.py menu.py "$PKG_DIR/"
cp "package/Install Throughline.command" "package/Throughline.command" \
   "package/READ ME FIRST.txt" "$PKG_DIR/"
chmod +x "$PKG_DIR/Install Throughline.command" "$PKG_DIR/Throughline.command"
mkdir -p "$PKG_DIR/chapters" "$PKG_DIR/gold"
[ -f rubric.md ] && cp rubric.md "$PKG_DIR/"
[ -d gold ] && cp -R gold/. "$PKG_DIR/gold/" 2>/dev/null || true
find "$PKG_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

ZIP="$OUT/Throughline.zip"
rm -f "$ZIP"
(cd "$(dirname "$PKG_DIR")" && zip -r -q "$ZIP" "Throughline")
echo "wrote $ZIP"
unzip -l "$ZIP" | tail -3
