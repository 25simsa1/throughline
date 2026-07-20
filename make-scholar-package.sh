#!/bin/bash
# assembles the give-to-a-scholar zip. code comes from the repo, and the
# LOCAL rubric.md + gold/ (never in git) ride along so her copy is
# calibrated to her. usage: ./make-scholar-package.sh [outdir]
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-$HOME/Desktop}"
PKG_DIR="$(mktemp -d)/Throughline"
APP="$PKG_DIR/app"          # all machinery hides in here
mkdir -p "$APP"

# the only three things she should ever see, at the top level
cp "package/Install Throughline.command" "package/Throughline.command" \
   "package/READ ME FIRST.txt" "$PKG_DIR/"
chmod +x "$PKG_DIR/Install Throughline.command" "$PKG_DIR/Throughline.command"

# everything else lives inside app/ where she never has to look
cp -R loaders stages templates "$APP/"
cp models.py store.py ingest.py schemas.py verify.py render.py llm.py \
   graph.py throughline.py menu.py "$APP/"
mkdir -p "$APP/chapters" "$APP/gold"
[ -f rubric.md ] && cp rubric.md "$APP/"
[ -d gold ] && cp -R gold/. "$APP/gold/" 2>/dev/null || true
find "$PKG_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

ZIP="$OUT/Throughline.zip"
rm -f "$ZIP"
(cd "$(dirname "$PKG_DIR")" && zip -r -q "$ZIP" "Throughline")
echo "wrote $ZIP"
unzip -l "$ZIP" | tail -3
