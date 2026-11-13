from __future__ import annotations

from ..level import Target
from .base import Instrument


class Forceps(Instrument):
    """Picks up foreign objects: splinters, shards, buttons."""

    word = "forceps"
    label = "Forceps"

    def apply(self, target: Target) -> str:
        target.done = True
        return "item_out"
