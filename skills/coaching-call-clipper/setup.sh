#!/usr/bin/env bash
# Set up the coaching-call-clipper Python environment (macOS / Linux).
# Creates a fixed, user-level virtual environment at
# ~/.coaching-call-clipper/.venv, installs faster-whisper, and adds the NVIDIA CUDA
# wheels when a GPU is detected (Linux). Safe to re-run.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ROOT="$HOME/.coaching-call-clipper"
VENV_DIR="$VENV_ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"

echo "coaching-call-clipper setup (macOS / Linux)"

# 1. Python present?
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found on PATH. Install Python 3.9+ and re-run this script." >&2
    exit 1
fi

# 2. Create the venv if missing.
if [ ! -x "$VENV_PY" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    mkdir -p "$VENV_ROOT"
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR."
fi

# 3. Install dependencies.
echo "Installing dependencies (this can take a few minutes the first time)..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt"

# 4. GPU wheels if an NVIDIA GPU is present (Linux). macOS has no CUDA, so it is skipped.
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU detected; installing CUDA wheels for GPU transcription..."
    "$VENV_PY" -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
else
    echo "No NVIDIA GPU detected; transcription will run on CPU (slower, but works)."
fi

# 5. ffmpeg check.
if command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg found."
else
    echo "ffmpeg was NOT found on PATH. Install it before transcribing or exporting:"
    echo "    macOS:        brew install ffmpeg"
    echo "    Debian/Ubuntu: sudo apt install ffmpeg"
fi

echo ""
echo "Done. Interpreter: $VENV_PY"
