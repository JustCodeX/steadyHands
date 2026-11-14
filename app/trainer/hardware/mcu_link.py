"""Bridge client for the MCU sketch in firmware/.

Method names must match firmware/lib/Core/Config.h:
  MCU -> us   "input"(tilt_x, tilt_y, knob, buttons, distance_mm, sensors_ok, seq)
  us -> MCU   "leds"(mask), "voice_state"(state), "ping"(), "status"()
"""
from __future__ import annotations

import logging
import time

from ..core.config import McuConfig, TOOL_WORDS
from ..core.events import GameEvent, InputFrame, McuStatus, VoiceStateChanged
from ..core.service import Service

log = logging.getLogger(__name__)

TOOL_LED_MASK = {"forceps": 0b001, "swab": 0b010, "clamp": 0b100, "scalpel": 0b111}


class McuLink(Service):
    name = "mcu_link"

    def __init__(self, bus, cfg: McuConfig) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self._bridge = None
        self._last_frame_t: float | None = None
        self._connected = False
        bus.subscribe(GameEvent, self._on_game_event)
        bus.subscribe(VoiceStateChanged, self._on_voice_state)

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        try:
            from arduino.router_bridge import Bridge
        except ImportError:
            log.error("arduino-router-bridge is not installed; MCU link disabled")
            self.bus.publish(McuStatus(connected=False, detail="library missing"))
            return
        self._bridge = Bridge(self.cfg.address)
        self._bridge.provide("input", self._on_input)
        if self._bridge.connect(timeout=self.cfg.connect_timeout_s):
            log.info("connected to router at %s", self.cfg.address)
        else:
            log.warning("router not reachable yet at %s; keeps trying", self.cfg.address)

    def stop(self) -> None:
        if self._bridge is not None:
            try:
                self._bridge.notify("voice_state", 0)
                self._bridge.notify("leds", 0)
            except Exception:
                pass
            self._bridge.disconnect()
            self._bridge = None

    def tick(self, dt: float) -> None:
        if self._bridge is None:
            return
        now = time.monotonic()
        alive = self._last_frame_t is not None and now - self._last_frame_t < self.cfg.frame_timeout_s
        if alive != self._connected:
            self._connected = alive
            self.bus.publish(McuStatus(connected=alive, detail="frames" if alive else "no frames"))
            log.info("MCU frames %s", "arriving" if alive else "stopped")

    # --- MCU -> bus ----------------------------------------------------------

    def _on_input(self, tilt_x, tilt_y, knob, buttons, distance_mm, distance_y_mm, sensors_ok, seq) -> None:
        # Runs on the Bridge dispatcher thread; publish() only enqueues.
        self._last_frame_t = time.monotonic()
        self.bus.publish(
            InputFrame(
                tilt_x=float(tilt_x),
                tilt_y=float(tilt_y),
                knob=int(knob),
                buttons=int(buttons),
                distance_mm=int(distance_mm),
                distance_y_mm=int(distance_y_mm),
                sensors_ok=int(sensors_ok),
                seq=int(seq),
                source="mcu",
            )
        )

    # --- bus -> MCU ----------------------------------------------------------

    def set_leds(self, mask: int) -> None:
        self._notify("leds", int(mask) & 0x07)

    def set_voice_state(self, state: int) -> None:
        self._notify("voice_state", int(state))

    def ping(self) -> int | None:
        if self._bridge is None:
            return None
        try:
            return int(self._bridge.call("ping", timeout=1.0))
        except Exception as exc:
            log.warning("ping failed: %s", exc)
            return None

    def _notify(self, method: str, *args) -> None:
        if self._bridge is None:
            return
        try:
            self._bridge.notify(method, *args)
        except Exception as exc:
            log.warning("notify %s failed: %s", method, exc)

    def _on_game_event(self, ev: GameEvent) -> None:
        # Wall contact is not signalled here: the buzz plays in the game (SoundService).
        if not self.cfg.tool_leds:
            return
        if ev.kind == "tool_changed":
            self.set_leds(TOOL_LED_MASK.get(ev.detail, 0))
        elif ev.kind in ("round_started",):
            self.set_leds(TOOL_LED_MASK.get(ev.detail, 0))
        elif ev.kind in ("menu", "lose", "win"):
            self.set_leds(0)

    def _on_voice_state(self, ev: VoiceStateChanged) -> None:
        self.set_voice_state(ev.state.value)


__all__ = ["McuLink", "TOOL_LED_MASK", "TOOL_WORDS"]
