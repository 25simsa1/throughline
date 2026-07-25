#!/bin/bash
# A simple text-menu version, in case the browser window does not open.
cd "$(dirname "$0")/app" || { echo "Could not find the app folder next to me."; read -r -p "Press Return to close."; exit 1; }
clear
if [ ! -x ".venv/bin/python" ]; then
  echo "One thing first, please double-click 'Install Throughline'"
  echo "and let it finish. You only ever do that once."
  echo
  read -r -p "Press Return to close."
  exit 1
fi
./.venv/bin/python menu.py
echo
read -r -p "Press Return to close."
