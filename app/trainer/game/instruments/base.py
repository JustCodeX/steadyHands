from __future__ import annotations

from abc import ABC, abstractmethod

from ..level import Target


class Instrument(ABC):
    """A surgical instrument the player can hold."""

    word: str = ""  # the voice command and the `needs` value in level.json
    label: str = ""

    @property
    def name(self) -> str:
        return self.word

    def can_handle(self, target: Target) -> bool:
        return not target.done and target.needs == self.word

    @abstractmethod
    def apply(self, target: Target) -> str:
        """Act on the target. Returns the GameEvent kind to publish."""
