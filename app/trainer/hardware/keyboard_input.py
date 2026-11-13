"""Keyboard as an input source for development and as a demo fallback.

Arrow keys tilt, Space is button A, M is B, C is C, +/- turn the knob.
Number keys 1-4 call tools; letters send the other voice commands as if heard.
"""
from __future__ import annotations

from ..core.events import CommandEvent, InputFrame, KeyEvent
from ..core.service import Service

KEY_COMMANDS = {
    "1": "forceps",
    "2": "swab",
    "3": "clamp",
    "4": "scalpel",
    "l": "light",
    "s": "steady",
    "x": "cancel",
    "r": "repeat",
    "h": "help",
    "p": "pause",
    "o": "continue",
    "n": "new game",
}

KEY_BUTTONS = {"space": InputFrame.BTN_A, "m": InputFrame.BTN_B, "c": InputFrame.BTN_C, "return": InputFrame.BTN_KNOB}


class KeyboardInput(Service):
    name = "keyboard_input"

    def __init__(self, bus, frame_hz: float = 50.0) -> None:
        super().__init__(bus)
        self._down: set[str] = set()
        self._knob = 0
        self._seq = 0
        self._period = 1.0 / frame_hz
        self._acc = 0.0
        self._active = False  # only publish frames once a key was used
        bus.subscribe(KeyEvent, self._on_key)

    def _on_key(self, ev: KeyEvent) -> None:
        if ev.down:
            self._down.add(ev.key)
            self._active = True
            if ev.key in KEY_COMMANDS:
                self.bus.publish(CommandEvent(word=KEY_COMMANDS[ev.key], confidence=1.0))
            elif ev.key in ("plus", "=", "]"):
                self._knob += 1
            elif ev.key in ("minus", "-", "["):
                self._knob -= 1
        else:
            self._down.discard(ev.key)

    def frame(self) -> InputFrame:
        tx = (1.0 if "right" in self._down else 0.0) - (1.0 if "left" in self._down else 0.0)
        ty = (1.0 if "down" in self._down else 0.0) - (1.0 if "up" in self._down else 0.0)
        if "left shift" in self._down or "right shift" in self._down:
            tx *= 0.35
            ty *= 0.35
        buttons = 0
        for key, bit in KEY_BUTTONS.items():
            if key in self._down:
                buttons |= bit
        self._seq += 1
        return InputFrame(tilt_x=tx, tilt_y=ty, knob=self._knob, buttons=buttons, seq=self._seq, source="keyboard")

    def tick(self, dt: float) -> None:
        if not self._active:
            return
        self._acc += dt
        while self._acc >= self._period:
            self._acc -= self._period
            self.bus.publish(self.frame())
