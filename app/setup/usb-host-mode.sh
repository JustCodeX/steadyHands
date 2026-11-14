#!/bin/sh
# Keep the hub's USB devices (headset, touch panel) connected to the UNO Q.
# Installed as a root systemd service by board_setup.sh. Two jobs:
#
# 1. Host mode. The Type-C negotiation with some PD hubs flips the port to
#    device mode about 16 s after boot; this undoes that whenever it happens.
#
# 2. Failed hub ports. In most boots the workshop hub refuses its directly
#    attached devices (kernel: "unable to enumerate USB device"); the port's
#    state then stays "default". Restarting the USB-C port makes the hub try
#    again, and a minority of tries works (13 Nov: 1 of 9 restarts, 3 of 10
#    boots). So: while a hub port has a device attached that did not connect,
#    restart the port, up to MAX_TRIES times.
#    A port with nothing attached reads "not attached" and causes no restart.
#    Each restart drops the hub's Ethernet and the touch panel for a few seconds.
#
# Log: journalctl -u steadyhands-usb-host
# Try again after it gave up: sudo systemctl restart steadyhands-usb-host
ROLE="${ROLE:-/sys/class/usb_role/4e00000.usb-role-switch/role}"
PORT_STATES="${PORT_STATES:-/sys/bus/usb/devices/*/*:1.0/*-port*/state}"
MAX_TRIES="${MAX_TRIES:-15}"
POLL_S="${POLL_S:-3}"        # time between two looks
DEVICE_S="${DEVICE_S:-2}"    # time the port spends in device mode during a restart
SETTLE_S="${SETTLE_S:-10}"   # time the hub gets to connect its devices after a restart

log() { echo "steadyhands-usb: $*"; }

# Names of the hub ports whose device is attached but did not connect.
failed_ports() {
  for f in $PORT_STATES; do
    [ -r "$f" ] || continue
    case "$(cat "$f" 2>/dev/null)" in
      "not attached" | configured | "") ;;
      *) basename "$(dirname "$f")" ;;
    esac
  done
}

tries=0     # port restarts in this incident
seen=0      # consecutive looks that found a failed port
gave_up=0
while true; do
  if [ "$(cat "$ROLE" 2>/dev/null)" = "device" ]; then
    echo host > "$ROLE"
    seen=0
    sleep "$POLL_S"
    continue
  fi

  failed="$(failed_ports | tr '\n' ' ' | sed 's/ $//')"
  if [ -z "$failed" ]; then
    if [ "$tries" -gt 0 ]; then
      log "no failed hub port left after $tries port restart(s)"
    fi
    tries=0
    seen=0
    gave_up=0
  elif [ "$gave_up" -eq 0 ]; then
    # A port is briefly in "default" while a device connects normally, so act
    # only when two looks in a row find it there.
    seen=$((seen + 1))
    if [ "$seen" -ge 2 ]; then
      if [ "$tries" -ge "$MAX_TRIES" ]; then
        log "gave up after $tries port restart(s); still failed: $failed"
        gave_up=1
      else
        tries=$((tries + 1))
        log "failed hub port(s) $failed: port restart $tries of $MAX_TRIES"
        echo device > "$ROLE"
        sleep "$DEVICE_S"
        echo host > "$ROLE"
        sleep "$SETTLE_S"
        continue  # the hub had its time: look again at once
      fi
    fi
  fi
  sleep "$POLL_S"
done
