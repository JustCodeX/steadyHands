#!/usr/bin/env bash
# Downloads the speech models into app/models/ (git-ignored). Run on the board.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS="$APP_DIR/models"
mkdir -p "$MODELS/piper"

VOSK=vosk-model-small-en-us-0.15
# alphacephei.com is unreachable from some networks (it was at the hackathon);
# the HuggingFace mirror serves the identical zip.
VOSK_URL="${VOSK_URL:-https://huggingface.co/rhasspy/vosk-models/resolve/main/en/$VOSK.zip}"
if [[ ! -d "$MODELS/$VOSK" ]]; then
  echo "Downloading $VOSK (40 MB) from $VOSK_URL"
  curl -L --fail -o "$MODELS/$VOSK.zip" "$VOSK_URL"
  (cd "$MODELS" && unzip -q "$VOSK.zip" && rm "$VOSK.zip")
fi

VOICE=en_US-lessac-medium
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
if [[ ! -f "$MODELS/piper/$VOICE.onnx" ]]; then
  echo "Downloading Piper voice $VOICE (about 60 MB)"
  curl -L --fail -o "$MODELS/piper/$VOICE.onnx" "$BASE/$VOICE.onnx"
  curl -L --fail -o "$MODELS/piper/$VOICE.onnx.json" "$BASE/$VOICE.onnx.json"
fi
echo "models ready in $MODELS"
