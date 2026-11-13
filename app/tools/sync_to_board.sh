#!/usr/bin/env bash
# Mirror app/ and levels/ to the board over adb (like firmware/tools/board.sh).
# Keeps the board's .venv, models and logs. The git repo on your computer stays
# the source of truth.
#   app/tools/sync_to_board.sh            copy
#   app/tools/sync_to_board.sh shell      copy, then open a shell in ~/promptpimps-unoq/app
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REMOTE="${REMOTE_DIR:-promptpimps-unoq}"
if [[ -z "${ADB:-}" ]]; then
  if command -v adb >/dev/null 2>&1; then ADB=adb
  else ADB="$(ls -d "$HOME"/Library/Arduino15/packages/arduino/tools/adb/*/adb 2>/dev/null | tail -1)"; fi
fi
"$ADB" shell "mkdir -p ~/$REMOTE/app ~/$REMOTE/levels && cd ~/$REMOTE/app && find . -mindepth 1 -maxdepth 1 ! -name .venv ! -name models ! -name logs -exec rm -rf {} + && rm -rf ~/$REMOTE/levels/*"
COPYFILE_DISABLE=1 tar -C "$REPO_DIR" --no-xattrs \
    --exclude=app/.venv --exclude=app/models --exclude=app/logs --exclude='__pycache__' \
    --exclude=.pytest_cache --exclude=.DS_Store -cf - app levels \
  | "$ADB" shell "tar -C ~/$REMOTE -xf -"
echo "synced app/ and levels/ to the board (~/$REMOTE)"
if [[ "${1:-}" == "shell" ]]; then "$ADB" shell -t "cd ~/$REMOTE/app; exec \$SHELL -l"; fi
