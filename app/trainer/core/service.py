"""Base class for every feature on the Linux side."""
from __future__ import annotations

from abc import ABC

from .event_bus import EventBus


class Service(ABC):
    """A feature. It talks to the rest of the app only through the bus.

    Subclasses override `start`, `stop` and `tick`. Subscriptions are usually
    made in `__init__` or `start`.
    """

    name: str = "service"

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def start(self) -> None:  # noqa: B027 - optional hook
        """Acquire resources (threads, devices, windows)."""

    def stop(self) -> None:  # noqa: B027 - optional hook
        """Release everything acquired in start()."""

    def tick(self, dt: float) -> None:  # noqa: B027 - optional hook
        """Called from the main loop; dt is seconds since the last tick."""
