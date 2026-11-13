"""Thread-safe publish/subscribe. Publishing only enqueues; `dispatch()` runs
handlers on the thread that calls it (the main loop), so services never need
locks of their own."""
from __future__ import annotations

import logging
import queue
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event: Any) -> None:
        """Queue an event. Safe from any thread."""
        self._queue.put(event)

    def pending(self) -> int:
        return self._queue.qsize()

    def dispatch(self, max_events: int = 1000) -> int:
        """Deliver queued events to their handlers. Returns how many were delivered."""
        delivered = 0
        while delivered < max_events:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            self._deliver(event)
            delivered += 1
        return delivered

    def _deliver(self, event: Any) -> None:
        # Handlers registered for a base class also receive subclasses.
        for cls in type(event).__mro__:
            for handler in list(self._handlers.get(cls, ())):
                try:
                    handler(event)
                except Exception:  # one bad handler must not stop the loop
                    log.exception("handler %r failed for %s", handler, type(event).__name__)
