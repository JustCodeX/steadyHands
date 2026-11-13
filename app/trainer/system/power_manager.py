"""Idle after a while without input: display standby, microphone off."""
from __future__ import annotations

import logging
import shutil
import subprocess
import time

from ..core.config import SystemConfig
from ..core.events import CommandEvent, IdleChanged, InputFrame, KeyEvent
from ..core.service import Service

log = logging.getLogger(__name__)


class PowerManager(Service):
    name = "power"

    def __init__(self, bus, cfg: SystemConfig, deadzone_g: float = 0.06) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.deadzone_g = deadzone_g
        self._last_activity = time.monotonic()
        self._idle = False
        bus.subscribe(InputFrame, self._on_frame)
        bus.subscribe(CommandEvent, lambda e: self._activity())
        bus.subscribe(KeyEvent, lambda e: self._activity())

    def _on_frame(self, f: InputFrame) -> None:
        if f.buttons or abs(f.tilt_x) > self.deadzone_g * 3 or abs(f.tilt_y) > self.deadzone_g * 3:
            self._activity()

    def _activity(self) -> None:
        self._last_activity = time.monotonic()
        if self._idle:
            self._set_idle(False)

    def tick(self, dt: float) -> None:
        if not self._idle and time.monotonic() - self._last_activity > self.cfg.idle_timeout_s:
            self._set_idle(True)

    @property
    def idle(self) -> bool:
        return self._idle

    def _set_idle(self, idle: bool) -> None:
        self._idle = idle
        log.info("idle %s", "on" if idle else "off")
        self.bus.publish(IdleChanged(idle=idle))
        if self.cfg.display_dpms:
            self._display_power(not idle)

    def _display_power(self, on: bool) -> None:
        xset = shutil.which("xset")
        if not xset:
            return
        try:
            subprocess.run(
                [xset, "-display", self.cfg.display_name, "dpms", "force", "on" if on else "off"],
                check=False,
                timeout=2,
                capture_output=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("xset failed: %s", exc)
