from __future__ import annotations

from ..level import Target
from .base import Instrument


class Swab(Instrument):
    """Clears blood that hides part of the corridor."""

    word = "swab"
    label = "Swab"

    def apply(self, target: Target) -> str:
        target.done = True
        return "swabbed"
