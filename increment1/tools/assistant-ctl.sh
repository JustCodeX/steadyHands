#!/usr/bin/env bash
# Start and stop the assistant on the board.
#
# Uses a pid file rather than pkill: matching the process by its command line
# also matches the ssh command that does the matching, which kills your own
# session.
#
#   tools/assistant-ctl.sh start|stop|restart|status|log
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/trainer-app}"
VENV="${VENV:-$HOME/trainer-venv}"
PIDFILE=/tmp/assistant.pid
LOGFILE=/tmp/assistant.log

running() { [[ -f $PIDFILE ]] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; }

case "${1:-status}" in
  start)
    running && { echo "already running as $(cat $PIDFILE)"; exit 0; }
    cd "$APP_DIR"
    # -u so the log is readable while it runs; python buffers into a file.
    setsid nohup "$VENV/bin/python" -u assistant.py > "$LOGFILE" 2>&1 < /dev/null &
    echo $! > $PIDFILE
    echo "started as $(cat $PIDFILE)"
    ;;
  stop)
    running || { echo "not running"; exit 0; }
    kill "$(cat $PIDFILE)" && rm -f $PIDFILE
    echo stopped
    ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  status)  running && echo "running as $(cat $PIDFILE)" || echo "not running" ;;
  log)     tail -n "${2:-20}" "$LOGFILE" ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
