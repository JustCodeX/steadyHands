#!/usr/bin/env bash
# One-time setup of the Linux side on the UNO Q. Run on the board as user arduino:
#   cd ~/promptpimps-unoq/app && setup/board_setup.sh
#
# Step 1 needs sudo (asks for the board password). Everything else is user-level.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "== 1/5 system packages (sudo)"
sudo apt-get install -y --no-install-recommends \
  python3-venv python3-pygame python3-numpy libportaudio2 espeak-ng xset unzip

echo "== 2/5 autologin so the game can use the HDMI display (:0)"
if ! grep -qs "autologin-user=arduino" /etc/lightdm/lightdm.conf.d/*.conf 2>/dev/null; then
  sudo mkdir -p /etc/lightdm/lightdm.conf.d
  printf '[Seat:*]\nautologin-user=arduino\nautologin-user-timeout=0\n' | sudo tee /etc/lightdm/lightdm.conf.d/50-steadyhands.conf >/dev/null
  echo "   autologin configured; takes effect after a reboot or: sudo systemctl restart lightdm"
fi

echo "== 3/5 Python environment"
# The board image ships Python without ensurepip, so bootstrap pip from
# Debian's wheel (no sudo needed), as firmware/tools/board.sh does.
if [[ ! -x .venv/bin/python ]]; then
  T="$(mktemp -d)"
  (cd "$T" && apt-get download python3-pip-whl >/dev/null && dpkg-deb -x python3-pip-whl_*.deb root)
  W="$(ls "$T"/root/usr/share/python-wheels/pip-*.whl)"
  python3 -m venv --without-pip --system-site-packages .venv
  .venv/bin/python "$W/pip" install -q --no-index "$W"
  rm -rf "$T"
fi
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m pip install -q -r requirements-setup.txt || echo "   piper-tts failed to install; clips will use espeak-ng"

echo "== 4/5 models"
setup/download_models.sh

echo "== 5/5 levels and patient lines"
.venv/bin/python tools/make_levels.py
.venv/bin/python tools/render_clips.py

echo
echo "Done. Start the trainer with:  app/run.sh"
