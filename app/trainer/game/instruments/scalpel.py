from __future__ import annotations

from ..level import Target
from .base import Instrument


class Scalpel(Instrument):
    """Opens a sealed passage (stretch goal)."""

    word = "scalpel"
    label = "Scalpel"

    def apply(self, target: Target) -> str:
        target.done = True
        return "opened"
