#!/usr/bin/env python3
"""M0 check for the MCU link, without the game: prints input frames and tests
alarm/leds/voice_state. Run on the board:  python tools/bridge_probe.py [seconds]
"""
from __future__ import annotations

import sys
import time

from arduino.router_bridge import Bridge

frames = 0
last = None


def on_input(tilt_x, tilt_y, knob, buttons, distance_mm, sensors_ok, seq):
    global frames, last
    frames += 1
    last = (tilt_x, tilt_y, knob, buttons, distance_mm, sensors_ok, seq)


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    b = Bridge()
    b.provide("input", on_input)
    if not b.connect(timeout=5):
        print("router not reachable")
        return 1
    print("ping ->", b.call("ping", timeout=2))
    print("status (sensor bits) ->", b.call("status", timeout=2))
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        time.sleep(1.0)
        print(f"{frames / (time.monotonic() - t0):5.1f} frames/s  last={last}")
    for state in (1, 2, 3, 0):
        b.notify("voice_state", state)
        time.sleep(0.4)
    b.notify("leds", 0b101)
    b.notify("alarm", 300)
    time.sleep(0.6)
    b.notify("leds", 0)
    b.disconnect()
    return 0 if frames > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
