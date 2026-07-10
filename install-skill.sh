#!/usr/bin/env bash
set -euo pipefail
dst="$HOME/.claude/skills/throughline"
mkdir -p "$(dirname "$dst")"
ln -sfn "$(cd "$(dirname "$0")" && pwd)/skills/throughline" "$dst"
echo "linked $dst -> repo skills/throughline"
