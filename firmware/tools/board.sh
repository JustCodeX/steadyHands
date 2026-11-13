#!/usr/bin/env bash
# Build/flash the MCU sketch on the UNO Q's own Linux side over adb.
#
# The arduinoq PlatformIO platform only builds on Linux and flashes via the
# board's OpenOCD, so this copies the project to the board and runs pio there.
# The git repo on your machine stays the source of truth.
#
#   tools/board.sh setup      one-time: install PlatformIO on the board (no sudo)
#   tools/board.sh build      compile
#   tools/board.sh upload     compile + flash
#   tools/board.sh monitor    open the Serial monitor (Ctrl+C to quit)
#   tools/board.sh reset      reset the MCU without building
#   tools/board.sh pio ...    run any pio command on the board
#   tools/board.sh shell      open a shell in the project dir on the board
#
# Env overrides: ADB (adb binary), ANDROID_SERIAL (pick a board when several
# are attached), REMOTE_DIR (project location on the board).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-promptpimps-unoq/firmware}"   # relative to the board's $HOME
PIO='$HOME/.platformio/penv/bin/pio'

if [[ -z "${ADB:-}" ]]; then
  if command -v adb >/dev/null 2>&1; then
    ADB=adb
  else
    ADB="$(ls -d "$HOME"/Library/Arduino15/packages/arduino/tools/adb/*/adb 2>/dev/null | tail -1)"
  fi
fi
[[ -x "$(command -v "$ADB" 2>/dev/null || echo "$ADB")" ]] || {
  echo "adb not found. Install Arduino App Lab/IDE or set ADB=/path/to/adb." >&2; exit 1; }

remote() { "$ADB" shell "$@"; }

sync_project() {
  # Mirror the project onto the board, keeping only its .pio build cache.
  [[ -n "$REMOTE_DIR" ]] || { echo "REMOTE_DIR must not be empty" >&2; exit 1; }
  remote "mkdir -p ~/$REMOTE_DIR && cd ~/$REMOTE_DIR && find . -mindepth 1 -maxdepth 1 ! -name .pio -exec rm -rf {} +"
  COPYFILE_DISABLE=1 tar -C "$PROJECT_DIR" --no-xattrs \
      --exclude=.pio --exclude=.vscode --exclude=.DS_Store -cf - . \
    | "$ADB" shell "tar -C ~/$REMOTE_DIR -xf -"
}

check_pio() {
  remote "test -x $PIO" || {
    echo "PlatformIO is not installed on the board. Run: tools/board.sh setup" >&2
    exit 1
  }
}

ROUTER_FIX='Flashing needs access to /var/run/arduino-router.sock (group arduino-router).
Fix once per board (asks for the board password), then wait for it to come back:
  tools/board.sh shell
  sudo usermod -aG arduino-router arduino && sudo reboot'

check_router() {
  remote "test -w /var/run/arduino-router.sock" || { echo "$ROUTER_FIX" >&2; exit 1; }
}

setup_board() {
  # The board image ships Python without pip/ensurepip, and installing
  # python3-venv needs sudo. Instead, unpack Debian's pip wheel in user space,
  # create ~/.platformio/penv with it, and pip-install PlatformIO.
  remote 'set -e
    if [ -x $HOME/.platformio/penv/bin/pio ]; then $HOME/.platformio/penv/bin/pio --version; exit 0; fi
    echo "Installing PlatformIO into ~/.platformio/penv ..."
    T=$(mktemp -d); cd "$T"
    apt-get download python3-pip-whl >/dev/null
    dpkg-deb -x python3-pip-whl_*.deb root
    W=$(ls root/usr/share/python-wheels/pip-*.whl)
    python3 -m venv --without-pip $HOME/.platformio/penv
    $HOME/.platformio/penv/bin/python "$W/pip" install -q --no-index "$W"
    $HOME/.platformio/penv/bin/python -m pip install -q platformio
    cd / && rm -rf "$T"
    $HOME/.platformio/penv/bin/pio --version'
  remote "test -w /var/run/arduino-router.sock" || echo "Warning: $ROUTER_FIX" >&2
}

cmd="${1:-build}"; shift || true
case "$cmd" in
  build)   check_pio; sync_project; remote "cd ~/$REMOTE_DIR && $PIO run $*" ;;
  upload)  check_pio; check_router; sync_project; remote "cd ~/$REMOTE_DIR && $PIO run -t upload $*" ;;
  monitor) check_pio; sync_project; "$ADB" shell -t "cd ~/$REMOTE_DIR && $PIO device monitor $*" ;;
  reset)   check_pio; check_router; sync_project; remote "cd ~/$REMOTE_DIR && $PIO run -t reset $*" ;;
  pio)     check_pio; sync_project; "$ADB" shell -t "cd ~/$REMOTE_DIR && $PIO $*" ;;
  setup)   setup_board ;;
  sync)    sync_project ;;
  shell)   "$ADB" shell -t "cd ~/$REMOTE_DIR 2>/dev/null; exec \$SHELL -l" ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
