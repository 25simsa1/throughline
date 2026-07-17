#!/bin/bash
# Double-click me to use Throughline.
cd "$(dirname "$0")"
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
