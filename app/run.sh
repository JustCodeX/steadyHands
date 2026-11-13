#!/usr/bin/env bash
# Start the trainer on the board's HDMI display. Extra flags go to python -m trainer.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
PY=".venv/bin/python"; [[ -x "$PY" ]] || PY=python3
exec "$PY" -m trainer "$@"
