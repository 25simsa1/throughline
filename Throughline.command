#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="python3"; fi
echo "Starting Throughline… a browser window will open. Close this window to stop."
exec "$PY" app/server.py
