#!/bin/bash
# One-time setup. Double-click me (the first time, right-click and choose Open).
cd "$(dirname "$0")/app" || { echo "Could not find the app folder next to me."; read -r -p "Press Return to close."; exit 1; }
clear
echo "========================================================"
echo "  THROUGHLINE SETUP"
echo "  This runs once. It downloads the AI engine and a"
echo "  language model, together a few gigabytes, so it can"
echo "  take 20 to 45 minutes depending on your internet."
echo "  Leave this window open until it says ALL DONE."
echo "========================================================"
echo

fail() { echo; echo "SETUP STOPPED: $1"; echo; read -r -p "Press Return to close."; exit 1; }

# 1. Python (macOS installs its developer tools on first use)
echo "Step 1 of 4. Checking Python..."
if ! /usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
  echo "  Your Mac will now show a window asking to install"
  echo "  'command line developer tools'. Click Install, wait for"
  echo "  it to finish, then double-click me again."
  /usr/bin/python3 --version >/dev/null 2>&1
  fail "Python is not ready yet. Run me again after the tools install."
fi
echo "  Python is ready."

# 2. Ollama, the engine that runs the model
echo "Step 2 of 4. Checking the AI engine (Ollama)..."
if [ ! -d "/Applications/Ollama.app" ] && ! command -v ollama >/dev/null 2>&1; then
  echo "  Downloading Ollama (about 450 MB)..."
  curl -L --progress-bar -o /tmp/Ollama-darwin.zip "https://ollama.com/download/Ollama-darwin.zip" \
    || fail "The Ollama download did not work. Check your internet and run me again."
  ditto -xk /tmp/Ollama-darwin.zip /Applications || fail "Could not install Ollama."
  rm -f /tmp/Ollama-darwin.zip
fi
open -a Ollama || fail "Could not start Ollama."
echo "  Waiting for the engine to wake up..."
OLLAMA=ollama
command -v ollama >/dev/null 2>&1 || OLLAMA="/Applications/Ollama.app/Contents/Resources/ollama"
for i in $(seq 1 30); do
  curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null && break
  sleep 2
done
curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null || fail "Ollama did not start. Open the Ollama app from Applications once, then run me again."
echo "  Engine is running."

# 3. Pick a model that fits this Mac, then download it
echo "Step 3 of 4. Downloading the language model..."
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if [ "$RAM_GB" -ge 16 ]; then MODEL="qwen3:14b"; else MODEL="granite3.3:8b"; fi
echo "  This Mac has ${RAM_GB} GB of memory, using the model $MODEL."
echo "  This is the big download. Progress will appear below."
"$OLLAMA" pull "$MODEL" || fail "The model download did not finish. Run me again, it resumes."
"$OLLAMA" pull granite-embedding:30m || fail "The small helper model did not download. Run me again."
echo "$MODEL" > model.txt
echo "  Models are ready."

# 4. The tool's own working parts
echo "Step 4 of 4. Setting up the tool..."
/usr/bin/python3 -m venv .venv || fail "Could not create the tool's workspace."
./.venv/bin/pip -q install --upgrade pip || fail "Could not update the installer."
./.venv/bin/pip -q install pymupdf ebooklib beautifulsoup4 pytesseract Pillow ocrmac \
  || fail "Could not install the tool's parts. Check your internet and run me again."

echo
echo "========================================================"
echo "  ALL DONE. From now on, just double-click Throughline."
echo "========================================================"
echo
read -r -p "Press Return to close."
