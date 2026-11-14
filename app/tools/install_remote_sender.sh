#!/usr/bin/env bash
# Installs the remote's sender as a cron job on the remote board itself.
#
# cron, not a systemd user unit: user units die with the last login session
# unless lingering is enabled, and that needs root. cron's @reboot entry starts
# the sender at boot and the minute entry puts it back if it ever stops, both
# without sudo.
#
#   BOARD_SSH=arduino@192.168.1.129 GAME_HOST=192.168.1.155 app/tools/install_remote_sender.sh
set -euo pipefail

BOARD_SSH="${BOARD_SSH:-arduino@192.168.1.129}"
GAME_HOST="${GAME_HOST:-192.168.1.155}"
PORT="${PORT:-9876}"

read -r -d '' SCRIPT <<EOF || true
set -e
mkdir -p \$HOME/bin
cat > \$HOME/bin/steadyhands-remote.sh <<'INNER'
#!/usr/bin/env bash
# Keeps one sender running; cron calls this every minute.
pgrep -f "remote_sender.py" >/dev/null && exit 0
cd \$HOME/promptpimps-unoq/app/tools || exit 1
PYTHONPATH=\$HOME/remote-libs exec python3 remote_sender.py --to ${GAME_HOST} --port ${PORT} >> \$HOME/remote_sender.log 2>&1
INNER
sed -i "s|\\\$HOME|\$HOME|g" \$HOME/bin/steadyhands-remote.sh
chmod +x \$HOME/bin/steadyhands-remote.sh
( crontab -l 2>/dev/null | grep -v steadyhands-remote.sh ; \
  echo "@reboot sleep 20 && \$HOME/bin/steadyhands-remote.sh" ; \
  echo "* * * * * \$HOME/bin/steadyhands-remote.sh" ) | crontab -
crontab -l | grep steadyhands-remote.sh
EOF

ssh "$BOARD_SSH" "$SCRIPT"
echo "sender installed on $BOARD_SSH, sending to ${GAME_HOST}:${PORT}"
