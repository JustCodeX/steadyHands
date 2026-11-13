"""Owns the EventBus and the Service list and runs the main loop."""
from __future__ import annotations

import logging
import time

from .event_bus import EventBus
from .events import QuitRequest
from .service import Service

log = logging.getLogger(__name__)


class App:
    def __init__(self, bus: EventBus | None = None, tick_hz: float = 60.0) -> None:
        self.bus = bus or EventBus()
        self.tick_hz = tick_hz
        self._services: list[Service] = []
        self._running = False
        self.bus.subscribe(QuitRequest, self._on_quit)

    def register(self, service: Service) -> Service:
        self._services.append(service)
        return service

    @property
    def services(self) -> list[Service]:
        return list(self._services)

    def _on_quit(self, _: QuitRequest) -> None:
        self._running = False

    def start(self) -> None:
        for s in self._services:
            log.info("starting %s", s.name)
            s.start()
        self._running = True

    def stop(self) -> None:
        self._running = False
        for s in reversed(self._services):
            try:
                s.stop()
            except Exception:
                log.exception("stopping %s failed", s.name)

    def step(self, dt: float) -> None:
        """One loop pass: deliver events, then tick every service."""
        self.bus.dispatch()
        for s in self._services:
            s.tick(dt)
        self.bus.dispatch()

    def run(self) -> None:
        self.start()
        period = 1.0 / self.tick_hz
        last = time.monotonic()
        try:
            while self._running:
                now = time.monotonic()
                dt = min(now - last, 0.25)  # a stall must not teleport the tool
                last = now
                self.step(dt)
                sleep_for = period - (time.monotonic() - now)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        except KeyboardInterrupt:
            log.info("interrupted")
        finally:
            self.stop()
