#!/usr/bin/env python3
"""Runs on the remote's UNO Q: reads its two Modulino Distance sensors and
sends the measurements to the board that runs the game.

The remote has no display and no game logic - it only measures. Its MCU runs
the same firmware as the main board (CONTROL_MODE 2, two ToF sensors on the
Qwiic chain), so the distances arrive here as the input frame's two distance
fields and go straight out as UDP.

    python3 remote_sender.py --to 192.168.1.155
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import time

log = logging.getLogger("remote_sender")

SENSOR_TOF_X = 1 << 4
SENSOR_TOF_Y = 1 << 5


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="send the remote's distances to the game board")
    p.add_argument("--to", required=True, help="IP or host of the board running the game")
    p.add_argument("--port", type=int, default=9876)
    p.add_argument("--router", default="unix:///var/run/arduino-router.sock")
    p.add_argument("--hz", type=float, default=50.0, help="datagrams per second")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s")

    from arduino.router_bridge import Bridge

    latest: dict[str, int] = {"x": 0, "y": 0, "ok": 0, "b": 0}

    def on_input(tilt_x, tilt_y, knob, buttons, distance_mm, distance_y_mm, sensors_ok, seq) -> None:
        # Runs on the Bridge dispatcher thread: only store, never send here.
        latest["x"] = int(distance_mm)
        latest["y"] = int(distance_y_mm)
        latest["ok"] = int(sensors_ok)
        latest["b"] = int(buttons)  # the remote's own buttons: the freeze key

    bridge = Bridge(args.router)
    bridge.provide("input", on_input)
    if not bridge.connect(timeout=10.0):
        log.error("no MCU on %s", args.router)
        return 1
    log.info("MCU connected; sending to %s:%d at %.0f Hz", args.to, args.port, args.hz)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    period = 1.0 / max(1.0, args.hz)
    seq = 0
    reported = 0.0
    try:
        while True:
            seq += 1
            payload = json.dumps(
                {"x": latest["x"], "y": latest["y"], "ok": latest["ok"], "b": latest["b"], "seq": seq}
            )
            try:
                sock.sendto(payload.encode("utf-8"), (args.to, args.port))
            except OSError as exc:
                log.warning("send failed: %s", exc)  # keep running; the link may come back
            now = time.monotonic()
            if now - reported > 5.0:
                reported = now
                both = latest["ok"] & SENSOR_TOF_X and latest["ok"] & SENSOR_TOF_Y
                log.info(
                    "x=%4d mm  y=%4d mm  sensors=%s  sent=%d",
                    latest["x"], latest["y"], "both" if both else "INCOMPLETE", seq,
                )
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.disconnect()
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
