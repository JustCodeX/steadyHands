from __future__ import annotations

from ..level import Target
from .base import Instrument


class Clamp(Instrument):
    """Stops a bleeding and its timer."""

    word = "clamp"
    label = "Clamp"

    def apply(self, target: Target) -> str:
        target.done = True
        target.timer_left = None
        return "clamped"
