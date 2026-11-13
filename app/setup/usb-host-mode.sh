#!/bin/sh
# Keep the UNO Q's USB-C port in host mode so a hub's USB devices (headset,
# touch panel) stay connected. The Type-C negotiation with some PD hubs flips
# the port to device mode about 16 s after boot; this undoes that whenever it
# happens. Installed as a root systemd service by board_setup.sh.
ROLE=/sys/class/usb_role/4e00000.usb-role-switch/role
while true; do
  if [ "$(cat "$ROLE" 2>/dev/null)" = "device" ]; then
    echo host > "$ROLE"
  fi
  sleep 3
done
